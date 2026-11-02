"""Small helpers: settings, passwords, login check, dates, money, status, WhatsApp."""
import calendar
import os
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import bcrypt
from dotenv import load_dotenv

load_dotenv()

GYM_NAME = os.getenv("GYM_NAME", "Gravity Fitness Club")
REMINDER_DAYS = int(os.getenv("REMINDER_DAYS", "2"))
RECENT_EXPIRED_DAYS = 30    # "Expired" tab + badge only count members who left in the last 30 days
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() in ("1", "true", "yes")
IST = ZoneInfo("Asia/Kolkata")

SESSION_HOURS = 12      # normal login
REMEMBER_DAYS = 30      # "Keep me signed in"


# ---------- passwords & login ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def start_session(session: dict, admin: dict, remember: bool) -> None:
    seconds = REMEMBER_DAYS * 86400 if remember else SESSION_HOURS * 3600
    session.clear()
    session.update(admin_id=admin["id"], admin_name=admin["name"],
                   expires=int(time.time()) + seconds)


def is_logged_in(session: dict) -> bool:
    return bool(session.get("admin_id")) and session.get("expires", 0) > time.time()


# Login rate limit: 5 wrong tries for the same username or IP -> blocked for 10 minutes.
# Kept in memory (resets when the app restarts) – enough for one small gym.
MAX_LOGIN_FAILS = 5
LOGIN_BLOCK_SECONDS = 600
_failed_logins: dict[str, list[float]] = {}


def _recent_fails(key: str) -> list[float]:
    cutoff = time.time() - LOGIN_BLOCK_SECONDS
    fails = [t for t in _failed_logins.get(key, []) if t > cutoff]
    _failed_logins[key] = fails
    return fails


def login_blocked_seconds(keys: list[str]) -> int:
    """Seconds left before these keys may try again (0 = not blocked)."""
    wait = 0
    for key in keys:
        fails = _recent_fails(key)
        if len(fails) >= MAX_LOGIN_FAILS:
            wait = max(wait, int(fails[-MAX_LOGIN_FAILS] + LOGIN_BLOCK_SECONDS - time.time()) + 1)
    return wait


def record_failed_login(keys: list[str]) -> None:
    for key in keys:
        _recent_fails(key).append(time.time())


def clear_failed_logins(keys: list[str]) -> None:
    for key in keys:
        _failed_logins.pop(key, None)


# ---------- dates ----------

def now() -> datetime:
    return datetime.now(IST)


def today() -> date:
    return now().date()


def end_date(start: date, months: int) -> date:
    """Last day of a package – the ONLY place this rule lives (register + renew use it).

    start + months - 1 day: 1 Oct + 1 month -> 31 Oct.
    If that date does not exist, run till month end: 31 Oct + 1 month -> 30 Nov.
    db/common_queries.sql (renew block) has the same rule in SQL.
    """
    m = start.month - 1 + months
    year, month = start.year + m // 12, m % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    if start.day > last_day:          # e.g. 31 Nov does not exist -> runs till 30 Nov
        return date(year, month, last_day)
    return date(year, month, start.day) - timedelta(days=1)


def renewal_start(old_end: date) -> date:
    """New period starts the day after the old one ends, or today if it already ended."""
    return max(old_end + timedelta(days=1), today())


def fmt_date(d) -> str:
    return d.strftime("%d %b %Y") if d else ""


def fmt_short(d) -> str:
    return d.strftime("%d %b") if d else ""


def fmt_long(d) -> str:
    return d.strftime("%A, %d %B %Y") if d else ""


def sent_label(sent_at) -> str:
    """last_reminder_at -> 'Sent today 10:42' / 'Sent yesterday' / 'Sent 3 days ago' / 'Not sent'."""
    if not sent_at:
        return "Not sent"
    local = sent_at.astimezone(IST)
    days = (today() - local.date()).days
    if days <= 0:
        return "Sent today " + local.strftime("%H:%M")
    return "Sent yesterday" if days == 1 else f"Sent {days} days ago"


def greeting() -> str:
    hour = now().hour
    if hour < 12:
        return "Good morning"
    return "Good afternoon" if hour < 17 else "Good evening"


def days_label(end: date) -> str:
    diff = (end - today()).days
    if diff == 0:
        return "Today"
    if diff == 1:
        return "Tomorrow"
    if diff > 1:
        return f"In {diff} days"
    if diff == -1:
        return "Yesterday"
    return f"{-diff} days ago"


# ---------- money & text ----------

def inr(amount) -> str:
    """68500 -> ₹68,500 ; 125000 -> ₹1,25,000 (Indian grouping)."""
    digits = str(int(amount or 0))
    head, tail = digits[:-3], digits[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return "₹" + (head + "," + tail if head else tail)


def inr_short(amount) -> str:
    """68500 -> ₹68.5k (small mobile cards)."""
    amount = int(amount or 0)
    if amount < 10000:
        return inr(amount)
    if amount < 100000:
        return f"₹{amount / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    return f"₹{amount / 100000:.2f}".rstrip("0").rstrip(".") + "L"


def mask_aadhaar(aadhaar) -> str:
    return f"XXXX XXXX {aadhaar[-4:]}" if aadhaar else ""


def initials(first: str, last: str | None = "") -> str:
    return ((first or "?")[:1] + (last or "")[:1]).upper()


def full_name(first: str, last: str | None = "") -> str:
    return f"{first} {last or ''}".strip()


# ---------- status ----------

STATUS_LABELS = {"active": "Active", "due": "Due soon", "expired": "Expired"}

# Same rule as db/common_queries.sql. Needs the named parameter %(days)s = REMINDER_DAYS.
STATUS_SQL = """CASE WHEN m.end_date < CURRENT_DATE THEN 'expired'
                     WHEN m.end_date <= CURRENT_DATE + %(days)s::int THEN 'due'
                     ELSE 'active' END"""

STATUS_WHERE = {
    "": "TRUE",
    "active": "m.end_date > CURRENT_DATE + %(days)s::int",
    "due": "m.end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + %(days)s::int",
    "expired": "m.end_date < CURRENT_DATE",
}


# ---------- WhatsApp ----------

def whatsapp_link(mobile: str, message: str) -> str:
    return f"https://wa.me/91{mobile[-10:]}?text={quote(message)}"


def reminder_message(name: str, package: str, end: date, fee, expired: bool) -> str:
    fee_text = inr(fee)[1:]
    if expired:
        return (f"Namaste {name} ji,\n"
                f"Gravity Fitness Club: aapka {package} package {fmt_date(end)} ko khatam ho chuka hai.\n"
                f"Renewal fee: Rs. {fee_text} baaki hai.\n"
                "Kripya jaldi fee jama karke membership continue karein. Dhanyavaad!")
    return (f"Namaste {name} ji,\n"
            f"Gravity Fitness Club se reminder: aapka {package} package {fmt_date(end)} ko khatam ho raha hai.\n"
            f"Renewal fee: Rs. {fee_text}\n"
            "Kripya samay par fee jama karein. Dhanyavaad!")


def reminder_text(row: dict) -> str:
    """row needs first_name, last_name, package, end_date, renewal_fee."""
    expired = row["end_date"] < today()
    return reminder_message(full_name(row["first_name"], row["last_name"]), row["package"],
                            row["end_date"], row["renewal_fee"], expired)


def reminder_link(row: dict) -> str:
    return whatsapp_link(row["mobile"], reminder_text(row))


def member_whatsapp_link(row: dict) -> str:
    """Fee reminder text when due / expired, otherwise just a greeting."""
    if row["end_date"] <= today() + timedelta(days=REMINDER_DAYS):
        return reminder_link(row)
    return whatsapp_link(row["mobile"], f"Namaste {full_name(row['first_name'], row['last_name'])} ji,\n")
