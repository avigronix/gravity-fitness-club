-- =====================================================================
-- Gravity Fitness Club - Common SQL commands (PostgreSQL 16)
-- Open psql:   psql -d gym_admin                (Mac Homebrew: your own user)
--              psql -U postgres -d gym_admin    (Windows installer: postgres user)
-- Below, "-U postgres" is only needed on Windows - leave it out on Mac.
-- Run a file:  \i db/common_queries.sql   (or copy single queries)
-- Status rule used everywhere:
--   Active   = end_date >  today + 2
--   Due soon = end_date BETWEEN today AND today + 2
--   Expired  = end_date <  today
-- =====================================================================


-- ---------------------------------------------------------------------
-- 0. SETUP (run in terminal, not inside psql)
-- ---------------------------------------------------------------------
-- Mac:      createdb gym_admin
--           psql -d gym_admin -f db/schema.sql
-- Windows:  createdb -U postgres gym_admin
--           psql -U postgres -d gym_admin -f db/schema.sql
-- Demo data (empty DB only, use YOUR mobile):
--           psql -d gym_admin -v demo_mobile=9XXXXXXXXX -f db/seed_demo.sql
-- Drop & recreate (DELETES ALL DATA):
--   Mac:     dropdb gym_admin && createdb gym_admin
--   Windows: dropdb -U postgres gym_admin && createdb -U postgres gym_admin


-- ---------------------------------------------------------------------
-- 1. QUICK CHECKS (psql meta commands)
-- ---------------------------------------------------------------------
-- \l              list databases
-- \c gym_admin    connect to database
-- \dt             list tables
-- \d members      show table structure
-- \q              quit


-- ---------------------------------------------------------------------
-- 2. PACKAGES
-- ---------------------------------------------------------------------
SELECT id, name, months, price FROM packages ORDER BY sort_order;

-- Change a price
UPDATE packages SET price = 1200 WHERE name = '1 Month';

-- Add a new package
INSERT INTO packages (name, months, price, sort_order) VALUES ('2 Months', 2, 1800, 5);


-- ---------------------------------------------------------------------
-- 3. MEMBERS
-- ---------------------------------------------------------------------
-- All members, newest first
SELECT membership_no, first_name, last_name, mobile, start_date, end_date, fee
FROM members ORDER BY id DESC;

-- Search by name / mobile / membership no
SELECT membership_no, first_name, last_name, mobile, end_date
FROM members
WHERE first_name ILIKE '%vishal%'
   OR last_name  ILIKE '%vishal%'
   OR mobile LIKE '%7084%'
   OR membership_no ILIKE '%0012%';

-- One member with package name and status
SELECT m.membership_no, m.first_name, m.last_name, m.mobile, p.name AS package,
       m.start_date, m.end_date, m.fee,
       CASE
           WHEN m.end_date < CURRENT_DATE     THEN 'Expired'
           WHEN m.end_date <= CURRENT_DATE + 2 THEN 'Due soon'
           ELSE 'Active'
       END AS status
FROM members m JOIN packages p ON p.id = m.package_id
WHERE m.id = 1;

-- Count by status
SELECT
    COUNT(*) FILTER (WHERE end_date >  CURRENT_DATE + 2)                       AS active,
    COUNT(*) FILTER (WHERE end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 2) AS due_soon,
    COUNT(*) FILTER (WHERE end_date <  CURRENT_DATE)                           AS expired,
    COUNT(*)                                                                   AS total
FROM members;

-- Page 2 of member list (20 per page)
SELECT membership_no, first_name, last_name, mobile, end_date
FROM members ORDER BY id DESC LIMIT 20 OFFSET 20;

-- Fix a wrong mobile number
UPDATE members SET mobile = '9876543210' WHERE id = 1;

-- Delete a member (also deletes their payments)
DELETE FROM members WHERE id = 1;


-- ---------------------------------------------------------------------
-- 4. FEE REMINDERS
-- ---------------------------------------------------------------------
-- Due in next 2 days (today, tomorrow, day after)
SELECT m.id, m.membership_no, m.first_name, m.last_name, m.mobile,
       p.name AS package, p.price AS renewal_fee, m.end_date, m.last_reminder_at
FROM members m JOIN packages p ON p.id = m.package_id
WHERE m.end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 2
ORDER BY m.end_date;

-- Expired / unpaid
SELECT m.id, m.membership_no, m.first_name, m.last_name, m.mobile,
       p.name AS package, p.price AS renewal_fee, m.end_date,
       CURRENT_DATE - m.end_date AS days_overdue
FROM members m JOIN packages p ON p.id = m.package_id
WHERE m.end_date < CURRENT_DATE
ORDER BY m.end_date DESC;

-- Mark reminder as sent
UPDATE members SET last_reminder_at = now() WHERE id = 1;


-- ---------------------------------------------------------------------
-- 5. RENEW / MARK PAID (manual, same thing the app does)
-- New period starts the day after old end_date (or today if already expired)
--
-- End date rule (same as end_date() in utils.py):
--   start + N months - 1 day        e.g. 1 Oct  + 1 month -> 31 Oct
--   but if that day does not exist in the target month, the package runs
--   till the last day of that month e.g. 31 Oct + 1 month -> 30 Nov
--                                        31 Jan + 1 month -> 28 Feb
-- PostgreSQL clamps 31 Oct + 1 month to 30 Nov by itself; when that clamp
-- happens (day of month got smaller) we keep it, otherwise subtract 1 day.
-- ---------------------------------------------------------------------
BEGIN;
WITH m AS (
    SELECT id, GREATEST(end_date + 1, CURRENT_DATE) AS new_start
    FROM members WHERE id = 1
), p AS (
    SELECT id, months, price FROM packages WHERE name = '1 Month'
), d AS (
    SELECT m.id AS member_id, m.new_start,
           (m.new_start + make_interval(months => p.months))::date AS plus_months
    FROM m, p
)
INSERT INTO payments (member_id, package_id, amount, mode, period_start, period_end)
SELECT d.member_id, p.id, p.price, 'Cash', d.new_start,
       CASE WHEN extract(day FROM d.plus_months) < extract(day FROM d.new_start)
            THEN d.plus_months          -- month-end clamp: run till last day
            ELSE d.plus_months - 1      -- normal: day before same date
       END
FROM d, p;

UPDATE members mb
SET package_id = pay.package_id, start_date = pay.period_start,
    end_date = pay.period_end, fee = pay.amount, last_reminder_at = NULL
FROM (SELECT * FROM payments WHERE member_id = 1 ORDER BY id DESC LIMIT 1) pay
WHERE mb.id = 1;
COMMIT;


-- ---------------------------------------------------------------------
-- 6. PAYMENTS & COLLECTION
-- ---------------------------------------------------------------------
-- Payment history of one member
SELECT paid_on, amount, mode, period_start, period_end
FROM payments WHERE member_id = 1 ORDER BY paid_on DESC;

-- Collection this month
SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS payments
FROM payments
WHERE paid_on >= date_trunc('month', CURRENT_DATE);

-- Month-wise collection (last 12 months)
SELECT to_char(date_trunc('month', paid_on), 'Mon YYYY') AS month,
       SUM(amount) AS total, COUNT(*) AS payments
FROM payments
WHERE paid_on >= date_trunc('month', CURRENT_DATE) - INTERVAL '11 months'
GROUP BY date_trunc('month', paid_on)
ORDER BY date_trunc('month', paid_on);

-- Today's collection by mode
SELECT mode, SUM(amount) FROM payments WHERE paid_on = CURRENT_DATE GROUP BY mode;

-- New joins this month
SELECT COUNT(*) FROM members WHERE created_at >= date_trunc('month', CURRENT_DATE);


-- ---------------------------------------------------------------------
-- 7. ADMINS
-- ---------------------------------------------------------------------
SELECT id, name, username, is_active, created_at FROM admins;

-- Block / unblock a staff login
UPDATE admins SET is_active = FALSE WHERE username = 'staff1';

-- Reset password: generate a bcrypt hash first, then update
--   python -c "import bcrypt; print(bcrypt.hashpw(b'NewPass@123', bcrypt.gensalt()).decode())"
UPDATE admins SET password_hash = '<paste-hash-here>' WHERE username = 'admin';


-- ---------------------------------------------------------------------
-- 8. CLEAR ALL MEMBER DATA BEFORE GO-LIVE  (DELETES every member + payment!)
-- Removes demo / test data. Admin logins and package prices stay.
-- RESTART IDENTITY -> the first real member becomes GFC-0001 again.
-- Take a backup first if unsure (section 9). Photos: empty static/uploads/ by hand.
-- ---------------------------------------------------------------------
-- TRUNCATE payments, members RESTART IDENTITY CASCADE;


-- ---------------------------------------------------------------------
-- 9. BACKUP & RESTORE (run in terminal)
-- ---------------------------------------------------------------------
-- Backup:   Mac:     pg_dump -d gym_admin -F c -f backup_gym_$(date +%F).dump
--           Windows: pg_dump -U postgres -d gym_admin -F c -f backup_gym_%DATE%.dump
-- Restore:  Mac:     pg_restore -d gym_admin --clean backup_gym_2026-11-01.dump
--           Windows: pg_restore -U postgres -d gym_admin --clean backup_gym_2026-11-01.dump
-- Plain SQL backup:  pg_dump -d gym_admin > backup.sql   (Windows: add -U postgres)
