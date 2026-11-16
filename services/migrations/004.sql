ALTER TABLE jobs ADD COLUMN coordinate_edit jsonb;
CREATE TABLE point_corrections (
    survey uuid NOT NULL REFERENCES surveys(id),
    identity text NOT NULL,
    longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    PRIMARY KEY (survey, identity)
);
