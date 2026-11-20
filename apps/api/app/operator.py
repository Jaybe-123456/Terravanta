"""Offline operator commands for provisioning pilot staff and cooperatives.

Run these commands inside the trusted API environment. They are not HTTP routes.
"""

import argparse
import re
import sys
from uuid import UUID

from sqlalchemy import func

from .db import AdminSessionLocal
from .models import AuditLog, Farm, FarmMember, Organization, OrganizationMember, SupabaseIdentityLink, User, UserRole


def create_cooperative(name: str) -> UUID:
    normalized_name = name.strip()
    if len(normalized_name) < 2 or len(normalized_name) > 180:
        raise ValueError("Cooperative name must be between 2 and 180 characters")
    with AdminSessionLocal() as db:
        existing = db.query(Organization).filter(
            Organization.kind == "cooperative",
            func.lower(Organization.name) == normalized_name.lower(),
        ).first()
        if existing:
            raise ValueError("A cooperative with this name is already registered")
        organization = Organization(name=normalized_name, kind="cooperative")
        db.add(organization)
        db.flush()
        db.add(AuditLog(action="operator.cooperative_created", entity_type="organization", entity_id=str(organization.id)))
        db.commit()
        return organization.id


def create_processor(name: str) -> UUID:
    normalized_name = name.strip()
    if len(normalized_name) < 2 or len(normalized_name) > 180:
        raise ValueError("Processor name must be between 2 and 180 characters")
    with AdminSessionLocal() as db:
        existing = db.query(Organization).filter(
            Organization.kind == "processor",
            func.lower(Organization.name) == normalized_name.lower(),
        ).first()
        if existing:
            raise ValueError("A processor with this name is already registered")
        organization = Organization(name=normalized_name, kind="processor")
        db.add(organization)
        db.flush()
        db.add(AuditLog(action="operator.processor_created", entity_type="organization", entity_id=str(organization.id)))
        db.commit()
        return organization.id


def provision_user(
    *,
    supabase_user_id: UUID,
    name: str,
    email: str,
    role: str,
    farm_id: UUID | None = None,
    organization_id: UUID | None = None,
) -> UUID:
    display_name = name.strip()
    normalized_email = email.strip().lower()
    if len(display_name) < 2 or len(display_name) > 120:
        raise ValueError("Name must be between 2 and 120 characters")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized_email):
        raise ValueError("Enter a valid email address")
    if role not in {"veterinarian", "cooperative_admin", "processor_admin"}:
        raise ValueError("Only veterinarian, cooperative_admin and processor_admin roles can be provisioned with this command")
    if role == "veterinarian" and (farm_id is None or organization_id is not None):
        raise ValueError("A veterinarian must be assigned to one farm and cannot receive an organization assignment")
    if role in {"cooperative_admin", "processor_admin"} and (organization_id is None or farm_id is not None):
        raise ValueError("An organization user must be assigned to one organization")

    with AdminSessionLocal() as db:
        if role == "veterinarian" and not db.get(Farm, farm_id):
            raise ValueError("Farm not found; check the farm UUID before provisioning")
        if role in {"cooperative_admin", "processor_admin"}:
            organization = db.get(Organization, organization_id)
            expected_kind = "cooperative" if role == "cooperative_admin" else "processor"
            if not organization or organization.kind != expected_kind:
                raise ValueError(f"{expected_kind.title()} organization not found; check its UUID before provisioning")

        identity_link = db.get(SupabaseIdentityLink, supabase_user_id)
        user = db.get(User, identity_link.user_id) if identity_link else db.get(User, supabase_user_id)
        email_owner = db.query(User).filter(func.lower(User.email) == normalized_email).first()
        if email_owner and user and email_owner.id != user.id:
            raise ValueError("This email is already linked to a different Terravanta identity")
        if not user and email_owner:
            other_link = db.query(SupabaseIdentityLink).filter_by(user_id=email_owner.id).first()
            if other_link:
                raise ValueError("This email is already linked to a different Supabase identity")
            user = email_owner
            if user.id != supabase_user_id:
                db.add(SupabaseIdentityLink(supabase_user_id=supabase_user_id, user_id=user.id))
        if user and user.email.lower() != normalized_email:
            raise ValueError("The Supabase identity is already linked to a different email")

        user_id = user.id if user else supabase_user_id
        assigned_roles = {row.role for row in db.query(UserRole).filter_by(user_id=user_id).all()}
        if assigned_roles and assigned_roles != {role}:
            can_convert_unassigned_farmer = (
                assigned_roles == {"farmer"}
                and role in {"cooperative_admin", "processor_admin"}
                and not db.query(FarmMember.farm_id).filter_by(user_id=user_id).first()
                and not db.query(Farm.id).filter_by(created_by=user_id).first()
            )
            if not can_convert_unassigned_farmer:
                raise ValueError("This account already has a role or farm data; operator review is required before changing access")
            db.query(UserRole).filter_by(user_id=user_id, role="farmer").delete(synchronize_session=False)
            assigned_roles = set()
        if not user:
            user = User(id=supabase_user_id, display_name=display_name, email=normalized_email)
            db.add(user)
            user_id = supabase_user_id
        else:
            user.display_name = display_name

        if role not in assigned_roles:
            db.add(UserRole(user_id=user_id, role=role))
        if role == "veterinarian":
            membership = db.get(FarmMember, (farm_id, user_id))
            if membership and membership.role != "veterinarian":
                raise ValueError("This account already has a different role on the selected farm")
            if not membership:
                db.add(FarmMember(farm_id=farm_id, user_id=user_id, role="veterinarian"))
        else:
            membership = db.get(OrganizationMember, (organization_id, user_id))
            if membership and membership.role != role:
                raise ValueError("This account already has a different role in the selected organization")
            if not membership:
                db.add(OrganizationMember(organization_id=organization_id, user_id=user_id, role=role))

        db.add(AuditLog(
            action="operator.staff_provisioned",
            entity_type="user",
            entity_id=str(user_id),
            farm_id=farm_id,
            metadata_json={"role": role, "organization_id": str(organization_id) if organization_id else None},
        ))
        db.commit()
        return user_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision Terravanta pilot organizations and staff accounts")
    commands = parser.add_subparsers(dest="command", required=True)

    cooperative = commands.add_parser("create-cooperative", help="Create a cooperative organization")
    cooperative.add_argument("--name", required=True)

    processor = commands.add_parser("create-processor", help="Create a processor counterparty organization")
    processor.add_argument("--name", required=True)

    staff = commands.add_parser("provision-user", help="Assign a signed-up Supabase identity to a staff role")
    staff.add_argument("--supabase-user-id", required=True, type=UUID)
    staff.add_argument("--name", required=True)
    staff.add_argument("--email", required=True)
    staff.add_argument("--role", required=True, choices=["veterinarian", "cooperative_admin", "processor_admin"])
    staff.add_argument("--farm-id", type=UUID)
    staff.add_argument("--organization-id", type=UUID)

    args = parser.parse_args()
    try:
        if args.command == "create-cooperative":
            entity_id = create_cooperative(args.name)
            print(f"Created cooperative organization {entity_id}")
        elif args.command == "create-processor":
            entity_id = create_processor(args.name)
            print(f"Created processor organization {entity_id}")
        else:
            entity_id = provision_user(
                supabase_user_id=args.supabase_user_id,
                name=args.name,
                email=args.email,
                role=args.role,
                farm_id=args.farm_id,
                organization_id=args.organization_id,
            )
            print(f"Provisioned {args.role} account {entity_id}")
    except (ValueError, TypeError) as exc:
        print(f"Provisioning failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
