"""Read-only retention inventory; this command never deletes evidence or rows."""

import os

from sqlalchemy import create_engine, text


def main() -> None:
    database_url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not database_url:
        raise SystemExit("Set MIGRATIONS_DATABASE_URL to an owner connection before running this read-only report")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE legal_hold) AS held,
                   count(*) FILTER (WHERE retention_basis = 'unreviewed') AS unreviewed,
                   count(*) FILTER (WHERE retention_until IS NOT NULL AND retention_until <= CURRENT_DATE) AS date_elapsed,
                   count(*) FILTER (WHERE NOT legal_hold AND retention_reviewed_at IS NOT NULL
                                      AND retention_basis <> 'unreviewed'
                                      AND retention_until IS NOT NULL AND retention_until <= CURRENT_DATE) AS reviewed_candidates
            FROM public.evidence_artifacts
        """)).mappings().one()
        print("Read-only evidence retention inventory (no files or rows changed)")
        for label, key in (("Artifacts", "total"), ("Legal holds", "held"), ("Policy unreviewed", "unreviewed"),
                           ("Retention dates elapsed", "date_elapsed"), ("Reviewed candidate count", "reviewed_candidates")):
            print(f"{label}: {result[key]}")
    engine.dispose()


if __name__ == "__main__":
    main()
