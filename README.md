# Gravity Fitness Club – Admin Panel

FastAPI + PostgreSQL 16 + Jinja2 + HTMX + Tailwind (CDN). Works on phone and desktop.

## 1. Setup

You need Python 3.11+ and PostgreSQL 16 (already installed).

### Mac (Homebrew PostgreSQL)

Homebrew's PostgreSQL has **no `postgres` user** – your Mac login (e.g. `rdxvinay`) is the database
superuser, so leave out `-U postgres` everywhere.

```bash
cd gravity-fitness-club

# database + tables
createdb gym_admin
psql -d gym_admin -f db/schema.sql

# python env
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# config
cp .env.example .env
#   DATABASE_URL=postgresql://<your-mac-user>@localhost:5432/gym_admin   (no password needed)
#   SECRET_KEY=<paste output of: python -c "import secrets; print(secrets.token_hex(32))">

# run
python -m uvicorn main:app --reload
```

### Windows (PostgreSQL installer)

```bat
cd gravity-fitness-club

createdb -U postgres gym_admin
psql -U postgres -d gym_admin -f db/schema.sql

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
rem   DATABASE_URL=postgresql://postgres:<your-pg-password>@localhost:5432/gym_admin
rem   SECRET_KEY=<paste output of: python -c "import secrets; print(secrets.token_hex(32))">

python -m uvicorn main:app --reload
```

Open http://127.0.0.1:8000 and log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`
(default `admin` / `ChangeMe@123`). The first admin is created automatically on startup.

Use `python -m uvicorn` (not plain `uvicorn`) so the venv's uvicorn always runs.

**On your phone (same Wi-Fi):** `python -m uvicorn main:app --reload --host 0.0.0.0`, then open
`http://<PC-IP>:8000` (Mac: `ipconfig getifaddr en0`, Windows: `ipconfig`). In Chrome/Safari use
"Add to Home Screen" – it then opens full-screen like an app.

## 2. Demo data (optional)

30 realistic members (4 due soon, 4 expired, 22 active, payment history, this month's collection).
All dates are relative to today. **Every demo member gets the one mobile number you pass** – use your
own, so a WhatsApp test never messages a stranger. Runs only when the members table is empty.

```bash
psql -d gym_admin -v demo_mobile=9XXXXXXXXX -f db/seed_demo.sql              # Mac
psql -U postgres -d gym_admin -v demo_mobile=9XXXXXXXXX -f db/seed_demo.sql  # Windows
```

Change the test number later (all members):

```bash
psql -d gym_admin -c "UPDATE members SET mobile = '9XXXXXXXXX'"
```

## 3. Testing (what to check by hand)

1. Open `/` without logging in → you land on `/login`. Wrong password → red error; 5 wrong tries → blocked 10 minutes.
2. **New Registration**: 1 Month from 31 Oct shows end date 30 Nov; save → member page with one payment row.
3. **All Members**: search by name / full name / mobile / GFC-0001 / 1, filter chips, pages; refresh and Back keep the view.
4. **Payment Reminders**: Due / Expired tabs, "Send on WhatsApp" opens WhatsApp and the button turns grey "Sent · Resend";
   "Mark paid" → renew → back on the same tab, row gone, badge count lower.
5. **Dashboard** numbers = the "Count by status" and "Collection this month" queries in `db/common_queries.sql`.
6. Phone: bottom tab bar, red + button, cards instead of tables, renew bottom sheet.

## 4. Go-live checklist

- [ ] **Clear demo data** – in psql run the "CLEAR ALL MEMBER DATA BEFORE GO-LIVE" line from
      `db/common_queries.sql` (`TRUNCATE payments, members RESTART IDENTITY CASCADE;`). Admins and package
      prices stay; the first real member becomes GFC-0001. Empty `static/uploads/` (keep `.gitkeep`).
- [ ] **Change the admin password** – sidebar → *Change password* (phone: *More* → *Change password*).
- [ ] **`.env`** – a long random `SECRET_KEY` (the app warns on startup if it is still `change-me`),
      and `COOKIE_SECURE=true` once the site runs on https.
- [ ] **Daily backup** (keep ~30 days), e.g. cron on the server:
      `0 2 * * * pg_dump -d gym_admin -F c -f /backups/gym_$(date +\%F).dump`
      (Windows: Task Scheduler with `pg_dump -U postgres -d gym_admin -F c -f D:\backups\gym.dump`).
      Back up `static/uploads/` (member photos) too.
- [ ] Check package prices: `SELECT name, price FROM packages;` (change with the queries in `db/common_queries.sql`).

## 5. Files

```
main.py              FastAPI app + all routes
db.py                connection pool (Asia/Kolkata on every connection) + query helpers
utils.py             passwords, login limit, dates, end-date rule, money, WhatsApp messages
templates/           base, login, dashboard, register, members, member, reminders, password, error
templates/partials/  members_list, reminder_list (HTMX swaps), member_form, mobile_check, ui (icons/macros)
static/app.js        end-date preview, renew confirm, reminder "sent" logging, sheets
static/uploads/      member photos (<member id>.jpg/png/webp)
db/schema.sql        tables + packages (do not change)
db/common_queries.sql  everyday SQL: status, reminders, renew, collection, clear data, backup
db/seed_demo.sql     demo data
docs/                requirements, UI guide, SRS, UI preview (local only, not in git)
```

`.gitignore` keeps `.env`, `venv/`, member photos, `docs/`, `PROMPT.md`, tests and backups out of git.
After cloning: create `.env` from `.env.example` and `venv` as in step 1 – nothing else is needed to run.
