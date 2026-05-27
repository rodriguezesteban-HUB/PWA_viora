-- Adds the columns used by the current habits UI, including weekly schedule.
-- Run this in Supabase SQL editor for existing projects.

ALTER TABLE habit_routines
  ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'habitos',
  ADD COLUMN IF NOT EXISTS period VARCHAR(50) DEFAULT 'diaria',
  ADD COLUMN IF NOT EXISTS target NUMERIC DEFAULT 1,
  ADD COLUMN IF NOT EXISTS current NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS unit VARCHAR(20) DEFAULT 'veces',
  ADD COLUMN IF NOT EXISTS done BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS requires_photo BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS week JSONB;

UPDATE habit_routines
SET
  category = COALESCE(category, 'habitos'),
  period = COALESCE(period, 'diaria'),
  target = COALESCE(target, 1),
  current = COALESCE(current, 0),
  unit = COALESCE(unit, 'veces'),
  done = COALESCE(done, FALSE),
  requires_photo = COALESCE(requires_photo, FALSE),
  verified = COALESCE(verified, FALSE);
