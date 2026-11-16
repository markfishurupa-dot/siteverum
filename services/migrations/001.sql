CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS surveys (
    id uuid PRIMARY KEY, label text NOT NULL, created timestamptz NOT NULL DEFAULT now(),
    validation jsonb, published boolean NOT NULL DEFAULT false, deleted boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS sources (
    survey uuid REFERENCES surveys(id), kind text NOT NULL, filename text NOT NULL,
    storage text NOT NULL, sha256 text NOT NULL, bytes bigint NOT NULL, PRIMARY KEY (survey, kind)
);
CREATE TABLE IF NOT EXISTS jobs (
    id uuid PRIMARY KEY, survey uuid REFERENCES surveys(id), fingerprint text NOT NULL,
    state text NOT NULL CHECK (state IN ('queued','running','completed','failed','cancelled')),
    settings jsonb NOT NULL, progress integer NOT NULL DEFAULT 0, error text, metadata jsonb,
    created timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs (state, created);
CREATE TABLE IF NOT EXISTS frames (
    job uuid REFERENCES jobs(id), sequence integer NOT NULL, geom geometry(Point,4326) NOT NULL,
    properties jsonb NOT NULL, PRIMARY KEY (job, sequence)
);
CREATE INDEX IF NOT EXISTS frames_geom ON frames USING gist (geom);
CREATE TABLE IF NOT EXISTS routes (job uuid PRIMARY KEY REFERENCES jobs(id), geom geometry(LineString,4326) NOT NULL);
CREATE INDEX IF NOT EXISTS routes_geom ON routes USING gist (geom);
CREATE TABLE IF NOT EXISTS artifacts (
    job uuid REFERENCES jobs(id), filename text NOT NULL, bytes bigint NOT NULL, PRIMARY KEY (job, filename)
);
