"""Verify bilateral receivables RLS using only the ephemeral CI PostGIS database."""

import os
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    seller_org, processor_org, outsider_org = uuid4(), uuid4(), uuid4()
    seller_user, processor_user, outsider_user = uuid4(), uuid4(), uuid4()
    relationship_id, case_id, line_id, artifact_id, receipt_id = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()

    with engine.begin() as connection:
        for organization_id, name in (
            (seller_org, "RLS Seller Cooperative"),
            (processor_org, "RLS Processor"),
            (outsider_org, "RLS Unrelated Organization"),
        ):
            connection.execute(text("""
                INSERT INTO public.organizations (id, name, kind, created_at)
                VALUES (:id, :name, :kind, now())
            """), {"id": organization_id, "name": name, "kind": "cooperative" if organization_id != processor_org else "processor"})
        for user_id, name in (
            (seller_user, "RLS Seller User"),
            (processor_user, "RLS Processor User"),
            (outsider_user, "RLS Outsider User"),
        ):
            connection.execute(text("""
                INSERT INTO public.users (id, display_name, email, created_at)
                VALUES (:id, :name, :email, now())
            """), {"id": user_id, "name": name, "email": f"{user_id}@receivables-rls.test"})
        for organization_id, user_id, role in (
            (seller_org, seller_user, "cooperative_admin"),
            (processor_org, processor_user, "processor_admin"),
            (outsider_org, outsider_user, "cooperative_admin"),
        ):
            connection.execute(text("""
                INSERT INTO public.organization_members (organization_id, user_id, role)
                VALUES (:org, :user, :role)
            """), {"org": organization_id, "user": user_id, "role": role})

        connection.execute(text("""
            INSERT INTO public.counterparty_relationships
                (id, organization_id, counterparty_organization_id, counterparty_name,
                 relationship_type, external_reference, status, created_by, created_at)
            VALUES (:id, :seller, :processor, 'RLS Processor', 'processor', :ref, 'active', :user, now())
        """), {"id": relationship_id, "seller": seller_org, "processor": processor_org,
               "ref": f"RLS-{relationship_id}", "user": seller_user})
        connection.execute(text("""
            INSERT INTO public.receivable_cases
                (id, organization_id, relationship_id, counterparty_organization_id,
                 source_document_type, source_reference, currency, asserted_amount, status,
                 description, created_by, created_at, updated_at)
            VALUES (:id, :seller, :relationship, :processor, 'invoice', :ref, 'KES', 100,
                    'submitted', 'RLS isolation fixture', :user, now(), now())
        """), {"id": case_id, "seller": seller_org, "relationship": relationship_id,
               "processor": processor_org, "ref": f"CASE-{case_id}", "user": seller_user})
        connection.execute(text("""
            INSERT INTO public.receivable_case_lines
                (id, organization_id, case_id, line_number, line_type, direction,
                 amount, currency, source_locator, provenance_class, created_by, created_at)
            VALUES (:id, :seller, :case, 1, 'accepted_supply', 'increase', 100,
                    'KES', 'row:1', 'seller_attested', :user, now())
        """), {"id": line_id, "seller": seller_org, "case": case_id, "user": seller_user})
        connection.execute(text("""
            INSERT INTO public.evidence_artifacts
                (id, organization_id, uploaded_by, source_party, source_system,
                 source_reference, filename, media_type, artifact_type, sha256,
                 storage_key, sensitivity, source_metadata, created_at)
            VALUES (:id, :org, :user, 'counterparty', 'processor_upload', 'RLS fixture',
                    'processor.csv', 'text/csv', 'processor_statement', repeat('a', 64),
                    :key, 'confidential', '{}'::json, now())
        """), {"id": artifact_id, "org": processor_org, "user": processor_user,
               "key": f"rls-fixture/{artifact_id}.csv"})

        def become(user_id):
            connection.exec_driver_sql("SET LOCAL ROLE terravanta_app")
            connection.execute(text("SELECT set_config('terravanta.user_id', :id, true)"), {"id": str(user_id)})

        become(processor_user)
        assert connection.scalar(text("SELECT count(*) FROM public.receivable_cases WHERE id = :id"), {"id": case_id}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.receivable_case_lines WHERE case_id = :id"), {"id": case_id}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.evidence_artifacts WHERE id = :id"), {"id": artifact_id}) == 1
        become(seller_user)
        connection.execute(text("""
            INSERT INTO public.client_write_receipts
                (id, actor_user_id, idempotency_key, request_hash, response_json, created_at)
            VALUES (:id, :actor, :key, repeat('b', 64), '{}'::json, now())
        """), {"id": receipt_id, "actor": seller_user, "key": f"ci-{receipt_id}"})
        assert connection.scalar(text("SELECT count(*) FROM public.client_write_receipts WHERE id = :id"), {"id": receipt_id}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.evidence_artifacts WHERE id = :id"), {"id": artifact_id}) == 0, "seller saw processor evidence before it was attached to the claim"
        become(processor_user)
        assert connection.scalar(text("SELECT count(*) FROM public.client_write_receipts WHERE id = :id"), {"id": receipt_id}) == 0, "processor saw another user's offline write receipt"
        connection.execute(text("""
            INSERT INTO public.counterparty_case_evidence
                (id, organization_id, case_id, counterparty_organization_id, artifact_id,
                 source_locator, linked_by, created_at)
            VALUES (:id, :seller, :case, :processor, :artifact, 'processor-row:1', :user, now())
        """), {"id": uuid4(), "seller": seller_org, "case": case_id,
               "processor": processor_org, "artifact": artifact_id, "user": processor_user})
        connection.execute(text("""
            INSERT INTO public.counterparty_line_reviews
                (id, organization_id, case_id, case_line_id, counterparty_organization_id,
                 reviewed_by_user_id, review_status, seller_amount_snapshot, processor_amount,
                 processor_direction, seller_direction_snapshot, currency, processor_reference,
                 source_locator, review_note, evidence_artifact_id, reviewed_at, created_at)
            VALUES (:id, :seller, :case, :line, :processor, :user, 'matched', 100, 100,
                    'increase', 'increase', 'KES', 'PROC-1', 'processor-row:1',
                    'Matched in CI isolation fixture', :artifact, now(), now())
        """), {"id": uuid4(), "seller": seller_org, "case": case_id, "line": line_id,
               "processor": processor_org, "user": processor_user, "artifact": artifact_id})

        become(seller_user)
        assert connection.scalar(text("SELECT count(*) FROM public.receivable_cases WHERE id = :id"), {"id": case_id}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.counterparty_line_reviews WHERE case_id = :id"), {"id": case_id}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.evidence_artifacts WHERE id = :id"), {"id": artifact_id}) == 1

        become(outsider_user)
        for table in ("receivable_cases", "receivable_case_lines", "counterparty_case_evidence", "counterparty_line_reviews", "evidence_artifacts"):
            filter_column = "case_id" if table in {
                "receivable_case_lines", "counterparty_case_evidence", "counterparty_line_reviews",
            } else "id"
            row_id = case_id if filter_column == "case_id" else artifact_id if table == "evidence_artifacts" else case_id
            visible = connection.scalar(
                text(f"SELECT count(*) FROM public.{table} WHERE {filter_column} = :id"),
                {"id": row_id},
            )
            assert visible == 0, f"unrelated organization can read {table}"
        assert connection.scalar(text("SELECT count(*) FROM public.client_write_receipts WHERE id = :id"), {"id": receipt_id}) == 0, "unrelated user saw another user's offline write receipt"
        try:
            with connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO public.client_write_receipts
                        (id, actor_user_id, idempotency_key, request_hash, response_json, created_at)
                    VALUES (:id, :actor, :key, repeat('c', 64), '{}'::json, now())
                """), {"id": uuid4(), "actor": seller_user, "key": f"ci-{uuid4()}"})
        except DBAPIError:
            pass
        else:
            raise AssertionError("unrelated user inserted an offline receipt for another user")
        try:
            with connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO public.counterparty_line_reviews
                        (id, organization_id, case_id, case_line_id, counterparty_organization_id,
                         reviewed_by_user_id, review_status, seller_amount_snapshot, processor_amount,
                         processor_direction, seller_direction_snapshot, currency, reviewed_at, created_at)
                    VALUES (:id, :seller, :case, :line, :processor, :user, 'matched', 100, 100,
                            'increase', 'increase', 'KES', now(), now())
                """), {"id": uuid4(), "seller": seller_org, "case": case_id, "line": line_id,
                       "processor": processor_org, "user": outsider_user})
        except DBAPIError:
            pass
        else:
            raise AssertionError("unrelated organization inserted a processor line review")

    engine.dispose()
    print("RLS passed: bilateral receivables sharing works; unrelated organizations and users are denied.")


if __name__ == "__main__":
    main()
