-- Simplify tasks table: add description and due_date, drop unused columns.
-- Safe to run once on existing databases.

-- 1) Add missing columns
ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS description TEXT,
  ADD COLUMN IF NOT EXISTS due_date DATE;

-- 2) Drop columns that are no longer used by the app
ALTER TABLE tasks
  DROP COLUMN IF EXISTS category,
  DROP COLUMN IF EXISTS period,
  DROP COLUMN IF EXISTS requires_photo,
  DROP COLUMN IF EXISTS verified,
  DROP COLUMN IF EXISTS unit,
  DROP COLUMN IF EXISTS target,
  DROP COLUMN IF EXISTS current,
  DROP COLUMN IF EXISTS frequency;
