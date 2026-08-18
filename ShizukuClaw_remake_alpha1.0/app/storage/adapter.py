from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from app.config import settings
from app.paths import ROOT, STORAGE_DIR, ensure_runtime_dirs


class StorageError(RuntimeError):
    pass


class StorageAdapter:
    """Default SQLite store. MySQL / PostgreSQL are optional plugins."""

    def __init__(self, driver: str | None = None) -> None:
        ensure_runtime_dirs()
        self.driver = (driver or settings.storage_driver or "sqlite").lower()
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._sql_conn: Any = None
        self.db_path = self._resolve_sqlite_path()
        self.connect()

    def _resolve_sqlite_path(self) -> Path:
        raw = settings.get("storage", {}).get("sqlite", {}).get("path", "data/storage/agent.db")
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def connect(self) -> None:
        if self.driver == "sqlite":
            self._connect_sqlite()
            return
        if self.driver in {"mysql", "postgresql", "postgres"}:
            self._connect_sql_plugin()
            return
        raise StorageError(f"unsupported storage driver: {self.driver}")

    def _connect_sqlite(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_sqlite_schema()

    def _connect_sql_plugin(self) -> None:
        try:
            import pymysql  # type: ignore
        except Exception:
            pymysql = None
        try:
            import psycopg2  # type: ignore
            import psycopg2.extras  # type: ignore
        except Exception:
            psycopg2 = None

        cfg = settings.get("storage", {}).get(self.driver if self.driver != "postgres" else "postgresql", {})
        if self.driver in {"postgresql", "postgres"}:
            if psycopg2 is None:
                raise StorageError("PostgreSQL plugin missing. Install psycopg2-binary first.")
            self._sql_conn = psycopg2.connect(
                host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 5432)),
                user=cfg.get("user", "postgres"),
                password=cfg.get("password", ""),
                dbname=cfg.get("database", "shizukuclaw"),
            )
            self._sql_conn.autocommit = True
            self._init_postgres_schema()
            return

        if pymysql is None:
            raise StorageError("MySQL plugin missing. Install pymysql first.")
        self._sql_conn = pymysql.connect(
            host=cfg.get("host", "127.0.0.1"),
            port=int(cfg.get("port", 3306)),
            user=cfg.get("user", "root"),
            password=cfg.get("password", ""),
            database=cfg.get("database", "shizukuclaw"),
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
        self._init_mysql_schema()

    def _init_sqlite_schema(self) -> None:
        assert self._conn is not None
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                embedding TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                thread_id TEXT NOT NULL,
                persona TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (thread_id, persona)
            );
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def _init_mysql_schema(self) -> None:
        sql = """
        CREATE TABLE IF NOT EXISTS chat_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            persona VARCHAR(64) NOT NULL,
            role VARCHAR(32) NOT NULL,
            content LONGTEXT NOT NULL,
            created_at VARCHAR(64) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS memories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            persona VARCHAR(64) NOT NULL,
            kind VARCHAR(32) NOT NULL,
            content LONGTEXT NOT NULL,
            metadata LONGTEXT,
            embedding LONGTEXT,
            created_at VARCHAR(64) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id VARCHAR(128) NOT NULL,
            persona VARCHAR(64) NOT NULL,
            state_json LONGTEXT NOT NULL,
            updated_at VARCHAR(64) NOT NULL,
            PRIMARY KEY (thread_id, persona)
        );
        CREATE TABLE IF NOT EXISTS kv_store (
            `key` VARCHAR(191) PRIMARY KEY,
            value LONGTEXT NOT NULL,
            updated_at VARCHAR(64) NOT NULL
        );
        """
        with self._sql_conn.cursor() as cur:
            for statement in [item.strip() for item in sql.split(";") if item.strip()]:
                cur.execute(statement)

    def _init_postgres_schema(self) -> None:
        sql = """
        CREATE TABLE IF NOT EXISTS chat_records (
            id SERIAL PRIMARY KEY,
            persona TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS memories (
            id SERIAL PRIMARY KEY,
            persona TEXT NOT NULL,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            embedding TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id TEXT NOT NULL,
            persona TEXT NOT NULL,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (thread_id, persona)
        );
        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
        with self._sql_conn.cursor() as cur:
            cur.execute(sql)

    def _now(self) -> str:
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"

    def add_chat_record(self, persona: str, role: str, content: str) -> int:
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                cur = self._conn.execute(
                    "INSERT INTO chat_records(persona, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (persona, role, content, self._now()),
                )
                self._conn.commit()
                return int(cur.lastrowid)
            with self._sql_conn.cursor() as cur:
                placeholder = "%s"
                cur.execute(
                    f"INSERT INTO chat_records(persona, role, content, created_at) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (persona, role, content, self._now()),
                )
                return int(getattr(cur, "lastrowid", 0) or 0)

    def list_records(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                rows = self._conn.execute(
                    "SELECT id, persona, role, content, created_at FROM chat_records ORDER BY id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
                return [dict(row) for row in rows]
            with self._sql_conn.cursor() as cur:
                cur.execute(
                    "SELECT id, persona, role, content, created_at FROM chat_records ORDER BY id DESC LIMIT %s OFFSET %s",
                    (limit, offset),
                )
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    def delete_record(self, record_id: int) -> bool:
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                cur = self._conn.execute("DELETE FROM chat_records WHERE id = ?", (record_id,))
                self._conn.commit()
                return cur.rowcount > 0
            with self._sql_conn.cursor() as cur:
                cur.execute("DELETE FROM chat_records WHERE id = %s", (record_id,))
                return True

    def clear_records(self) -> None:
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                self._conn.execute("DELETE FROM chat_records")
                self._conn.commit()
                return
            with self._sql_conn.cursor() as cur:
                cur.execute("DELETE FROM chat_records")

    def delete_first_n(self, n: int) -> int:
        records = self.list_records(limit=n, offset=0)
        deleted = 0
        for record in records:
            if self.delete_record(int(record["id"])):
                deleted += 1
        return deleted

    def add_memory(self, persona: str, content: str, kind: str = "long_term", metadata: dict[str, Any] | None = None) -> int:
        embedding = json.dumps(_embed_text(content), ensure_ascii=False)
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                cur = self._conn.execute(
                    "INSERT INTO memories(persona, kind, content, metadata, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (persona, kind, content, payload, embedding, self._now()),
                )
                self._conn.commit()
                return int(cur.lastrowid)
            with self._sql_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO memories(persona, kind, content, metadata, embedding, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (persona, kind, content, payload, embedding, self._now()),
                )
                return int(getattr(cur, "lastrowid", 0) or 0)

    def list_memories(self, persona: str | None = None, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT id, persona, kind, content, metadata, created_at FROM memories"
        conds: list[str] = []
        args: list[Any] = []
        if persona:
            conds.append("persona = ?")
            args.append(persona)
        if kind:
            conds.append("kind = ?")
            args.append(kind)
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                rows = self._conn.execute(query, args).fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    item["metadata"] = _safe_json(item.get("metadata"))
                    result.append(item)
                return result
            sql = query.replace("?", "%s")
            with self._sql_conn.cursor() as cur:
                cur.execute(sql, args)
                rows = cur.fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    item["metadata"] = _safe_json(item.get("metadata"))
                    result.append(item)
                return result

    def search_memories(self, query: str, persona: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        query_vec = _embed_text(query)
        with self._lock:
            sql = "SELECT id, persona, kind, content, metadata, embedding, created_at FROM memories"
            args: list[Any] = []
            if persona:
                sql += " WHERE persona = ?"
                args.append(persona)
            if self.driver == "sqlite":
                assert self._conn is not None
                rows = self._conn.execute(sql, args).fetchall()
                scored = []
                for row in rows:
                    item = dict(row)
                    vec = _safe_json(item.get("embedding")) or []
                    item["score"] = _cosine(query_vec, vec)
                    item["metadata"] = _safe_json(item.get("metadata"))
                    item.pop("embedding", None)
                    scored.append(item)
                scored.sort(key=lambda x: x.get("score", 0), reverse=True)
                return scored[:top_k]
            with self._sql_conn.cursor() as cur:
                cur.execute(sql.replace("?", "%s"), args)
                rows = cur.fetchall()
                scored = []
                for row in rows:
                    item = dict(row)
                    vec = _safe_json(item.get("embedding")) or []
                    item["score"] = _cosine(query_vec, vec)
                    item["metadata"] = _safe_json(item.get("metadata"))
                    item.pop("embedding", None)
                    scored.append(item)
                scored.sort(key=lambda x: x.get("score", 0), reverse=True)
                return scored[:top_k]

    def save_checkpoint(self, thread_id: str, persona: str, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                self._conn.execute(
                    """
                    INSERT INTO checkpoints(thread_id, persona, state_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(thread_id, persona) DO UPDATE SET
                        state_json=excluded.state_json,
                        updated_at=excluded.updated_at
                    """,
                    (thread_id, persona, payload, self._now()),
                )
                self._conn.commit()
                return
            with self._sql_conn.cursor() as cur:
                if self.driver in {"postgresql", "postgres"}:
                    cur.execute(
                        """
                        INSERT INTO checkpoints(thread_id, persona, state_json, updated_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (thread_id, persona) DO UPDATE SET
                            state_json=EXCLUDED.state_json,
                            updated_at=EXCLUDED.updated_at
                        """,
                        (thread_id, persona, payload, self._now()),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO checkpoints(thread_id, persona, state_json, updated_at)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            state_json=VALUES(state_json),
                            updated_at=VALUES(updated_at)
                        """,
                        (thread_id, persona, payload, self._now()),
                    )

    def load_checkpoint(self, thread_id: str, persona: str) -> dict[str, Any] | None:
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                row = self._conn.execute(
                    "SELECT state_json FROM checkpoints WHERE thread_id = ? AND persona = ?",
                    (thread_id, persona),
                ).fetchone()
                return _safe_json(row["state_json"]) if row else None
            with self._sql_conn.cursor() as cur:
                cur.execute(
                    "SELECT state_json FROM checkpoints WHERE thread_id = %s AND persona = %s",
                    (thread_id, persona),
                )
                row = cur.fetchone()
                if not row:
                    return None
                value = row["state_json"] if isinstance(row, dict) else row[0]
                return _safe_json(value)

    def set_kv(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                self._conn.execute(
                    """
                    INSERT INTO kv_store(key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                    """,
                    (key, payload, self._now()),
                )
                self._conn.commit()
                return
            with self._sql_conn.cursor() as cur:
                if self.driver in {"postgresql", "postgres"}:
                    cur.execute(
                        """
                        INSERT INTO kv_store(key, value, updated_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
                        """,
                        (key, payload, self._now()),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO kv_store(`key`, value, updated_at)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE value=VALUES(value), updated_at=VALUES(updated_at)
                        """,
                        (key, payload, self._now()),
                    )

    def get_kv(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if self.driver == "sqlite":
                assert self._conn is not None
                row = self._conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
                return _safe_json(row["value"]) if row else default
            with self._sql_conn.cursor() as cur:
                column = "`key`" if self.driver == "mysql" else "key"
                cur.execute(f"SELECT value FROM kv_store WHERE {column} = %s", (key,))
                row = cur.fetchone()
                if not row:
                    return default
                value = row["value"] if isinstance(row, dict) else row[0]
                parsed = _safe_json(value)
                return default if parsed is None else parsed

    def status(self) -> dict[str, Any]:
        sqlite_path = None
        if self.driver == "sqlite":
            try:
                sqlite_path = self.db_path.relative_to(ROOT).as_posix()
            except ValueError:
                sqlite_path = self.db_path.name
        return {
            "driver": self.driver,
            "sqlite_path": sqlite_path,
            "ready": True,
        }


def _safe_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _embed_text(text: str) -> list[float]:
    tokens = [part.lower() for part in text.replace("\n", " ").split() if part]
    buckets = [0.0] * 32
    if not tokens:
        return buckets
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % 32
        buckets[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in buckets)) or 1.0
    return [v / norm for v in buckets]


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return float(sum(left[i] * right[i] for i in range(size)))


_STORAGE: StorageAdapter | None = None


def get_storage() -> StorageAdapter:
    global _STORAGE
    if _STORAGE is None:
        _STORAGE = StorageAdapter()
    return _STORAGE
