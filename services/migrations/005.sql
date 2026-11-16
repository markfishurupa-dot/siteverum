ALTER TABLE surveys ADD COLUMN source_revision bigint NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN source_revision bigint NOT NULL DEFAULT 0;
ALTER TABLE surveys ADD COLUMN published_job uuid REFERENCES jobs(id);
UPDATE surveys s SET published_job = (
    SELECT j.id FROM jobs j WHERE j.survey = s.id AND j.state = 'completed'
    ORDER BY j.created DESC, j.id DESC LIMIT 1
) WHERE s.published;
