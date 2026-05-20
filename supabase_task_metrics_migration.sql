-- Añadir soporte para metas y progreso en las tareas de Supabase
ALTER TABLE tasks 
ADD COLUMN IF NOT EXISTS target NUMERIC(10, 2) DEFAULT 1,
ADD COLUMN IF NOT EXISTS current NUMERIC(10, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS unit VARCHAR(50) DEFAULT 'veces';
