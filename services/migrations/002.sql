ALTER TABLE surveys ADD COLUMN slug text;
WITH names AS (
    SELECT id, COALESCE(NULLIF(trim(both '-' from regexp_replace(label, '[^A-Za-z0-9_-]+', '-', 'g')), ''), 'survey') AS name
    FROM surveys
), ranked AS (
    SELECT id, name, row_number() OVER (PARTITION BY lower(name) ORDER BY id) AS rank FROM names
)
UPDATE surveys SET slug = CASE
    WHEN rank > 1 OR lower(name) IN ('api', 'static', 'health')
    THEN name || '~' || surveys.id::text ELSE name END
FROM ranked WHERE surveys.id = ranked.id;
CREATE UNIQUE INDEX surveys_slug ON surveys (lower(slug));
