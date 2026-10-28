-- For a db volume created before detected_at was added to db/init/01_schema.sql.
-- Apply once: docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < db/migrations/001_analysis_results_detected_at.sql
ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS detected_at timestamp(3);
