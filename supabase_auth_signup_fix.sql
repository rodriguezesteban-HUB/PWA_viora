-- Fix for Supabase Auth error:
-- "Database error saving new user"
--
-- Viora does not need an auth.users trigger to create public.users.
-- The Flask backend creates/loads public.users after validating the
-- Supabase Auth access token. If an old trigger exists on auth.users
-- and fails, Supabase Auth cannot finish signup.

-- 1) Inspect non-internal triggers attached to auth.users.
select
  trigger_name,
  event_manipulation,
  action_statement
from information_schema.triggers
where event_object_schema = 'auth'
  and event_object_table = 'users';

-- 2) Remove common profile/user creation triggers if they exist.
drop trigger if exists on_auth_user_created on auth.users;
drop trigger if exists handle_new_user on auth.users;
drop trigger if exists create_profile_on_signup on auth.users;

-- 3) Remove common trigger functions if they exist.
drop function if exists public.handle_new_user();
drop function if exists public.create_profile_for_user();
drop function if exists public.create_user_profile();

-- 4) Make public.users tolerant if any remaining process inserts id/email only.
alter table public.users
  alter column name set default 'Usuario';

-- 5) Keep email unique, but make sure the table shape matches Viora.
alter table public.users
  alter column email set not null,
  alter column name set not null;

-- 6) Create the fallback email/password table used by /api/auth/email/register.
-- This is only for Viora's backend fallback path. Do not expose password hashes
-- to browser clients; SUPABASE_KEY in the backend should be the service_role key,
-- while SUPABASE_ANON_KEY / SUPABASE_PUBLISHABLE_KEY is the public browser key.
create table if not exists public.auth_users (
  email varchar(255) primary key,
  name varchar(255) not null,
  password_hash text not null,
  created_at timestamp with time zone default current_timestamp
);

alter table public.auth_users enable row level security;
revoke all on public.auth_users from anon, authenticated;
grant all on public.auth_users to service_role;
