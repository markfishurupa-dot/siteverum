ALTER TABLE point_corrections ADD COLUMN bearing double precision CHECK (bearing >= 0 AND bearing < 360);
ALTER TABLE point_corrections ADD COLUMN deleted boolean NOT NULL DEFAULT false;
