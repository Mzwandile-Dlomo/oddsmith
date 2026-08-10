"""One-off migration: copy all Oddsmith data from the local DB into Supabase.

Usage (after pasting SUPABASE_DATABASE_URL into .env):
    uv run --active python scripts/migrate_to_supabase.py

Reads from MIGRATION_SOURCE_DATABASE_URL (default: local Docker Postgres) and
writes to SUPABASE_DATABASE_URL. Creates the schema on the target, then copies
every table. Idempotent: the target tables are cleared before copy so re-runs do
not duplicate rows. Non-destructive to the source.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, delete, select

from oddsmith.db import CachedFixture, HistoricalMatch, Slip, SlipLeg

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TABLES = [HistoricalMatch, Slip, SlipLeg, CachedFixture]


def _engine(url: str):
    return create_engine(url)


def main() -> int:
    source_url = os.environ.get("MIGRATION_SOURCE_DATABASE_URL")
    target_url = os.environ.get("SUPABASE_DATABASE_URL")
    if not source_url:
        print("ERROR: MIGRATION_SOURCE_DATABASE_URL is not set", file=sys.stderr)
        return 1
    if not target_url:
        print("ERROR: SUPABASE_DATABASE_URL is not set (paste it into .env)", file=sys.stderr)
        return 1

    source = _engine(source_url)
    target = _engine(target_url)

    print("Creating schema on target (Supabase)...")
    SQLModel.metadata.create_all(target)

    with Session(source) as src, Session(target) as dst:
        for table in TABLES:
            rows = list(src.exec(select(table)))
            dst.exec(delete(table))
            dst.commit()
            for row in rows:
                data = row.model_dump()
                dst.add(table(**data))
            dst.commit()
            copied = len(list(dst.exec(select(table))))
            print(f"  {table.__name__}: copied {len(rows)} -> target now has {copied}")

    # Rows were copied with explicit ids, so advance each id sequence past the
    # max copied id — otherwise the next INSERT collides on the primary key.
    with target.begin() as conn:
        for table in TABLES:
            tname = table.__tablename__
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{tname}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {tname}), 0) + 1, false)"
                )
            )
    print("Reset id sequences on target.")

    print("Migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
