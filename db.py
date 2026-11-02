"""PostgreSQL connection pool + tiny query helpers (plain SQL, %s parameters)."""
import os

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()


def _configure(conn):
    # Every connection works in IST so CURRENT_DATE is the gym's "today".
    conn.execute("SET timezone TO 'Asia/Kolkata'")
    conn.commit()


pool = ConnectionPool(
    os.getenv("DATABASE_URL", ""),
    min_size=1,
    max_size=10,
    open=False,
    configure=_configure,
    kwargs={"row_factory": dict_row},
)


def connection():
    """Use as `with db.connection() as conn:` – commits on success, rolls back on error."""
    return pool.connection()


def fetch_all(sql: str, params=()) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql: str, params=()) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchone()


def execute(sql: str, params=()) -> int:
    with pool.connection() as conn:
        return conn.execute(sql, params).rowcount
