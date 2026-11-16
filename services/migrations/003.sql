ALTER TABLE sources ADD COLUMN recording text NOT NULL DEFAULT 'primary';
ALTER TABLE sources ADD COLUMN added_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE sources DROP CONSTRAINT sources_pkey;
ALTER TABLE sources ADD PRIMARY KEY (survey, recording, kind);
ALTER TABLE surveys ADD COLUMN map_layers text NOT NULL DEFAULT 'both'
    CHECK (map_layers IN ('both', 'route', 'points'));
ALTER TABLE routes ALTER COLUMN geom TYPE geometry(MultiLineString, 4326)
    USING ST_Multi(geom);
