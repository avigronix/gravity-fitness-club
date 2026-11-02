"""Gravity Fitness Club admin panel – FastAPI app and all routes."""
import logging
import math
import os
import re
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

import db
import utils

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
MAX_PHOTO_BYTES = 5 * 1024 * 1024

FOOD_TYPES = ["Veg", "Non-veg", "Eggetarian"]
OBJECTIVES = ["Fat loss", "Muscle gain", "General fitness", "Weight gain"]
BP_OPTIONS = ["No", "High", "Low"]
PAY_MODES = ["Cash", "UPI", "Card"]
MEMBER_FIELDS = ("first_name", "last_name", "guardian_name", "sex", "age", "mobile", "email",
                 "aadhaar_no", "address", "weight_kg", "height", "food_type", "objective",
                 "sugar", "blood_pressure", "disease")
PAYMENT_FIELDS = ("package_id", "start_date", "fee", "mode")
PER_PAGE = 20

log = logging.getLogger("uvicorn.error")


# ---------- startup ----------

def check_secret_key():
    if utils.SECRET_KEY in ("", "change-me"):
        log.warning("=" * 70)
        log.warning("SECRET_KEY in .env is still 'change-me' – login cookies are NOT safe.")
        log.warning('Set one: python -c "import secrets; print(secrets.token_hex(32))"')
        log.warning("=" * 70)


def create_first_admin():
    if db.fetch_one("SELECT 1 FROM admins LIMIT 1"):
        return
    db.execute(
        "INSERT INTO admins (name, username, password_hash) VALUES (%s, %s, %s)",
        (os.getenv("ADMIN_NAME", "Owner"), os.getenv("ADMIN_USERNAME", "admin"),
         utils.hash_password(os.getenv("ADMIN_PASSWORD", "ChangeMe@123"))),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_secret_key()
    db.pool.open(wait=True, timeout=10)
    create_first_admin()
    yield
    db.pool.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=utils.SECRET_KEY, max_age=utils.REMEMBER_DAYS * 86400,
                   same_site="lax", https_only=utils.COOKIE_SECURE)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters.update(
    inr=utils.inr, inr_short=utils.inr_short, dmy=utils.fmt_date, short=utils.fmt_short,
    long=utils.fmt_long, days_label=utils.days_label, mask_aadhaar=utils.mask_aadhaar,
    days_left=lambda d: (d - utils.today()).days,
)
templates.env.globals.update(
    gym_name=utils.GYM_NAME, reminder_days=utils.REMINDER_DAYS, recent_days=utils.RECENT_EXPIRED_DAYS,
    status_labels=utils.STATUS_LABELS,
    initials=utils.initials, full_name=utils.full_name, member_wa_link=utils.member_whatsapp_link,
    sent_label=utils.sent_label, food_types=FOOD_TYPES, objectives=OBJECTIVES, pay_modes=PAY_MODES,
)


# ---------- auth ----------

class LoginRequired(Exception):
    pass


def login_required(request: Request):
    if not utils.is_logged_in(request.session):
        request.session.clear()
        raise LoginRequired


@app.exception_handler(LoginRequired)
async def go_to_login(request: Request, exc: LoginRequired):
    if request.headers.get("HX-Request"):
        return Response(headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


def error_page(request: Request, status_code: int):
    """Plain page without DB calls, so it also works when the database is down."""
    title = "Page not found" if status_code == 404 else "Something went wrong"
    return templates.TemplateResponse(request, "error.html", {"code": status_code, "title": title},
                                      status_code=status_code)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error_page(request, exc.status_code)


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    return error_page(request, 500)       # the error itself is still logged by uvicorn


# Every route on this router needs a logged-in admin.
router = APIRouter(dependencies=[Depends(login_required)])


# ---------- page helpers ----------

def reminder_count() -> int:
    """Badge: due soon + expired in the last 30 days (same as the two reminder tabs)."""
    row = db.fetch_one(
        "SELECT COUNT(*) AS n FROM members "
        "WHERE end_date BETWEEN CURRENT_DATE - %s::int AND CURRENT_DATE + %s::int",
        (utils.RECENT_EXPIRED_DAYS, utils.REMINDER_DAYS),
    )
    return row["n"]


def flash(request: Request, message: str, kind: str = "success"):
    request.session["flash"] = {"kind": kind, "message": message}


def render(request: Request, name: str, nav: str = "", status_code: int = 200, **context):
    """Full page. Adds what base.html needs (one count query for the reminders badge)."""
    if "reminder_count" not in context:
        context["reminder_count"] = reminder_count() if utils.is_logged_in(request.session) else 0
    context.update(
        nav=nav,
        today=utils.today(),
        greeting=utils.greeting(),
        admin_name=request.session.get("admin_name", ""),
        flash=request.session.pop("flash", None),
    )
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def redirect(url: str):
    return RedirectResponse(url, status_code=303)


async def form_data(request: Request):
    """Whole form (incl. files) as a dependency, so routes can stay plain `def`."""
    return await request.form()


# ---------- small parsers ----------

def to_int(text: str, low: int, high: int) -> int | None:
    try:
        number = int(text)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def to_float(text: str, low: float, high: float) -> float | None:
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def to_date(text: str) -> date | None:
    try:
        value = date.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return value if 2000 <= value.year <= 2100 else None


def digits_only(text: str) -> str:
    return re.sub(r"[\s\-]", "", text or "")


# ---------- members: queries ----------

def get_packages() -> list[dict]:
    return db.fetch_all("SELECT id, name, months, price FROM packages ORDER BY sort_order, id")


def find_package(packages: list[dict], package_id) -> dict | None:
    return next((p for p in packages if str(p["id"]) == str(package_id)), None)


def next_membership_no() -> str:
    row = db.fetch_one("SELECT CASE WHEN is_called THEN last_value + 1 ELSE last_value END AS n "
                       "FROM members_id_seq")
    return f"GFC-{row['n']:04d}"


def members_with_mobile(mobile: str, exclude_id: int = 0) -> list[dict]:
    return db.fetch_all("SELECT id, membership_no, first_name, last_name FROM members "
                        "WHERE mobile = %s AND id <> %s ORDER BY id LIMIT 3", (mobile, exclude_id))


def get_member(member_id: int) -> dict | None:
    return db.fetch_one(
        f"""SELECT m.*, p.name AS package, p.months, p.price AS renewal_fee,
                   {utils.STATUS_SQL} AS status
            FROM members m JOIN packages p ON p.id = m.package_id
            WHERE m.id = %(id)s""",
        {"days": utils.REMINDER_DAYS, "id": member_id},
    )


def get_payments(member_id: int) -> list[dict]:
    return db.fetch_all(
        """SELECT pay.*, p.name AS package FROM payments pay
           JOIN packages p ON p.id = pay.package_id
           WHERE pay.member_id = %s ORDER BY pay.paid_on DESC, pay.id DESC""",
        (member_id,),
    )


# ---------- members: validation ----------

EMAIL_RE = r"[^@\s]+@[^@\s]+\.[^@\s]+"
# 5.11 / 5.5 / 6 / 5'11 / 5'11" / 5' 11" / 6' – stored exactly as typed
HEIGHT_RE = r"[2-8](\.\d{1,2}|'(\s?\d{1,2}(\"|'')?)?)?"


def clean_member(form) -> tuple[dict, dict]:
    """Personal / body / medical fields (shared by register and edit). Returns (values, errors)."""
    v = {k: str(form.get(k) or "").strip() for k in MEMBER_FIELDS}
    v["mobile"] = digits_only(v["mobile"])
    v["aadhaar_no"] = digits_only(v["aadhaar_no"])
    v["sugar"] = v["sugar"] or "No"
    v["blood_pressure"] = v["blood_pressure"] or "No"
    checks = [
        ("first_name", 0 < len(v["first_name"]) <= 60, "Enter first name"),
        ("last_name", len(v["last_name"]) <= 60, "Last name is too long"),
        ("guardian_name", len(v["guardian_name"]) <= 100, "Name is too long"),
        ("sex", v["sex"] in ("M", "F"), "Select male or female"),
        ("age", not v["age"] or to_int(v["age"], 5, 100) is not None, "Age must be 5 to 100"),
        ("mobile", re.fullmatch(r"\d{10}", v["mobile"]), "Enter a 10-digit mobile number"),
        ("email", not v["email"] or (len(v["email"]) <= 120 and re.fullmatch(EMAIL_RE, v["email"])),
         "Enter a valid email"),
        ("aadhaar_no", not v["aadhaar_no"] or re.fullmatch(r"\d{12}", v["aadhaar_no"]),
         "Aadhaar must be 12 digits"),
        ("weight_kg", not v["weight_kg"] or to_float(v["weight_kg"], 20, 300) is not None,
         "Weight must be 20 to 300 kg"),
        ("height", not v["height"] or re.fullmatch(HEIGHT_RE, v["height"]),
         "Height like 5.11, 6 or 5'11\""),
        ("food_type", v["food_type"] in ("", *FOOD_TYPES), "Select food type"),
        ("objective", v["objective"] in ("", *OBJECTIVES), "Select objective"),
        ("sugar", v["sugar"] in ("No", "Yes"), "Select Yes or No"),
        ("blood_pressure", v["blood_pressure"] in BP_OPTIONS, "Select blood pressure"),
    ]
    return v, {name: msg for name, ok, msg in checks if not ok}


def clean_payment(form, packages: list[dict], with_start: bool = True) -> tuple[dict, dict]:
    """Package, start date, fee, mode (register; renew has no start date). Returns (values, errors)."""
    v = {k: str(form.get(k) or "").strip() for k in PAYMENT_FIELDS}
    checks = [
        ("package_id", find_package(packages, v["package_id"]), "Select a package"),
        ("start_date", not with_start or to_date(v["start_date"]), "Enter a valid start date"),
        ("fee", to_int(v["fee"], 0, 1_000_000) is not None, "Enter amount in rupees (numbers only)"),
        ("mode", v["mode"] in PAY_MODES, "Select payment mode"),
    ]
    return v, {name: msg for name, ok, msg in checks if not ok}


def member_params(v: dict) -> dict:
    """Validated form strings -> values for the members table."""
    params = {k: (v[k] or None) for k in MEMBER_FIELDS}
    params["age"] = int(v["age"]) if v["age"] else None
    params["weight_kg"] = float(v["weight_kg"]) if v["weight_kg"] else None
    params["sugar"] = v["sugar"] == "Yes"
    params["blood_pressure"] = v["blood_pressure"]
    return params


def photo_ext(data: bytes) -> str | None:
    """Real file type from the first bytes (not the file name)."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def read_photo(upload) -> tuple[bytes | None, str | None, str | None]:
    """Returns (data, ext, error). No file chosen -> (None, None, None)."""
    if not getattr(upload, "filename", ""):
        return None, None, None
    data = upload.file.read(MAX_PHOTO_BYTES + 1)
    if not data:
        return None, None, None
    if len(data) > MAX_PHOTO_BYTES:
        return None, None, "Photo must be 5 MB or smaller"
    ext = photo_ext(data)
    if not ext:
        return None, None, "Photo must be a JPG, PNG or WEBP image"
    return data, ext, None


# ---------- members: save ----------

INSERT_MEMBER = """
    INSERT INTO members (first_name, last_name, guardian_name, sex, age, mobile, email, aadhaar_no,
                         address, weight_kg, height, food_type, objective, sugar, blood_pressure,
                         disease, package_id, start_date, end_date, fee)
    VALUES (%(first_name)s, %(last_name)s, %(guardian_name)s, %(sex)s, %(age)s, %(mobile)s,
            %(email)s, %(aadhaar_no)s, %(address)s, %(weight_kg)s, %(height)s, %(food_type)s,
            %(objective)s, %(sugar)s, %(blood_pressure)s, %(disease)s, %(package_id)s,
            %(start_date)s, %(end_date)s, %(fee)s)
    RETURNING id, membership_no"""

INSERT_PAYMENT = """
    INSERT INTO payments (member_id, package_id, amount, mode, period_start, period_end)
    VALUES (%(member_id)s, %(package_id)s, %(fee)s, %(mode)s, %(start_date)s, %(end_date)s)"""


def save_photo(conn, member_id: int, data: bytes, ext: str):
    name = f"{member_id}.{ext}"
    for old in UPLOAD_DIR.glob(f"{member_id}.*"):   # replace an older photo of any type
        old.unlink()
    (UPLOAD_DIR / name).write_bytes(data)
    conn.execute("UPDATE members SET photo = %s WHERE id = %s", (name, member_id))


def create_member(v: dict, package: dict, photo: bytes | None, ext: str | None) -> dict:
    """Member + first payment (+ photo) in ONE transaction."""
    start = to_date(v["start_date"])
    params = member_params(v) | {
        "package_id": package["id"], "start_date": start, "fee": int(v["fee"]),
        "end_date": utils.end_date(start, package["months"]), "mode": v["mode"],
    }
    with db.connection() as conn:
        member = conn.execute(INSERT_MEMBER, params).fetchone()
        conn.execute(INSERT_PAYMENT, params | {"member_id": member["id"]})
        if photo:
            save_photo(conn, member["id"], photo, ext)
    return member


# ---------- members: register ----------

def register_defaults(packages: list[dict]) -> dict:
    first = packages[0]
    return {k: "" for k in MEMBER_FIELDS} | {
        "package_id": str(first["id"]), "fee": str(first["price"]), "mode": "Cash",
        "start_date": utils.today().isoformat(), "sugar": "No", "blood_pressure": "No", "rules": "",
    }


def register_page(request: Request, v: dict, errors: dict, status_code: int = 200):
    packages = get_packages()
    package, start = find_package(packages, v["package_id"]), to_date(v["start_date"])
    end = utils.end_date(start, package["months"]) if package and start else None
    duplicates = members_with_mobile(v["mobile"]) if len(v["mobile"]) == 10 else []
    return render(request, "register.html", nav="register", status_code=status_code,
                  v=v, errors=errors, packages=packages, package=package, end=end,
                  duplicates=duplicates, next_no=next_membership_no())


@router.get("/members/new")
def register_form(request: Request):
    return register_page(request, register_defaults(get_packages()), {})


@router.post("/members/new")
def register(request: Request, form=Depends(form_data)):
    packages = get_packages()
    v, errors = clean_member(form)
    pay, pay_errors = clean_payment(form, packages)
    v, errors = v | pay | {"rules": form.get("rules") or ""}, errors | pay_errors
    if not v["rules"]:
        errors["rules"] = "Member must accept the gym rules"
    photo, ext, photo_error = read_photo(form.get("photo"))
    if photo_error:
        errors["photo"] = photo_error
    if errors:
        return register_page(request, v, errors, status_code=400)
    member = create_member(v, find_package(packages, v["package_id"]), photo, ext)
    flash(request, f"Member saved – {member['membership_no']}")
    return redirect(f"/members/{member['id']}")


@router.get("/members/check-mobile")
def check_mobile(request: Request, mobile: str = "", exclude: int = 0):
    mobile = digits_only(mobile)
    matches = members_with_mobile(mobile, exclude) if re.fullmatch(r"\d{10}", mobile) else []
    return templates.TemplateResponse(request, "partials/mobile_check.html", {"duplicates": matches})


# ---------- members: list ----------

def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_where(q: str) -> tuple[str, dict]:
    """Name, full name, mobile or membership no (GFC-0012 / 0012 / 12)."""
    if not q:
        return "TRUE", {}
    number = re.fullmatch(r"(?:gfc-?)?0*(\d{1,7})", q, re.IGNORECASE)
    digits = digits_only(q)
    return (
        """(m.first_name ILIKE %(like)s OR m.last_name ILIKE %(like)s
            OR concat_ws(' ', m.first_name, m.last_name) ILIKE %(like)s
            OR m.membership_no ILIKE %(like)s OR m.mobile LIKE %(digits)s OR m.id = %(num)s)""",
        {"like": f"%{escape_like(q)}%", "num": int(number.group(1)) if number else None,
         "digits": f"%{digits}%" if digits.isdigit() else f"%{escape_like(q)}%"},
    )


def count_by_status(where: str, params: dict) -> dict:
    return db.fetch_one(
        f"""SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE {utils.STATUS_WHERE['active']}) AS active,
                   COUNT(*) FILTER (WHERE {utils.STATUS_WHERE['due']}) AS due,
                   COUNT(*) FILTER (WHERE {utils.STATUS_WHERE['expired']}) AS expired
            FROM members m WHERE {where}""",
        params | {"days": utils.REMINDER_DAYS},
    )


def list_members(where: str, params: dict, status: str, page: int) -> list[dict]:
    return db.fetch_all(
        f"""SELECT m.id, m.membership_no, m.first_name, m.last_name, m.mobile, m.start_date,
                   m.end_date, m.fee, p.name AS package, p.price AS renewal_fee,
                   {utils.STATUS_SQL} AS status
            FROM members m JOIN packages p ON p.id = m.package_id
            WHERE {where} AND {utils.STATUS_WHERE[status]}
            ORDER BY m.id DESC LIMIT %(limit)s OFFSET %(offset)s""",
        params | {"days": utils.REMINDER_DAYS, "limit": PER_PAGE, "offset": (page - 1) * PER_PAGE},
    )


def members_url(q: str = "", status: str = "", page: int = 1) -> str:
    query = urlencode({k: v for k, v in (("q", q), ("status", status), ("page", page)) if v and v != 1})
    return "/members" + ("?" + query if query else "")


def page_numbers(page: int, pages: int) -> list[int | None]:
    """1 … 4 5 6 … 12  (None = gap)."""
    keep = {1, pages, page - 1, page, page + 1}
    numbers, last = [], 0
    for n in sorted(k for k in keep if 1 <= k <= pages):
        if n - last > 1:
            numbers.append(None)
        numbers.append(n)
        last = n
    return numbers


def is_partial(request: Request) -> bool:
    """HTMX swap (not a history restore, which needs the whole page)."""
    return bool(request.headers.get("HX-Request")) and not request.headers.get("HX-History-Restore-Request")


def page_or_partial(request: Request, page: str, partial: str, nav: str, url: str, context: dict):
    """Same URL: whole page for a normal visit, only the list partial for an HTMX swap."""
    if is_partial(request):
        response = templates.TemplateResponse(request, partial, context)
        response.headers["HX-Push-Url"] = url      # e.g. page=99 -> shows (and pushes) last page
    else:
        response = render(request, page, nav=nav, **context)
    response.headers["Vary"] = "HX-Request"        # browser cache never mixes page and partial
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/members")
def members_page(request: Request, q: str = "", status: str = "", page: str = "1"):
    q = " ".join(q.split())[:60]
    status = status if status in utils.STATUS_LABELS else ""
    where, params = search_where(q)
    counts = count_by_status(where, params)
    total = counts[status or "total"]
    pages = max(1, math.ceil(total / PER_PAGE))
    page_no = min(to_int(page, 1, 1_000_000) or 1, pages)
    url = members_url(q, status, page_no)
    request.session["members_url"] = url
    context = dict(rows=list_members(where, params, status, page_no), q=q, status=status,
                   counts=counts, total=total, page=page_no, pages=pages, per_page=PER_PAGE,
                   page_numbers=page_numbers(page_no, pages), members_url=members_url)
    return page_or_partial(request, "members.html", "partials/members_list.html", "members", url, context)


# ---------- members: detail / edit / renew ----------

def member_form_values(member: dict) -> dict:
    """DB row -> the strings the edit form shows."""
    v = {k: "" if member[k] is None else str(member[k]) for k in MEMBER_FIELDS}
    v["weight_kg"] = f"{member['weight_kg']:g}" if member["weight_kg"] is not None else ""
    v["sugar"] = "Yes" if member["sugar"] else "No"
    return v


def renew_defaults(member: dict) -> dict:
    return {"package_id": str(member["package_id"]), "fee": str(member["renewal_fee"]), "mode": "Cash"}


def safe_return_url(url: str) -> str:
    """Only allow going back to a reminders tab (never an outside URL)."""
    return url if re.fullmatch(r"/reminders(\?tab=(due|expired)(&show=all)?)?", url or "") else ""


def member_page(request: Request, member: dict, status_code: int = 200, return_to: str = "", **extra):
    """return_to: set when opened from Payment reminders ("Mark paid") – renew goes back there."""
    query = request.query_params
    if not return_to and query.get("back") == "reminders":
        return_to = reminders_url(query.get("tab", "due"), query.get("show", ""))
    payments = get_payments(member["id"])
    context = dict(
        m=member, member_name=utils.full_name(member["first_name"], member["last_name"]),
        payments=payments, total_paid=sum(p["amount"] for p in payments), packages=get_packages(),
        renew_start=utils.renewal_start(member["end_date"]), rv=renew_defaults(member),
        renew_errors={}, open_renew=bool(query.get("renew")), editing=False, return_to=return_to,
        back_url=return_to or request.session.get("members_url", "/members"),
    )
    return render(request, "member.html", nav="reminders" if return_to else "members",
                  status_code=status_code, **(context | extra))


def member_or_redirect(request: Request, member_id: int):
    member = get_member(member_id)
    if not member:
        flash(request, "Member not found", "error")
    return member


@router.get("/members/{member_id:int}")
def member_detail(request: Request, member_id: int):
    member = member_or_redirect(request, member_id)
    return member_page(request, member) if member else redirect("/members")


UPDATE_MEMBER = ("UPDATE members SET " + ", ".join(f"{f} = %({f})s" for f in MEMBER_FIELDS)
                 + " WHERE id = %(id)s")


def update_member(member_id: int, v: dict, photo: bytes | None, ext: str | None):
    with db.connection() as conn:
        conn.execute(UPDATE_MEMBER, member_params(v) | {"id": member_id})
        if photo:
            save_photo(conn, member_id, photo, ext)


def edit_page(request: Request, member: dict, v: dict, errors: dict, status_code: int = 200):
    duplicates = members_with_mobile(v["mobile"], member["id"]) if len(v["mobile"]) == 10 else []
    return member_page(request, member, status_code, editing=True, v=v, errors=errors,
                       duplicates=duplicates)


@router.get("/members/{member_id:int}/edit")
def edit_form(request: Request, member_id: int):
    member = member_or_redirect(request, member_id)
    return edit_page(request, member, member_form_values(member), {}) if member else redirect("/members")


@router.post("/members/{member_id:int}/edit")
def edit(request: Request, member_id: int, form=Depends(form_data)):
    member = member_or_redirect(request, member_id)
    if not member:
        return redirect("/members")
    v, errors = clean_member(form)
    photo, ext, photo_error = read_photo(form.get("photo"))
    if photo_error:
        errors["photo"] = photo_error
    if errors:
        return edit_page(request, member, v, errors, status_code=400)
    update_member(member_id, v, photo, ext)
    flash(request, "Member details updated")
    return redirect(f"/members/{member_id}")


def renew_member(member_id: int, v: dict, package: dict) -> tuple[date, date] | None:
    """Payment + new period in ONE transaction. None if the member was renewed meanwhile
    (double tap / second tab): the form's current_end no longer matches."""
    with db.connection() as conn:
        row = conn.execute("SELECT end_date FROM members WHERE id = %s FOR UPDATE", (member_id,)).fetchone()
        if row["end_date"].isoformat() != v["current_end"]:
            return None
        start = utils.renewal_start(row["end_date"])
        params = {"member_id": member_id, "package_id": package["id"], "fee": int(v["fee"]),
                  "mode": v["mode"], "start_date": start, "end_date": utils.end_date(start, package["months"])}
        conn.execute(INSERT_PAYMENT, params)
        conn.execute("""UPDATE members SET package_id = %(package_id)s, start_date = %(start_date)s,
                               end_date = %(end_date)s, fee = %(fee)s, last_reminder_at = NULL
                        WHERE id = %(member_id)s""", params)
    return params["start_date"], params["end_date"]


@router.post("/members/{member_id:int}/renew")
def renew(request: Request, member_id: int, form=Depends(form_data)):
    member = member_or_redirect(request, member_id)
    if not member:
        return redirect("/members")
    packages = get_packages()
    v, errors = clean_payment(form, packages, with_start=False)
    v["current_end"] = str(form.get("current_end") or "")
    return_to = safe_return_url(str(form.get("return_to") or ""))
    if errors:
        return member_page(request, member, 400, return_to=return_to, rv=v, renew_errors=errors,
                           open_renew=True)
    period = renew_member(member_id, v, find_package(packages, v["package_id"]))
    name = utils.full_name(member["first_name"], member["last_name"])
    if period:
        flash(request, f"Payment saved for {name} – new period {utils.fmt_date(period[0])} "
                       f"to {utils.fmt_date(period[1])}")
    else:
        flash(request, "Already renewed – no second payment was saved.", "error")
    return redirect(return_to or f"/members/{member_id}")


# ---------- payment reminders ----------

REMINDER_WHERE = {
    "due": "m.end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + %(days)s::int",
    "expired": "m.end_date < CURRENT_DATE AND m.end_date >= CURRENT_DATE - %(recent)s::int",
    "expired_all": "m.end_date < CURRENT_DATE",
}
REMINDER_PARAMS = {"days": utils.REMINDER_DAYS, "recent": utils.RECENT_EXPIRED_DAYS}


def reminders_url(tab: str = "due", show: str = "") -> str:
    tab = tab if tab in ("due", "expired") else "due"
    return f"/reminders?tab={tab}" + ("&show=all" if tab == "expired" and show == "all" else "")


def reminder_counts() -> dict:
    return db.fetch_one(
        f"""SELECT COUNT(*) FILTER (WHERE {REMINDER_WHERE['due']}) AS due,
                   COUNT(*) FILTER (WHERE {REMINDER_WHERE['expired']}) AS expired,
                   COUNT(*) FILTER (WHERE {REMINDER_WHERE['expired_all']}) AS expired_all
            FROM members m""",
        REMINDER_PARAMS,
    )


def get_reminders(key: str, limit: int = 500) -> list[dict]:
    order = "m.end_date, m.id" if key == "due" else "m.end_date DESC, m.id"
    rows = db.fetch_all(
        f"""SELECT m.id, m.membership_no, m.first_name, m.last_name, m.mobile, m.end_date,
                   m.last_reminder_at, p.name AS package, p.price AS renewal_fee
            FROM members m JOIN packages p ON p.id = m.package_id
            WHERE {REMINDER_WHERE[key]} ORDER BY {order} LIMIT %(limit)s""",
        REMINDER_PARAMS | {"limit": limit},
    )
    return [r | {"message": utils.reminder_text(r), "link": utils.reminder_link(r)} for r in rows]


@router.get("/reminders")
def reminders_page(request: Request, tab: str = "due", show: str = ""):
    url = reminders_url(tab, show)
    tab = "expired" if tab == "expired" else "due"
    show = "all" if url.endswith("show=all") else ""
    rows = get_reminders("expired_all" if show else tab)
    context = dict(rows=rows, tab=tab, show=show, counts=reminder_counts(), reminders_url=reminders_url,
                   to_collect=sum(r["renewal_fee"] for r in rows),
                   sent_count=sum(1 for r in rows if r["last_reminder_at"]))
    return page_or_partial(request, "reminders.html", "partials/reminder_list.html", "reminders", url, context)


@router.post("/reminders/{member_id:int}/sent")
def reminder_sent(member_id: int):
    """Called by app.js when "Send on WhatsApp" is tapped (the link itself opens WhatsApp)."""
    row = db.fetch_one("UPDATE members SET last_reminder_at = now() WHERE id = %s RETURNING last_reminder_at",
                       (member_id,))
    if not row:
        return Response(status_code=404)
    return {"label": utils.sent_label(row["last_reminder_at"])}


# ---------- login / logout ----------

@app.get("/login")
def login_page(request: Request):
    if utils.is_logged_in(request.session):
        return redirect("/")
    return render(request, "login.html")


@app.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""),
          remember: str = Form("")):
    username = username.strip()
    keys = ["user:" + username.lower(), "ip:" + (request.client.host if request.client else "")]
    wait = utils.login_blocked_seconds(keys)
    if wait:
        return render(request, "login.html", status_code=429, username=username,
                      error=f"Too many wrong attempts. Please try again in {math.ceil(wait / 60)} minutes.")
    admin = db.fetch_one("SELECT id, name, password_hash FROM admins WHERE username = %s AND is_active",
                         (username,))
    if not admin or not utils.check_password(password, admin["password_hash"]):
        utils.record_failed_login(keys)
        return render(request, "login.html", status_code=401, username=username,
                      error="Wrong username or password. Please try again.")
    utils.clear_failed_logins(keys)
    utils.start_session(request.session, admin, remember=bool(remember))
    return redirect("/")


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


# ---------- dashboard ----------

def dashboard_summary() -> dict:
    """All card numbers in one query (same rules as db/common_queries.sql)."""
    return db.fetch_one(
        f"""SELECT COUNT(*) FILTER (WHERE {utils.STATUS_WHERE['active']}) AS active,
                   COUNT(*) FILTER (WHERE {utils.STATUS_WHERE['due']}) AS due,
                   COUNT(*) FILTER (WHERE m.end_date < CURRENT_DATE
                                      AND m.end_date >= CURRENT_DATE - %(recent)s::int) AS expired,
                   COUNT(*) FILTER (WHERE {utils.STATUS_WHERE['expired']}) AS expired_all,
                   COUNT(*) FILTER (WHERE m.created_at >= date_trunc('month', CURRENT_DATE)) AS joined,
                   (SELECT COALESCE(SUM(amount), 0) FROM payments
                     WHERE paid_on >= date_trunc('month', CURRENT_DATE)) AS collected,
                   (SELECT COUNT(*) FROM payments
                     WHERE paid_on >= date_trunc('month', CURRENT_DATE)) AS payments
            FROM members m""",
        {"days": utils.REMINDER_DAYS, "recent": utils.RECENT_EXPIRED_DAYS},
    )


def recent_joins() -> list[dict]:
    return db.fetch_all(
        """SELECT m.id, m.membership_no, m.first_name, m.last_name, m.created_at, p.name AS package
           FROM members m JOIN packages p ON p.id = m.package_id
           ORDER BY m.created_at DESC, m.id DESC LIMIT 5""")


@router.get("/")
def dashboard(request: Request):
    summary = dashboard_summary()
    return render(request, "dashboard.html", nav="dashboard", s=summary, due=get_reminders("due", limit=5),
                  recent=recent_joins(), reminder_count=summary["due"] + summary["expired"])


# ---------- account ----------

@router.get("/account/password")
def password_form(request: Request):
    return render(request, "password.html", nav="account", errors={})


@router.post("/account/password")
def change_password(request: Request, current: str = Form(""), new: str = Form(""), confirm: str = Form("")):
    admin = db.fetch_one("SELECT password_hash FROM admins WHERE id = %s", (request.session["admin_id"],))
    checks = [
        ("current", admin and utils.check_password(current, admin["password_hash"]), "Current password is wrong"),
        ("new", len(new) >= 8, "New password must be at least 8 characters"),
        ("confirm", new == confirm, "Passwords do not match"),
    ]
    errors = {name: msg for name, ok, msg in checks if not ok}
    if errors:
        return render(request, "password.html", nav="account", status_code=400, errors=errors)
    db.execute("UPDATE admins SET password_hash = %s WHERE id = %s",
               (utils.hash_password(new), request.session["admin_id"]))
    flash(request, "Password changed")
    return redirect("/")


app.include_router(router)
