import contextlib
import sqlite3
from pathlib import Path

from config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """One connection per request/thread. Autocommit mode; writes go through write_txn()."""
    path = Path(db_path or settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI may run a sync dependency's setup and teardown on different
    # worker threads. Each connection is still used by exactly one request at a time.
    conn = sqlite3.connect(path, isolation_level=None, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())


@contextlib.contextmanager
def write_txn(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE takes the write lock up front, so concurrent writers queue
    (up to busy_timeout) instead of racing. Everything inside is one atomic unit."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
