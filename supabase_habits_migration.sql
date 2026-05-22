-- Move data from tasks -> habits and keep weekly habits in habit_routines
-- Safe to run once; review before applying in production.

-- 1) Ensure tasks has the columns we need to copy
ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS description TEXT,
  ADD COLUMN IF NOT EXISTS unit VARCHAR(20) DEFAULT 'veces',
  ADD COLUMN IF NOT EXISTS target NUMERIC DEFAULT 1,
  ADD COLUMN IF NOT EXISTS current NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS frequency VARCHAR(50);

-- 2) Rename existing weekly habits tables
ALTER TABLE IF EXISTS habit_logs RENAME TO habit_routine_logs;
ALTER TABLE IF EXISTS habits RENAME TO habit_routines;

-- 3) Create the new habits table with the tasks schema
CREATE TABLE IF NOT EXISTS habits (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  category VARCHAR(50) DEFAULT 'habitos' CHECK (category IN (
    'gym',
    'social',
    'habitos',
    'salud_mental',
    'salud',
    'procrastinacion',
    'estudio',
    'trabajo',
    'hogar'
  )),
  period VARCHAR(50) DEFAULT 'diaria',
  frequency VARCHAR(50),
  done BOOLEAN DEFAULT FALSE,
  requires_photo BOOLEAN DEFAULT FALSE,
  verified BOOLEAN DEFAULT FALSE,
  unit VARCHAR(20) DEFAULT 'veces',
  target NUMERIC DEFAULT 1,
  current NUMERIC DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4) Copy data from tasks -> habits
INSERT INTO habits (
  id,
  user_id,
  name,
  description,
  category,
  period,
  frequency,
  done,
  requires_photo,
  verified,
  unit,
  target,
  current,
  created_at
)
SELECT
  id,
  user_id,
  name,
  description,
  category,
  period,
  frequency,
  done,
  requires_photo,
  verified,
  unit,
  target,
  current,
  created_at
FROM tasks;

-- 5) Normalize requires_photo from category
UPDATE habits
SET requires_photo = (category = 'gym')
WHERE requires_photo IS DISTINCT FROM (category = 'gym');

-- 6) Optional: empty tasks after validating the copy
-- TRUNCATE TABLE tasks;
