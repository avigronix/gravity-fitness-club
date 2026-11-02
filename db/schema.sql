-- =====================================================================
-- Gravity Fitness Club - Admin Panel
-- Database schema for PostgreSQL 16
--
-- Run once (from project root):
--   psql -U postgres -d gym_admin -f db/schema.sql
-- Safe to run again: uses IF NOT EXISTS / ON CONFLICT.
-- =====================================================================

SET timezone = 'Asia/Kolkata';

-- ---------- Admin users (gym owner / front desk) ----------
CREATE TABLE IF NOT EXISTS admins (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(200) NOT NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ---------- Membership packages & prices ----------
CREATE TABLE IF NOT EXISTS packages (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(30) NOT NULL UNIQUE,
    months     INT         NOT NULL CHECK (months > 0),
    price      INT         NOT NULL CHECK (price >= 0),
    sort_order INT         NOT NULL DEFAULT 0
);

INSERT INTO packages (name, months, price, sort_order) VALUES
    ('1 Month',  1,  1000, 1),
    ('3 Months', 3,  2500, 2),
    ('6 Months', 6,  4500, 3),
    ('1 Year',   12, 7500, 4)
ON CONFLICT (name) DO NOTHING;

-- ---------- Members (one row per person, holds CURRENT package) ----------
CREATE TABLE IF NOT EXISTS members (
    id               SERIAL PRIMARY KEY,
    membership_no    VARCHAR(12) GENERATED ALWAYS AS ('GFC-' || lpad(id::text, 4, '0')) STORED,

    -- personal
    first_name       VARCHAR(60)  NOT NULL,
    last_name        VARCHAR(60),
    guardian_name    VARCHAR(100),                 -- S/O, D/O, W/O
    sex              CHAR(1)      NOT NULL CHECK (sex IN ('M', 'F')),
    age              INT,
    mobile           VARCHAR(10)  NOT NULL,        -- 10 digits, used for WhatsApp
    email            VARCHAR(120),
    aadhaar_no       VARCHAR(12),
    address          TEXT,
    photo            VARCHAR(200),                 -- file name inside static/uploads/

    -- body & goal
    weight_kg        NUMERIC(5,1),
    height           VARCHAR(10),                  -- e.g. 5.11
    food_type        VARCHAR(20),                  -- Veg / Non-veg / Eggetarian
    objective        VARCHAR(30),                  -- Fat loss / Muscle gain / ...

    -- medical
    sugar            BOOLEAN      NOT NULL DEFAULT FALSE,
    blood_pressure   VARCHAR(10)  NOT NULL DEFAULT 'No',   -- No / High / Low
    disease          TEXT,

    -- current package
    package_id       INT          NOT NULL REFERENCES packages(id),
    start_date       DATE         NOT NULL,
    end_date         DATE         NOT NULL,
    fee              INT          NOT NULL,

    last_reminder_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_members_end_date ON members (end_date);
CREATE INDEX IF NOT EXISTS idx_members_mobile   ON members (mobile);

-- ---------- Payments (every registration / renewal adds one row) ----------
CREATE TABLE IF NOT EXISTS payments (
    id           SERIAL PRIMARY KEY,
    member_id    INT         NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    package_id   INT         NOT NULL REFERENCES packages(id),
    amount       INT         NOT NULL CHECK (amount >= 0),
    mode         VARCHAR(10) NOT NULL DEFAULT 'Cash' CHECK (mode IN ('Cash', 'UPI', 'Card')),
    period_start DATE        NOT NULL,
    period_end   DATE        NOT NULL,
    paid_on      DATE        NOT NULL DEFAULT CURRENT_DATE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payments_paid_on   ON payments (paid_on);
CREATE INDEX IF NOT EXISTS idx_payments_member_id ON payments (member_id);

-- First admin login is created automatically by the app on startup
-- from ADMIN_USERNAME / ADMIN_PASSWORD in .env (password is bcrypt-hashed).
