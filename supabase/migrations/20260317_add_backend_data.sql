-- Add backend_data column to saved_analyses to persist structured AI/backend results
ALTER TABLE saved_analyses
  ADD COLUMN IF NOT EXISTS backend_data jsonb;
