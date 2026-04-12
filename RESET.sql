-- ================================================================
-- Rimo Task Manager — FULL RESET SCRIPT
-- WARNING: This will delete ALL data (Users, Tasks, Meetings)!
-- ================================================================

-- 1. Delete all data (Order matters for Foreign Keys)
TRUNCATE TABLE tasks CASCADE;
TRUNCATE TABLE meetings CASCADE;
TRUNCATE TABLE users CASCADE;

-- 2. Optional: Reset ID sequences (if using serials, though we use UUIDs)

-- 3. Re-insert the default Manager account
-- Username: manager1
-- Password: manager123
INSERT INTO users (username, role, password_hash)
VALUES ('manager1', 'manager', encode(sha256('manager123'::bytea), 'hex'));

-- 4. Re-insert baseline developers for testing (Optional)
INSERT INTO users (username, role, password_hash) VALUES
  ('akshay', 'developer', encode(sha256('dev123'::bytea), 'hex')),
  ('priya',  'developer', encode(sha256('dev123'::bytea), 'hex'));

-- Done! Your system is now clean for fresh testing.
