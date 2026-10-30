"""File-backed SQLite connections; only the migration command upgrades schema."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from sqlalchemy import URL, create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError


class SchemaError(RuntimeError):
    pass


MIGRATION = Path(__file__).with_name("migrations") / "001_tasks.sql"
TASK_MIGRATION = MIGRATION.with_name("002_research_tasks.sql")
CHECKPOINT_MIGRATION = MIGRATION.with_name('003_task_checkpoints.sql')
EXPORT_MIGRATION = MIGRATION.with_name('004_export_jobs.sql')
SCHEMA_VERSION = 4
REQUIRED_TABLES = {"schema_migrations", "reports", "report_versions", "report_chats",
                   "legacy_batches", "legacy_imports", "research_tasks", "task_attempts", "task_events", "task_checkpoints", "export_jobs"}


def migrations():
    return [(1, MIGRATION), (2, TASK_MIGRATION), (3, CHECKPOINT_MIGRATION), (4, EXPORT_MIGRATION)]


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
        self.last_backup = None

        @event.listens_for(self.engine, "connect")
        def configure(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")

    def _check(self, conn):
        tables = set(inspect(conn).get_table_names())
        if not REQUIRED_TABLES <= tables:
            raise SchemaError("Storage schema missing; run scripts/migrate_report_store.py before starting the API")
        rows = conn.execute(text("SELECT version, checksum FROM schema_migrations ORDER BY version")).all()
        expected = [(version, sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest())
                    for version, path in migrations()]
        if [(r.version, r.checksum) for r in rows] != expected:
            raise SchemaError("Unsupported or modified storage schema; use a compatible application and migration command")

    def check_schema(self):
        # A read-only check must not create an empty file for an unprepared deployment.
        if not self.path.is_file():
            raise SchemaError("Storage is not initialized; run scripts/migrate_report_store.py --init-only")
        with self.engine.connect() as conn:
            self._check(conn)

    def migrate(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file():
            with self.engine.connect() as existing:
                if 'schema_migrations' in inspect(existing).get_table_names():
                    rows=existing.execute(text('SELECT version,checksum FROM schema_migrations ORDER BY version')).all()
                    expected=[(v,sha256(p.read_text(encoding='utf-8').encode()).hexdigest()) for v,p in migrations()]
                    if not rows or [(r.version,r.checksum) for r in rows]!=expected[:len(rows)]:
                        raise SchemaError('Unknown or modified schema; refusing migration')
                    if rows[-1].version<SCHEMA_VERSION:
                        self.last_backup=self.backup()
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
                    rows = conn.execute(text("SELECT version, checksum FROM schema_migrations ORDER BY version")).all()
                    expected = [(v, sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest())
                                for v, p in migrations()]
                    if not rows or [(r.version, r.checksum) for r in rows] != expected[:len(rows)]:
                        raise SchemaError("Unknown or modified schema; refusing migration")
                    applied = rows[-1].version
                elif tables:
                    raise SchemaError("Refusing to initialize a nonempty database without a schema version")
                else:
                    applied = 0
                for version, path in migrations():
                    if version <= applied:
                        continue
                    statement = ""
                    for line in path.read_text(encoding="utf-8").splitlines(True):
                        statement += line
                        if sqlite3.complete_statement(statement):
                            conn.exec_driver_sql(statement)
                            statement = ""
                    if statement.strip():
                        raise SchemaError("Incomplete migration SQL")
                    conn.execute(text("INSERT INTO schema_migrations(version, checksum) VALUES (:version, :checksum)"),
                                 {"version": version, "checksum": sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()})
                self._check(conn)
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

    def backup(self):
        if not self.path.is_file():
            raise SchemaError('Cannot back up a missing database')
        directory=self.path.parent/'backups'
        directory.mkdir(parents=True,exist_ok=True)
        target=directory/(self.path.stem+'-'+uuid4().hex+'.sqlite3')
        # SQLite backup includes committed WAL pages; copying only the .db would not.
        source=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=30)
        try:
            destination=sqlite3.connect(target)
            try:
                source.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise SchemaError('Database backup integrity check failed')
            finally:
                destination.close()
        finally:
            source.close()
        return target
