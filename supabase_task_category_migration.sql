ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'habitos';

UPDATE tasks
SET category = 'gym'
WHERE COALESCE(requires_photo, FALSE) = TRUE
  AND (category IS NULL OR category = 'habitos');

UPDATE tasks
SET category = 'habitos'
WHERE category IS NULL
  OR category NOT IN (
    'gym',
    'social',
    'habitos',
    'salud_mental',
    'salud',
    'procrastinacion',
    'estudio',
    'trabajo',
    'hogar'
  );

ALTER TABLE tasks
ALTER COLUMN category SET DEFAULT 'habitos';

ALTER TABLE tasks
DROP CONSTRAINT IF EXISTS tasks_category_check;

ALTER TABLE tasks
ADD CONSTRAINT tasks_category_check
CHECK (category IN (
  'gym',
  'social',
  'habitos',
  'salud_mental',
  'salud',
  'procrastinacion',
  'estudio',
  'trabajo',
  'hogar'
));

UPDATE tasks
SET requires_photo = (category = 'gym');
