CREATE TABLE pole_models (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    sha256 text NOT NULL,
    labels jsonb NOT NULL DEFAULT '{}',
    added_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE module_runs ADD COLUMN pole_model uuid REFERENCES pole_models(id);
