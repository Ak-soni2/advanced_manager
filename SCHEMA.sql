-- ================================================================
-- Rimo Task Manager — Supabase Schema
-- ================================================================

-- 1. Users Table (Maps to Login System)
CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username      TEXT UNIQUE NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('manager','developer')),
  password_hash TEXT NOT NULL,
  github_handle TEXT,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- 2. Meetings Table (Stores Transcripts)
CREATE TABLE IF NOT EXISTS meetings (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title       TEXT NOT NULL,
  transcript  TEXT NOT NULL,
  uploaded_by UUID REFERENCES users(id),
  attendees   JSONB, -- Stores list of unique meeting participants
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- 3. Tasks Table (Core Entity)
CREATE TABLE IF NOT EXISTS tasks (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id      UUID REFERENCES meetings(id) ON DELETE CASCADE,
  description     TEXT NOT NULL,
  raw_assignee    TEXT, -- AI suggested name from transcript
  assigned_to     UUID REFERENCES users(id), -- Linked user
  assignees_list  JSONB DEFAULT '[]'::jsonb, -- Support for multi-assignees
  confidence      INT DEFAULT 0 CHECK (confidence BETWEEN 0 AND 100),
  status          TEXT DEFAULT 'pending_review'
                  CHECK (status IN (
                    'pending_review','confirmed','in_progress','done', 'rejected'
                  )),
  priority        TEXT DEFAULT 'medium'
                  CHECK (priority IN ('high','medium','low')),
  deadline        TEXT, -- Stored as text for flexibility (formatted as YYYY-MM-DD)
  manager_notes   TEXT, -- Threaded chat history (Manager)
  dev_notes       TEXT, -- Threaded chat history (Developer)
  github_issue_url TEXT, -- Link to synced GitHub issue
  reasoning       TEXT, -- AI generated logic for why this is a task
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

-- 4. Seed Demo Data
-- Default passwords: manager123 (mngr) and dev123 (devs)
-- Logic matches encode(sha256('password'), 'hex')
INSERT INTO users (username, role, password_hash) VALUES
  ('manager1', 'manager',   encode(sha256('manager123'::bytea), 'hex')),
  ('akshay',   'developer', encode(sha256('dev123'::bytea),     'hex')),
  ('priya',    'developer', encode(sha256('dev123'::bytea),     'hex')),
  ('rahul',    'developer', encode(sha256('dev123'::bytea),     'hex'))
ON CONFLICT (username) DO NOTHING;

-- 5. Helper Views / Functions (Optional but useful)
-- Example: Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tasks_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW
EXECUTE PROCEDURE update_updated_at_column();
