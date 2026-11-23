
"""Apply the additive module migration to a populated baseline in isolated PostGIS."""
from pathlib import Path
import subprocess
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "streetview-v2-modules-dev-db-1"
DATABASE = "migration_check_" + uuid4().hex[:12]


def sql(db, statement):
    command = ["docker", "exec", "-i", CONTAINER, "psql", "-U", "streetview", "-d", db,
               "-v", "ON_ERROR_STOP=1", "-qAt"]
    return subprocess.run(command, input=statement, text=True, encoding="utf-8", check=True,
                          capture_output=True).stdout.strip()


def main():
    sql("postgres", f"CREATE DATABASE {DATABASE};")
    try:
        migrations = ROOT / "services/migrations"
        for version in range(1, 8):
            sql(DATABASE, (migrations / f"{version:03d}.sql").read_text())
        survey, job = uuid4(), uuid4()
        sql(DATABASE, f"""
            INSERT INTO surveys(id,label,slug,published,publicly_available)
                VALUES ('{survey}','Existing survey','existing-map',true,true);
            INSERT INTO jobs(id,survey,fingerprint,state,settings) VALUES ('{job}','{survey}','source-hash','completed','{{}}');
            UPDATE surveys SET published_job='{job}' WHERE id='{survey}';
            INSERT INTO frames(job,sequence,geom,properties) VALUES ('{job}',0,ST_SetSRID(ST_MakePoint(2,6),4326),
                '{{"image_path":"images/000000.jpg"}}');
            INSERT INTO artifacts(job,filename,bytes) VALUES ('{job}','survey.zip',360);
        """)
        unchanged = """
            SELECT s.id,s.slug,s.published,s.published_job,j.fingerprint,ST_AsText(f.geom),f.properties->>'image_path',a.bytes
            FROM surveys s JOIN jobs j ON j.id=s.published_job
            JOIN frames f ON f.job=j.id JOIN artifacts a ON a.job=j.id;
        """
        before = sql(DATABASE, unchanged)
        sql(DATABASE, (migrations / "008.sql").read_text())
        assert sql(DATABASE, unchanged) == before
        assert sql(DATABASE, "SELECT privacy_module IS NULL AND published_derivative_run IS NULL FROM surveys;") == "t"
        assert sql(DATABASE, "SELECT count(*) FROM modules;") == "0"
        print("Populated PostGIS migration retained survey, published run/slug, frame geometry, and artifact metadata")
    finally:
        sql("postgres", f"DROP DATABASE {DATABASE};")


if __name__ == "__main__":
    main()
