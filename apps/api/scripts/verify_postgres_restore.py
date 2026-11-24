"""Dump and restore the ephemeral CI database to a fresh database in the same cluster."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


TABLES = ("organizations", "receivable_cases", "counterparty_line_reviews", "evidence_artifacts")


def main() -> None:
    source = make_url(os.environ["DATABASE_URL"])
    if source.get_backend_name() != "postgresql":
        raise SystemExit("Restore verification requires the ephemeral PostgreSQL/PostGIS CI database")
    if not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        raise SystemExit("Install PostgreSQL client tools before running restore verification")

    database_name = source.database
    restore_name = f"tv_restore_{uuid4().hex[:12]}"
    source_url = source.set(drivername="postgresql+psycopg")
    admin_url = source_url.set(database="postgres")
    restore_url = source_url.set(database=restore_name)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    source_engine = create_engine(source_url)
    restored_engine = None
    try:
        with source_engine.connect() as connection:
            before = {table: connection.scalar(text(f"SELECT count(*) FROM public.{table}")) for table in TABLES}
            version_before = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            postgis_before = connection.scalar(text("SELECT PostGIS_Version()"))

        quoted_restore = '"' + restore_name.replace('"', '""') + '"'
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_restore} TEMPLATE template0")

        cli_env = os.environ.copy()
        if source.password is not None:
            cli_env["PGPASSWORD"] = source.password
        cli_env["PGHOST"] = source.host or "localhost"
        cli_env["PGPORT"] = str(source.port or 5432)
        cli_env["PGUSER"] = source.username or "postgres"
        with tempfile.TemporaryDirectory(prefix="terravanta-db-restore-") as temp_dir:
            dump_path = Path(temp_dir) / "terravanta-ci.dump"
            subprocess.run(
                ["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--file", str(dump_path), "--dbname", database_name or "terravanta"],
                env=cli_env, check=True, stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                ["pg_restore", "--exit-on-error", "--no-owner", "--no-acl", "--dbname", restore_name, str(dump_path)],
                env=cli_env, check=True, stdout=subprocess.DEVNULL,
            )

        restored_engine = create_engine(restore_url)
        with restored_engine.connect() as connection:
            after = {table: connection.scalar(text(f"SELECT count(*) FROM public.{table}")) for table in TABLES}
            version_after = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            postgis_after = connection.scalar(text("SELECT PostGIS_Version()"))
        assert before == after, f"Restored table counts differ: before={before}, after={after}"
        assert version_before == version_after, "Restored Alembic version differs from source"
        assert postgis_before == postgis_after, "Restored PostGIS extension is unavailable or differs"
        print(f"PostgreSQL dump/restore verified: {restore_name}, Alembic {version_after}, PostGIS available")
    finally:
        if restored_engine is not None:
            restored_engine.dispose()
        source_engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS \"{restore_name}\" WITH (FORCE)")
        admin_engine.dispose()


if __name__ == "__main__":
    main()
