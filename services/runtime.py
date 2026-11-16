import os
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

ROOT = Path(os.environ.get("SV_MEDIA", "private-samples/runtime")).resolve()
MIGRATIONS = Path(__file__).with_name("migrations")


def connect():
    return psycopg.connect("", row_factory=dict_row)


def migrate():
    ROOT.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(183001)")
        db.execute("CREATE TABLE IF NOT EXISTS migrations (version text PRIMARY KEY)")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if not db.execute("SELECT 1 FROM migrations WHERE version=%s", (path.name,)).fetchone():
                db.execute(path.read_text(encoding="utf-8"))
                db.execute("INSERT INTO migrations VALUES (%s)", (path.name,))


def run_path(survey: UUID, job: UUID):
    return ROOT / str(survey) / "runs" / str(job)
