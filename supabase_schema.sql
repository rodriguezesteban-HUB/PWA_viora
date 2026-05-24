CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  streak INT DEFAULT 0,
  total_tasks INT DEFAULT 0,
  total_recovered NUMERIC(10, 2) DEFAULT 0.00,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_users (
  email VARCHAR(255) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE auth_users ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON auth_users FROM anon, authenticated;
GRANT ALL ON auth_users TO service_role;

CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
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
  done BOOLEAN DEFAULT FALSE,
  requires_photo BOOLEAN DEFAULT FALSE,
  verified BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS habit_routines (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  icon VARCHAR(10) DEFAULT '🔥',
  streak INT DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS habit_routine_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  habit_id UUID NOT NULL REFERENCES habit_routines(id) ON DELETE CASCADE,
  log_date DATE NOT NULL DEFAULT CURRENT_DATE,
  done BOOLEAN DEFAULT FALSE,
  UNIQUE (habit_id, log_date)
);

CREATE TABLE IF NOT EXISTS finances (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  type VARCHAR(20) CHECK (type IN ('income', 'expense')) NOT NULL,
  amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
  transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bets (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  active BOOLEAN DEFAULT TRUE,
  amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 1000),
  bet_date DATE NOT NULL DEFAULT CURRENT_DATE,
  completed BOOLEAN DEFAULT FALSE,
  refunded BOOLEAN DEFAULT FALSE,
  transaction_ref VARCHAR(100),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP WITH TIME ZONE,
  cancelled_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS community_posts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cat VARCHAR(50) DEFAULT 'general',
  text VARCHAR(500) NOT NULL,
  votes INT DEFAULT 0,
  comments_count INT DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS community_comments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  post_id UUID NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text VARCHAR(300) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users (id, name, email)
VALUES ('11111111-1111-1111-1111-111111111111', 'Usuario Prueba', 'test@viora.app')
ON CONFLICT DO NOTHING;
