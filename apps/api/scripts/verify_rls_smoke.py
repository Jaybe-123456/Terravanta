"""Exercise the core tenant-isolation and consent projection policies in PostgreSQL."""

import os
from uuid import uuid4

from sqlalchemy import create_engine, text


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)
    farmer_a, farmer_b, cooperative_user = uuid4(), uuid4(), uuid4()
    legacy_farmer, legacy_subject = uuid4(), uuid4()
    staff_user, staff_subject = uuid4(), uuid4()
    farm_a, farm_b, cooperative_id = uuid4(), uuid4(), uuid4()
    cooperative_email = f"{cooperative_user}@rls.test"

    with engine.begin() as connection:
        identity_map_direct_access = connection.scalar(text("""
            SELECT has_table_privilege('terravanta_app', 'public.supabase_identity_links', 'SELECT')
        """))
        assert identity_map_direct_access is False, "runtime role must not read the provider-to-user identity map directly"

        for user_id, name, email in (
            (farmer_a, "Farmer A", f"{farmer_a}@rls.test"),
            (farmer_b, "Farmer B", f"{farmer_b}@rls.test"),
            (cooperative_user, "Cooperative Reviewer", cooperative_email),
        ):
            connection.execute(text("""
                INSERT INTO public.users (id, display_name, email, created_at)
                VALUES (:id, :name, :email, now())
            """), {"id": user_id, "name": name, "email": email})

        connection.execute(text("""
            INSERT INTO public.users (id, display_name, email, created_at)
            VALUES (:id, 'Legacy Farmer', 'legacy-farmer@rls.test', now()),
                   (:staff_id, 'Clinic Veterinarian', 'clinic-vet@rls.test', now())
        """), {"id": legacy_farmer, "staff_id": staff_user})
        connection.execute(text("""
            INSERT INTO public.user_roles (user_id, role)
            VALUES (:farmer_id, 'farmer'), (:staff_id, 'veterinarian')
        """), {"farmer_id": legacy_farmer, "staff_id": staff_user})

        for farm_id, owner_id, code in ((farm_a, farmer_a, "RLS-A"), (farm_b, farmer_b, "RLS-B")):
            connection.execute(text("""
                INSERT INTO public.farms
                    (id, code, name, owner_name, county, subcounty, size_acres,
                     farming_system, production_activities, verification_status,
                     is_synthetic, created_by, created_at)
                VALUES
                    (:id, :code, :name, :owner, 'Kiambu', 'Test', 1,
                     'mixed', '[]'::json, 'farmer_submitted', false, :owner_id, now())
            """), {
                "id": farm_id,
                "code": code,
                "name": f"Farm {code}",
                "owner": f"Owner {code}",
                "owner_id": owner_id,
            })
            connection.execute(text("""
                INSERT INTO public.farm_members (farm_id, user_id, role)
                VALUES (:farm_id, :owner_id, 'owner')
            """), {"farm_id": farm_id, "owner_id": owner_id})
            connection.execute(text("""
                INSERT INTO public.user_roles (user_id, role)
                VALUES (:owner_id, 'farmer')
            """), {"owner_id": owner_id})

        connection.execute(text("""
            INSERT INTO public.organizations (id, name, kind, created_at)
            VALUES (:id, 'RLS Test Cooperative', 'cooperative', now())
        """), {"id": cooperative_id})
        connection.execute(text("""
            INSERT INTO public.organization_members (organization_id, user_id, role)
            VALUES (:organization_id, :user_id, 'cooperative_admin')
        """), {"organization_id": cooperative_id, "user_id": cooperative_user})
        connection.execute(text("""
            INSERT INTO public.user_roles (user_id, role)
            VALUES (:user_id, 'cooperative_admin')
        """), {"user_id": cooperative_user})
        connection.execute(text("""
            INSERT INTO public.consents
                (id, farm_id, granted_by, grantee_org_id, grantee_email, scope, status, created_at)
            VALUES (:id, :farm_id, :granted_by, :organization_id, '', 'delivery_summary', 'active', now())
        """), {
            "id": uuid4(), "farm_id": farm_b, "granted_by": farmer_b, "organization_id": cooperative_id,
        })
        connection.execute(text("""
            INSERT INTO public.consents
                (id, farm_id, granted_by, grantee_org_id, grantee_email, scope, status, created_at)
            VALUES (:id, :farm_id, :granted_by, NULL, :email, 'delivery_summary', 'active', now())
        """), {"id": uuid4(), "farm_id": farm_a, "granted_by": farmer_a, "email": cooperative_email})

        connection.exec_driver_sql("SET LOCAL ROLE terravanta_app")
        connection.execute(text("SELECT set_config('terravanta.user_id', :user_id, true)"), {"user_id": str(farmer_a)})
        visible_farms = set(connection.scalars(text("SELECT id FROM public.farms")))
        visible_users = set(connection.scalars(text("SELECT id FROM public.users")))
        assert visible_farms == {farm_a}, f"farmer saw another farm: {visible_farms}"
        assert visible_users == {farmer_a}, f"farmer saw another user: {visible_users}"

        connection.exec_driver_sql("SET LOCAL ROLE terravanta_app")
        connection.execute(text("SELECT set_config('terravanta.user_id', :user_id, true)"), {"user_id": str(cooperative_user)})
        direct_farm_read = connection.scalar(text("SELECT count(*) FROM public.farms WHERE id = :farm_id"), {"farm_id": farm_b})
        shared_card = connection.execute(text("""
            SELECT id, name, code, is_synthetic
            FROM terravanta_private.shared_farm_card(:farm_id)
        """), {"farm_id": farm_b}).mappings().first()
        email_grant_visible = connection.scalar(text("""
            SELECT count(*) FROM public.consents
            WHERE farm_id = :farm_id AND lower(grantee_email) = lower(:email)
        """), {"farm_id": farm_a, "email": cooperative_email})
        assert direct_farm_read == 0, "cooperative consent exposed the complete farm row"
        assert shared_card and shared_card["id"] == farm_b, "consented farm-card projection was not available"
        assert email_grant_visible == 1, "email-targeted consent was hidden from the assigned cooperative user"

        connection.execute(text("SELECT set_config('terravanta.auth_subject', :subject, true)"), {"subject": str(legacy_subject)})
        linked = connection.execute(text("""
            SELECT internal_user_id, outcome
            FROM terravanta_private.claim_farmer_identity(:subject, 'legacy-farmer@rls.test', 'Legacy Farmer')
        """), {"subject": legacy_subject}).mappings().one()
        assert linked["internal_user_id"] == legacy_farmer
        assert linked["outcome"] == "linked_legacy_farmer"
        connection.execute(text("SELECT set_config('terravanta.user_id', :user_id, true)"), {"user_id": str(legacy_farmer)})
        resolved = connection.scalar(text("SELECT terravanta_private.resolve_auth_user(:subject)"), {"subject": legacy_subject})
        assert resolved == legacy_farmer, "verified Supabase subject did not resolve to the existing farmer ID"
        visible_profile = set(connection.scalars(text("SELECT id FROM public.users")))
        assert visible_profile == {legacy_farmer}, "identity mapping widened the user's profile visibility"

        connection.execute(text("SELECT set_config('terravanta.auth_subject', :subject, true)"), {"subject": str(staff_subject)})
        staff_claim = connection.execute(text("""
            SELECT internal_user_id, outcome
            FROM terravanta_private.claim_farmer_identity(:subject, 'clinic-vet@rls.test', 'Impersonator')
        """), {"subject": staff_subject}).mappings().one()
        assert staff_claim["internal_user_id"] is None and staff_claim["outcome"] == "conflict", \
            "self-service onboarding must not claim an existing staff identity"

    engine.dispose()
    print("RLS smoke check passed: farmer isolation and consent-limited farm projection")


if __name__ == "__main__":
    main()
