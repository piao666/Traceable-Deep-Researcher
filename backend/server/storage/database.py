"""File-backed SQLite connections; only the migration command upgrades schema."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sqlite3
import time

from sqlalchemy import URL, create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError


class SchemaError(RuntimeError):
    pass


MIGRATION = Path(__file__).with_name("migrations") / "001_tasks.sql"
SCHEMA_VERSION = 1
REQUIRED_TABLES = {"schema_migrations", "reports", "report_versions", "report_chats",
                   "legacy_batches", "legacy_imports"}


class Database:
    def __init__(self, url: str):
        parsed = make_url(url)
        if (parsed.drivername not in {"sqlite", "sqlite+pysqlite"} or not parsed.database
                or parsed.database == ":memory:" or parsed.query or parsed.host or parsed.username
                or parsed.password or parsed.port):
            raise ValueError("TDR_DATABASE_URL must identify a file-backed SQLite database")
        self.path = Path(parsed.database).resolve()
        self.engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(self.path)), poolclass=NullPool,
            connect_args={"timeout": 30, "check_same_thread": True},
        )
        self.url = str(self.engine.url)

        @event.listens_for(self.engine, "connect")
        def configure(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")

    def _check(self, conn):
        tables = set(inspect(conn).get_table_names())
        if not REQUIRED_TABLES <= tables:
            raise SchemaError("Storage schema missing; run scripts/migrate_report_store.py before starting the API")
        rows = conn.execute(text("SELECT version, checksum FROM schema_migrations ORDER BY version")).all()
        expected = sha256(MIGRATION.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        if [(r.version, r.checksum) for r in rows] != [(SCHEMA_VERSION, expected)]:
            raise SchemaError("Unsupported or modified storage schema; use a compatible application and migration command")

    def check_schema(self):
        # A read-only check must not create an empty file for an unprepared deployment.
        if not self.path.is_file():
            raise SchemaError("Storage is not initialized; run scripts/migrate_report_store.py --init-only")
        with self.engine.connect() as conn:
            self._check(conn)

    def migrate(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.engine.connect() as conn:
            # journal_mode transitions can return BUSY without honoring busy_timeout.
            deadline = time.monotonic() + 30
            while True:
                try:
                    mode = conn.exec_driver_sql("PRAGMA journal_mode=WAL").scalar()
                    if mode != "wal":
                        raise SchemaError("SQLite WAL could not be enabled")
                    break
                except OperationalError as exc:
                    conn.rollback()
                    if getattr(exc.orig, "sqlite_errorcode", None) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            conn.commit()
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                tables = set(inspect(conn).get_table_names())
                if "schema_migrations" in tables:
                    self._check(conn)
                elif tables:
                    raise SchemaError("Refusing to initialize a nonempty database without a schema version")
                else:
                    statement = ""
                    for line in MIGRATION.read_text(encoding="utf-8").splitlines(True):
                        statement += line
                        if sqlite3.complete_statement(statement):
                            conn.exec_driver_sql(statement)
                            statement = ""
                    if statement.strip():
                        raise SchemaError("Incomplete migration SQL")
                    conn.execute(text("INSERT INTO schema_migrations(version, checksum) VALUES (:version, :checksum)"),
                                 {"version": SCHEMA_VERSION, "checksum": sha256(MIGRATION.read_text(encoding="utf-8").encode("utf-8")).hexdigest()})
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @contextmanager
    def read(self):
        self.check_schema()
        with self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN")
            yield conn

    @contextmanager
    def write(self):
        self.check_schema()
        with self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def dispose(self):
        self.engine.dispose()
