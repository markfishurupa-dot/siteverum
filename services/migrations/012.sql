-- Disable historical browser-test fixtures without deleting their execution history.
UPDATE modules
SET enabled = false
WHERE module_id ~ '^browser-poles-[0-9a-f]{6}$'
  AND manifest->>'name' = 'Fixture poles'
  AND manifest->>'description' = 'Deterministic local test module';
