
CREATE TABLE modules (
    module_id text NOT NULL, version text NOT NULL, manifest jsonb NOT NULL,
    sha256 text NOT NULL, enabled boolean NOT NULL DEFAULT true, installed timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (module_id, version)
);
CREATE TABLE module_runs (
    id uuid PRIMARY KEY, module_id text NOT NULL, version text NOT NULL,
    survey uuid NOT NULL REFERENCES surveys(id), source_job uuid NOT NULL REFERENCES jobs(id),
    configuration jsonb NOT NULL, fingerprint text NOT NULL,
    state text NOT NULL CHECK (state IN ('queued','running','completed','failed','cancelled')),
    progress integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    created timestamptz NOT NULL DEFAULT now(), started timestamptz, finished timestamptz,
    error text, summary jsonb, requested_key text,
    FOREIGN KEY (module_id, version) REFERENCES modules(module_id, version),
    UNIQUE (survey, module_id, requested_key)
);
CREATE UNIQUE INDEX module_active_fingerprint ON module_runs (fingerprint) WHERE state IN ('queued','running');
CREATE INDEX module_runs_survey ON module_runs (survey, created DESC);
CREATE INDEX module_runs_queue ON module_runs (created) WHERE state='queued';
CREATE TABLE module_artifacts (
    run uuid NOT NULL REFERENCES module_runs(id), path text NOT NULL, category text NOT NULL,
    sha256 text NOT NULL, bytes bigint NOT NULL,
    PRIMARY KEY (run,path)
);
CREATE TABLE module_features (
    id uuid PRIMARY KEY, run uuid NOT NULL REFERENCES module_runs(id), layer text NOT NULL,
    source_id text NOT NULL, original geometry(Geometry,4326) NOT NULL,
    estimated geometry(Geometry,4326) NOT NULL, reviewed geometry(Geometry,4326),
    properties jsonb NOT NULL, review_state text NOT NULL DEFAULT 'pending'
        CHECK (review_state IN ('pending','approved','rejected')),
    updated timestamptz, UNIQUE(run,layer,source_id)
);
CREATE INDEX module_features_geom ON module_features USING gist (estimated);
CREATE TABLE module_evidence (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    feature uuid NOT NULL REFERENCES module_features(id), sequence integer NOT NULL,
    bbox jsonb NOT NULL, details jsonb NOT NULL
);
CREATE INDEX module_evidence_feature ON module_evidence (feature);
CREATE TABLE module_feature_reviews (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, feature uuid NOT NULL REFERENCES module_features(id),
    state text NOT NULL, geometry geometry(Geometry,4326), created timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE module_derivatives (
    run uuid NOT NULL REFERENCES module_runs(id), sequence integer NOT NULL, path text NOT NULL,
    metadata jsonb NOT NULL, PRIMARY KEY (run,sequence),
    FOREIGN KEY (run,path) REFERENCES module_artifacts(run,path)
);
ALTER TABLE surveys ADD COLUMN privacy_module text,
    ADD COLUMN published_derivative_run uuid REFERENCES module_runs(id);
CREATE TABLE published_module_layers (
    survey uuid NOT NULL REFERENCES surveys(id), run uuid NOT NULL REFERENCES module_runs(id),
    layer text NOT NULL, collection jsonb NOT NULL, PRIMARY KEY (survey,run,layer)
);
