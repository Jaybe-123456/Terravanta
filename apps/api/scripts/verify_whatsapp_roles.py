"""Check the production WhatsApp group-role boundary after Alembic migrations."""

import os

from sqlalchemy import create_engine, text


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        roles = connection.execute(text("""
            SELECT
                (SELECT rolcanlogin FROM pg_roles WHERE rolname = 'terravanta_webhook') AS webhook_can_login,
                (SELECT rolinherit FROM pg_roles WHERE rolname = 'terravanta_webhook') AS webhook_inherits,
                (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'terravanta_webhook') AS webhook_bypasses_rls,
                (SELECT rolcanlogin FROM pg_roles WHERE rolname = 'terravanta_worker') AS worker_can_login,
                (SELECT rolinherit FROM pg_roles WHERE rolname = 'terravanta_worker') AS worker_inherits,
                (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'terravanta_worker') AS worker_bypasses_rls,
                pg_has_role('terravanta_worker', 'terravanta_app', 'MEMBER') AS worker_has_app_role,
                pg_has_role('terravanta_webhook', 'terravanta_app', 'MEMBER') AS webhook_has_app_role,
                has_function_privilege(
                    'terravanta_worker',
                    'terravanta_private.claim_whatsapp_deliveries(integer)',
                    'EXECUTE'
                ) AS worker_can_claim,
                has_function_privilege(
                    'terravanta_app',
                    'terravanta_private.claim_whatsapp_deliveries(integer)',
                    'EXECUTE'
                ) AS app_can_claim,
                has_function_privilege(
                    'terravanta_webhook',
                    'terravanta_private.claim_whatsapp_deliveries(integer)',
                    'EXECUTE'
                ) AS webhook_can_claim,
                has_table_privilege(
                    'terravanta_webhook', 'public.whatsapp_preferences', 'SELECT'
                ) AS webhook_can_read_preferences,
                has_table_privilege(
                    'terravanta_webhook', 'public.farms', 'SELECT'
                ) AS webhook_can_read_farms,
                has_column_privilege(
                    'terravanta_webhook', 'public.veterinary_contact_requests', 'conversation_code', 'SELECT'
                ) AS webhook_can_read_request_code,
                has_column_privilege(
                    'terravanta_webhook', 'public.veterinary_contact_requests', 'message', 'SELECT'
                ) AS webhook_can_read_request_text
        """)).mappings().one()

    assert roles["webhook_can_login"] is False
    assert roles["webhook_inherits"] is True
    assert roles["webhook_bypasses_rls"] is False
    assert roles["worker_can_login"] is False
    assert roles["worker_inherits"] is True
    assert roles["worker_bypasses_rls"] is False
    assert roles["worker_has_app_role"] is True
    assert roles["webhook_has_app_role"] is False
    assert roles["worker_can_claim"] is True
    assert roles["app_can_claim"] is False
    assert roles["webhook_can_claim"] is False
    assert roles["webhook_can_read_preferences"] is True
    assert roles["webhook_can_read_farms"] is False
    assert roles["webhook_can_read_request_code"] is True
    assert roles["webhook_can_read_request_text"] is False

    engine.dispose()
    print("WhatsApp role check passed: worker queue functions and narrow webhook table/column grants")


if __name__ == "__main__":
    main()
