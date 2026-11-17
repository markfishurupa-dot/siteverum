ALTER TABLE surveys ADD COLUMN publicly_available boolean NOT NULL DEFAULT false;
ALTER TABLE surveys ADD COLUMN default_basemap text NOT NULL DEFAULT 'survey'
    CHECK (default_basemap IN ('survey', 'osm'));
