from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(SessionLocal, "after_begin")
def apply_rls_context(session, transaction, connection):
    """Reapply transaction-local tenant identity after every commit/rollback."""
    subject = session.info.get("terravanta.auth_subject")
    if subject and connection.dialect.name == "postgresql":
        connection.exec_driver_sql("SET LOCAL ROLE terravanta_app")
        connection.execute(
            text("SELECT set_config('terravanta.auth_subject', :subject, true)"),
            {"subject": subject},
        )
        internal_user_id = connection.execute(
            text("SELECT terravanta_private.resolve_auth_user(CAST(:subject AS uuid))"),
            {"subject": subject},
        ).scalar_one_or_none()
        session.info["terravanta.user_id"] = str(internal_user_id) if internal_user_id else None
        connection.execute(
            text("SELECT set_config('terravanta.user_id', :user_id, true)"),
            {"user_id": str(internal_user_id) if internal_user_id else ""},
        )
    elif subject:
        # Local SQLite development mirrors subject-as-user for new accounts and
        # reads the identity bridge table for legacy-account migration tests.
        internal_user_id = connection.execute(
            text("SELECT user_id FROM supabase_identity_links WHERE supabase_user_id = :subject"),
            {"subject": subject},
        ).scalar_one_or_none()
        session.info["terravanta.user_id"] = str(internal_user_id or subject)

# Schema migrations and trusted operator commands use the owner connection;
# request handlers use DATABASE_URL, which must be a non-owner RLS role.
admin_database_url = settings.migrations_database_url or settings.database_url
admin_connect_args = {"check_same_thread": False} if admin_database_url.startswith("sqlite") else {}
admin_engine = engine if admin_database_url == settings.database_url else create_engine(
    admin_database_url, connect_args=admin_connect_args, pool_pre_ping=True,
)
AdminSessionLocal = SessionLocal if admin_engine is engine else sessionmaker(
    bind=admin_engine, autoflush=False, expire_on_commit=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_admin_db():
    """Owner session reserved for migrations, local demo login and trusted operator actions."""
    db = AdminSessionLocal()
    try:
        yield db
    finally:
        db.close()
