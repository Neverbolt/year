from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

import aiosqlite
import jwt
from aiohttp import WSMsgType, web
from passlib.context import CryptContext
from errors import AUTH_FAILED, AUTH_REQUIRED, INVALID_JSON, UNKNOWN_MESSAGE
from ws_commands import (
    AuthCommand,
)
from ws_handlers import WS_COMMAND_HANDLERS, send_ws_error
from ws_parsing import parse_message

DB_PATH = os.environ.get("YEAR_DB_PATH", "year.db")
HOST = os.environ.get("YEAR_HOST", "0.0.0.0")
PORT = int(os.environ.get("YEAR_PORT", "8000"))
BOOTSTRAP_PASSWORD = os.environ.get("YEAR_APP_PASSWORD")
BOOTSTRAP_USERS = os.environ.get("YEAR_APP_USERS_JSON")
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get("YEAR_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}
JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALG = "HS256"
SESSION_COOKIE_NAME = "year_session"
READ_ONLY_ROLE = "readonly"
ADMIN_ROLE = "admin"
VALID_ROLES = {ADMIN_ROLE, READ_ONLY_ROLE}
DUMMY_PASSWORD_HASH = "$pbkdf2-sha256$29000$V.pdC6E0JgSglFKK8d57jw$vnA0T0x4iOBVhtSGcVwqDAVBBusZT6F4LmSpaV0t1Ik"

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

COLOR_PALETTE = [
    "#ef4444",
    "#f97316",
    "#f59e0b",
    "#eab308",
    "#84cc16",
    "#22c55e",
    "#14b8a6",
    "#06b6d4",
    "#0ea5e9",
    "#3b82f6",
    "#6366f1",
    "#8b5cf6",
    "#a855f7",
    "#d946ef",
    "#ec4899",
    "#f43f5e",
]


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    color: str
    version: int


@dataclass(frozen=True)
class DayLabel:
    id: int
    name: str
    color: str
    marker_style: str
    version: int


@dataclass(frozen=True)
class DayEntry:
    date: str
    category_id: Optional[int]
    corner_label_id: Optional[int]
    circle_label_id: Optional[int]
    version: int


@dataclass(frozen=True)
class NoteRange:
    id: int
    start_date: str
    end_date: str
    note: str
    version: int


@dataclass(frozen=True)
class UserSnapshot:
    id: int
    version: int
    role: str
    categoryIds: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class ManagedUser:
    id: int
    name: str
    role: str
    isActive: bool
    version: int
    categoryIds: List[int]


@dataclass(frozen=True)
class ErrorMessage:
    type: str
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class SnapshotMessage:
    type: str
    categories: List[Category]
    dayLabels: List[DayLabel]
    days: List[DayEntry]
    noteRanges: List[NoteRange]
    palette: List[str]
    user: UserSnapshot
    serverTime: str


@dataclass(frozen=True)
class UserListMessage:
    type: str
    users: List[ManagedUser]




@dataclass(frozen=True)
class DayLabelCreatedMessage:
    type: str
    dayLabel: DayLabel


@dataclass(frozen=True)
class DayLabelUpdatedMessage:
    type: str
    dayLabel: DayLabel


@dataclass(frozen=True)
class DayLabelDeletedMessage:
    type: str
    id: int


@dataclass(frozen=True)
class CategoryCreatedMessage:
    type: str
    category: Category


@dataclass(frozen=True)
class CategoryUpdatedMessage:
    type: str
    category: Category


@dataclass(frozen=True)
class CategoryDeletedMessage:
    type: str
    id: int


@dataclass(frozen=True)
class DayUpdatedMessage:
    type: str
    day: DayEntry


@dataclass(frozen=True)
class DayDeletedMessage:
    type: str
    date: str


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    name: str
    role: str
    version: int
    category_ids: set[int]

    @property
    def is_admin(self) -> bool:
        return self.role == ADMIN_ROLE


@dataclass(frozen=True)
class WebSocketSession:
    ws: web.WebSocketResponse
    user: AuthenticatedUser


class AuthError(Exception):
    pass


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, stored: str) -> bool:
    return pwd_context.verify(password, stored)


def validate_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in VALID_ROLES:
        raise ValueError("invalid_role")
    return normalized


def category_id_set(values: Iterable[Any]) -> set[int]:
    category_ids: set[int] = set()
    for value in values:
        try:
            category_ids.add(int(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_category") from exc
    return category_ids


def parse_user_payload(data: Dict[str, Any], *, require_password: bool) -> tuple[str, str, Optional[str], set[int]]:
    name = data.get("name")
    role = data.get("role")
    password = data.get("password")
    category_ids = data.get("categoryIds", [])
    if not isinstance(name, str) or not name.strip():
        raise ValueError("invalid_name")
    if not isinstance(role, str):
        raise ValueError("invalid_role")
    if require_password:
        if not isinstance(password, str) or len(password) < 8:
            raise ValueError("password_too_short")
    elif password is not None and (not isinstance(password, str) or len(password) < 8):
        raise ValueError("password_too_short")
    if not isinstance(category_ids, list):
        raise ValueError("invalid_category")
    return name.strip(), validate_role(role), password, category_id_set(category_ids)


def jwt_issue(user: AuthenticatedUser) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def jwt_verify(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError as exc:
        raise AuthError("invalid_token") from exc
    try:
        return int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthError("invalid_token_payload") from exc


def encode_message(message: Any) -> str:
    payload = asdict(message)
    if isinstance(message, ErrorMessage) and message.details is None:
        payload.pop("details", None)
    return json.dumps(payload)


async def ensure_column(db: aiosqlite.Connection, table: str, column: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        rows = await cursor.fetchall()
    return any(row[1] == column for row in rows)

async def day_column_not_null(db: aiosqlite.Connection, column: str) -> bool:
    async with db.execute("PRAGMA table_info(days)") as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        if row[1] == column:
            return bool(row[3])
    return False


async def rebuild_days_table(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS days_new (
            date TEXT PRIMARY KEY,
            category_id INTEGER,
            corner_label_id INTEGER,
            circle_label_id INTEGER,
            version INTEGER NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT,
            FOREIGN KEY (corner_label_id) REFERENCES day_labels(id) ON DELETE RESTRICT,
            FOREIGN KEY (circle_label_id) REFERENCES day_labels(id) ON DELETE RESTRICT
        )
        """
    )
    has_corner_label_id = await ensure_column(db, "days", "corner_label_id")
    has_circle_label_id = await ensure_column(db, "days", "circle_label_id")
    has_legacy_label_id = await ensure_column(db, "days", "label_id")
    if has_corner_label_id and has_circle_label_id:
        await db.execute(
            """
            INSERT INTO days_new (date, category_id, corner_label_id, circle_label_id, version)
            SELECT date, category_id, corner_label_id, circle_label_id, version
            FROM days
            """
        )
    elif has_legacy_label_id:
        await db.execute(
            """
            INSERT INTO days_new (date, category_id, corner_label_id, circle_label_id, version)
            SELECT
                days.date,
                days.category_id,
                CASE WHEN day_labels.marker_style = 'corner' THEN days.label_id ELSE NULL END,
                CASE WHEN day_labels.marker_style = 'circle' THEN days.label_id ELSE NULL END,
                days.version
            FROM days
            LEFT JOIN day_labels ON day_labels.id = days.label_id
            """
        )
    else:
        await db.execute(
            """
            INSERT INTO days_new (date, category_id, corner_label_id, circle_label_id, version)
            SELECT date, category_id, NULL, NULL, version FROM days
            """
        )
    await db.execute("DROP TABLE days")
    await db.execute("ALTER TABLE days_new RENAME TO days")


async def init_db(db: aiosqlite.Connection) -> None:
    await db.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        PRAGMA foreign_keys=ON;
        PRAGMA busy_timeout=5000;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            role TEXT NOT NULL DEFAULT 'admin',
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT NOT NULL,
            created_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS day_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT NOT NULL,
            marker_style TEXT NOT NULL DEFAULT 'corner',
            created_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS days (
            date TEXT PRIMARY KEY,
            category_id INTEGER,
            corner_label_id INTEGER,
            circle_label_id INTEGER,
            version INTEGER NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT,
            FOREIGN KEY (corner_label_id) REFERENCES day_labels(id) ON DELETE RESTRICT,
            FOREIGN KEY (circle_label_id) REFERENCES day_labels(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS note_ranges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            note TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS user_category_permissions (
            user_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, category_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_name ON users(name);
        """
    )
    if not await ensure_column(db, "users", "version"):
        await db.execute("ALTER TABLE users ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
    if not await ensure_column(db, "users", "name"):
        await db.execute("ALTER TABLE users ADD COLUMN name TEXT")
    if not await ensure_column(db, "users", "role"):
        await db.execute(
            "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'"
        )
    if not await ensure_column(db, "users", "is_active"):
        await db.execute(
            "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
        )
    if not await ensure_column(db, "categories", "version"):
        await db.execute(
            "ALTER TABLE categories ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
        )
    if not await ensure_column(db, "day_labels", "version"):
        await db.execute(
            "ALTER TABLE day_labels ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
        )
    if not await ensure_column(db, "day_labels", "marker_style"):
        await db.execute(
            "ALTER TABLE day_labels ADD COLUMN marker_style TEXT NOT NULL DEFAULT 'corner'"
        )
    should_rebuild_days = False
    if not await ensure_column(db, "days", "corner_label_id"):
        should_rebuild_days = True
    if not await ensure_column(db, "days", "circle_label_id"):
        should_rebuild_days = True
    if await day_column_not_null(db, "category_id"):
        should_rebuild_days = True
    if should_rebuild_days:
        await rebuild_days_table(db)
    if await ensure_column(db, "days", "note"):
        await db.execute(
            """
            INSERT INTO note_ranges (start_date, end_date, note, version)
            SELECT date, date, note, 1
            FROM days
            WHERE note IS NOT NULL AND TRIM(note) != ''
            """
        )
        await rebuild_days_table(db)
    await db.commit()


async def ensure_bootstrap_user(db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        row = await cursor.fetchone()
    if row and int(row[0]) > 0:
        return
    bootstrap_users: list[dict[str, Any]] = []
    if BOOTSTRAP_USERS:
        try:
            parsed = json.loads(BOOTSTRAP_USERS)
        except json.JSONDecodeError as exc:
            raise RuntimeError("YEAR_APP_USERS_JSON must be valid JSON") from exc
        if not isinstance(parsed, list) or not parsed:
            raise RuntimeError("YEAR_APP_USERS_JSON must contain at least one user")
        bootstrap_users = [item for item in parsed if isinstance(item, dict)]
        if len(bootstrap_users) != len(parsed):
            raise RuntimeError("YEAR_APP_USERS_JSON entries must be objects")
    elif BOOTSTRAP_PASSWORD:
        bootstrap_users = [{"name": "admin", "password": BOOTSTRAP_PASSWORD, "role": ADMIN_ROLE}]
    else:
        raise RuntimeError(
            "No users found. Set YEAR_APP_PASSWORD or YEAR_APP_USERS_JSON to bootstrap accounts."
        )

    for bootstrap_user in bootstrap_users:
        name, role, password, _ = parse_user_payload(bootstrap_user, require_password=True)
        await db.execute(
            """
            INSERT INTO users (name, role, password_hash, is_active, created_at, version)
            VALUES (?, ?, ?, 1, ?, 1)
            """,
            (name, role, hash_password(password or ""), now_iso()),
        )
    await db.commit()


async def fetch_user_permissions(db: aiosqlite.Connection, user_id: int) -> set[int]:
    permissions: set[int] = set()
    async with db.execute(
        "SELECT category_id FROM user_category_permissions WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        async for row in cursor:
            permissions.add(int(row[0]))
    return permissions


async def get_user_by_id(db: aiosqlite.Connection, user_id: int) -> AuthenticatedUser:
    async with db.execute(
        """
        SELECT id, COALESCE(name, 'user-' || id), role, version, is_active
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row or int(row[4]) != 1:
        raise AuthError("invalid_user")
    permissions = await fetch_user_permissions(db, int(row[0]))
    return AuthenticatedUser(
        id=int(row[0]),
        name=str(row[1]),
        role=str(row[2]),
        version=int(row[3]),
        category_ids=permissions,
    )


async def find_user_by_password(db: aiosqlite.Connection, password: str) -> Optional[AuthenticatedUser]:
    rows: list[tuple[int, str, str, str, int]] = []
    async with db.execute(
        """
        SELECT id, COALESCE(name, 'user-' || id), role, password_hash, version
        FROM users
        WHERE is_active = 1
        ORDER BY id
        """
    ) as cursor:
        async for row in cursor:
            rows.append((int(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4])))
    matches: list[AuthenticatedUser] = []
    for user_id, name, role, password_hash, version in rows:
        matched = verify_password(password, password_hash)
        if matched:
            permissions = await fetch_user_permissions(db, user_id)
            matches.append(
                AuthenticatedUser(
                    id=user_id,
                    name=name,
                    role=role,
                    version=version,
                    category_ids=permissions,
                )
            )
    if not rows:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    if len(matches) != 1:
        return None
    return matches[0]


class AppState:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        self._sessions: List[WebSocketSession] = []
        self._lock = asyncio.Lock()

    async def register_ws(self, ws: web.WebSocketResponse, user: AuthenticatedUser) -> None:
        async with self._lock:
            self._sessions.append(WebSocketSession(ws=ws, user=user))

    async def unregister_ws(self, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            self._sessions = [session for session in self._sessions if session.ws is not ws]

    async def _snapshot_sessions(self) -> List[WebSocketSession]:
        async with self._lock:
            return list(self._sessions)

    async def _send_ws(
        self,
        ws: web.WebSocketResponse,
        payload: str,
        dead: List[web.WebSocketResponse],
    ) -> None:
        if ws.closed:
            dead.append(ws)
            return
        try:
            await asyncio.wait_for(ws.send_str(payload), timeout=2)
        except (asyncio.TimeoutError, ConnectionResetError):
            dead.append(ws)

    async def send_to_user(self, user_id: int, message: Any) -> None:
        payload = encode_message(message)
        dead: List[web.WebSocketResponse] = []
        for session in await self._snapshot_sessions():
            if session.user.id == user_id:
                await self._send_ws(session.ws, payload, dead)
        if dead:
            await self.unregister_dead(dead)

    async def unregister_dead(self, dead: List[web.WebSocketResponse]) -> None:
        async with self._lock:
            self._sessions = [session for session in self._sessions if session.ws not in dead]

    async def broadcast_filtered(self, builder) -> None:
        sessions = await self._snapshot_sessions()
        dead: List[web.WebSocketResponse] = []
        tasks = []
        for session in sessions:
            message = builder(session.user)
            if message is None:
                continue
            tasks.append(asyncio.create_task(self._send_ws(session.ws, encode_message(message), dead)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if dead:
            await self.unregister_dead(dead)

    async def fetch_day_labels(self) -> List[DayLabel]:
        labels: List[DayLabel] = []
        async with self.db.execute(
            "SELECT id, name, color, marker_style, version FROM day_labels ORDER BY id"
        ) as cursor:
            async for row in cursor:
                labels.append(
                    DayLabel(
                        int(row[0]),
                        str(row[1]),
                        str(row[2]),
                        str(row[3]),
                        int(row[4]),
                    )
                )
        return labels

    async def fetch_categories(self, user: Optional[AuthenticatedUser] = None) -> List[Category]:
        query = "SELECT id, name, color, version FROM categories"
        params: tuple[Any, ...] = ()
        if user and not user.is_admin:
            allowed = sorted(user.category_ids)
            if not allowed:
                return []
            placeholders = ",".join("?" for _ in allowed)
            query += f" WHERE id IN ({placeholders})"
            params = tuple(allowed)
        query += " ORDER BY id"
        categories: List[Category] = []
        async with self.db.execute(query, params) as cursor:
            async for row in cursor:
                categories.append(Category(int(row[0]), str(row[1]), str(row[2]), int(row[3])))
        return categories

    async def fetch_days(self, user: Optional[AuthenticatedUser] = None) -> List[DayEntry]:
        query = "SELECT date, category_id, corner_label_id, circle_label_id, version FROM days"
        params: tuple[Any, ...] = ()
        if user and not user.is_admin:
            allowed = sorted(user.category_ids)
            if not allowed:
                return []
            placeholders = ",".join("?" for _ in allowed)
            query += f" WHERE category_id IN ({placeholders})"
            params = tuple(allowed)
        query += " ORDER BY date"
        days: List[DayEntry] = []
        async with self.db.execute(query, params) as cursor:
            async for row in cursor:
                days.append(
                    DayEntry(
                        str(row[0]),
                        int(row[1]) if row[1] is not None else None,
                        int(row[2]) if row[2] is not None else None,
                        int(row[3]) if row[3] is not None else None,
                        int(row[4]),
                    )
                )
        return days

    async def fetch_note_ranges(self, user: Optional[AuthenticatedUser] = None) -> List[NoteRange]:
        notes: List[NoteRange] = []
        if user and not user.is_admin:
            allowed = sorted(user.category_ids)
            if not allowed:
                return []
            placeholders = ",".join("?" for _ in allowed)
            query = f"""
                SELECT
                    note_ranges.id,
                    MIN(days.date) AS visible_start_date,
                    MAX(days.date) AS visible_end_date,
                    note_ranges.note,
                    note_ranges.version
                FROM note_ranges
                JOIN days
                    ON days.date BETWEEN note_ranges.start_date AND note_ranges.end_date
                WHERE days.category_id IN ({placeholders})
                GROUP BY note_ranges.id, note_ranges.note, note_ranges.version
                ORDER BY visible_start_date, visible_end_date, note_ranges.id
            """
            async with self.db.execute(query, tuple(allowed)) as cursor:
                async for row in cursor:
                    if row[1] is None or row[2] is None:
                        continue
                    notes.append(
                        NoteRange(int(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]))
                    )
            return notes

        query = (
            "SELECT id, start_date, end_date, note, version FROM note_ranges "
            "ORDER BY start_date, end_date, id"
        )
        async with self.db.execute(query) as cursor:

            async for row in cursor:
                notes.append(
                    NoteRange(int(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]))
                )
        return notes

    async def build_snapshot(self, user: AuthenticatedUser) -> SnapshotMessage:
        fresh_user = await get_user_by_id(self.db, user.id)
        categories = await self.fetch_categories(fresh_user)
        day_labels = await self.fetch_day_labels()
        days = await self.fetch_days(fresh_user)
        note_ranges = await self.fetch_note_ranges(fresh_user)
        return SnapshotMessage(
            type="snapshot",
            categories=categories,
            dayLabels=day_labels,
            days=days,
            noteRanges=note_ranges,
            palette=COLOR_PALETTE,
            user=UserSnapshot(
                id=fresh_user.id,
                version=fresh_user.version,
                role=fresh_user.role,
                categoryIds=sorted(fresh_user.category_ids),
            ),
            serverTime=now_iso(),
        )

    async def refresh_sessions_for_user_ids(self, user_ids: Iterable[int]) -> None:
        for user_id in set(user_ids):
            try:
                user = await get_user_by_id(self.db, user_id)
            except AuthError:
                continue
            await self.send_to_user(user_id, await self.build_snapshot(user))

    async def refresh_readonly_sessions(self) -> None:
        readonly_user_ids = {
            session.user.id for session in await self._snapshot_sessions() if not session.user.is_admin
        }
        await self.refresh_sessions_for_user_ids(readonly_user_ids)

    async def create_day_label(self, name: str, color: str, marker_style: str) -> DayLabel:
        await self.db.execute("BEGIN")
        try:
            await self.db.execute(
                """
                INSERT INTO day_labels (name, color, marker_style, created_at, version)
                VALUES (?, ?, ?, ?, 1)
                """,
                (name, color, marker_style, now_iso()),
            )
            async with self.db.execute("SELECT last_insert_rowid()") as cursor:
                row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("Failed to fetch day label id")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return DayLabel(int(row[0]), name, color, marker_style, 1)

    async def update_day_label(
        self, label_id: int, name: str, color: str, marker_style: str, expected_version: int
    ) -> DayLabel:
        await self.db.execute("BEGIN")
        try:
            cursor = await self.db.execute(
                """
                UPDATE day_labels
                SET name = ?, color = ?, marker_style = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (name, color, marker_style, label_id, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return DayLabel(label_id, name, color, marker_style, expected_version + 1)

    async def delete_day_label(self, label_id: int, expected_version: int) -> None:
        await self.db.execute("BEGIN")
        try:
            cursor = await self.db.execute(
                "DELETE FROM day_labels WHERE id = ? AND version = ?",
                (label_id, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def create_category(self, name: str, color: str) -> Category:
        await self.db.execute("BEGIN")
        try:
            await self.db.execute(
                "INSERT INTO categories (name, color, created_at, version) VALUES (?, ?, ?, 1)",
                (name, color, now_iso()),
            )
            async with self.db.execute("SELECT last_insert_rowid()") as cursor:
                row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("Failed to fetch category id")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return Category(int(row[0]), name, color, 1)

    async def update_category(
        self, category_id: int, name: str, color: str, expected_version: int
    ) -> Category:
        await self.db.execute("BEGIN")
        try:
            cursor = await self.db.execute(
                """
                UPDATE categories
                SET name = ?, color = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (name, color, category_id, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return Category(category_id, name, color, expected_version + 1)

    async def delete_category(self, category_id: int, expected_version: int) -> None:
        await self.db.execute("BEGIN")
        try:
            cursor = await self.db.execute(
                "DELETE FROM categories WHERE id = ? AND version = ?",
                (category_id, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def upsert_day(
        self,
        date: str,
        category_id: Optional[int],
        corner_label_id: Optional[int],
        circle_label_id: Optional[int],
        expected_version: Optional[int],
    ) -> DayEntry:
        await self.db.execute("BEGIN")
        try:
            if expected_version in (None, 0):
                cursor = await self.db.execute(
                    """
                    INSERT INTO days (date, category_id, corner_label_id, circle_label_id, version)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(date) DO NOTHING
                    """,
                    (date, category_id, corner_label_id, circle_label_id),
                )
                if cursor.rowcount != 1:
                    await self.db.rollback()
                    raise ValueError("version_conflict")
                await self.db.commit()
                return DayEntry(date, category_id, corner_label_id, circle_label_id, 1)
            cursor = await self.db.execute(
                """
                UPDATE days
                SET category_id = ?, corner_label_id = ?, circle_label_id = ?, version = version + 1
                WHERE date = ? AND version = ?
                """,
                (category_id, corner_label_id, circle_label_id, date, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        if expected_version is None:
            raise RuntimeError("Missing expected version for update")
        return DayEntry(date, category_id, corner_label_id, circle_label_id, expected_version + 1)

    async def delete_day(self, date: str, expected_version: Optional[int]) -> None:
        if expected_version is None:
            raise ValueError("invalid_version")
        await self.db.execute("BEGIN")
        try:
            cursor = await self.db.execute(
                "DELETE FROM days WHERE date = ? AND version = ?",
                (date, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def create_note_range(self, start_date: str, end_date: str, note: str) -> NoteRange:
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        await self.db.execute("BEGIN")
        try:
            async with self.db.execute(
                """
                SELECT 1
                FROM note_ranges
                WHERE NOT (end_date < ? OR start_date > ?)
                LIMIT 1
                """,
                (start_date, end_date),
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                await self.db.rollback()
                raise ValueError("note_range_overlap")
            cursor = await self.db.execute(
                "INSERT INTO note_ranges (start_date, end_date, note, version) VALUES (?, ?, ?, 1)",
                (start_date, end_date, note),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise RuntimeError("note_create_failed")
            async with self.db.execute("SELECT last_insert_rowid()") as id_cursor:
                id_row = await id_cursor.fetchone()
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return NoteRange(int(id_row[0]), start_date, end_date, note, 1)

    async def update_note_range(
        self, note_id: int, note: str, expected_version: int
    ) -> NoteRange:
        await self.db.execute("BEGIN")
        try:
            cursor = await self.db.execute(
                """
                UPDATE note_ranges
                SET note = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (note, note_id, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            async with self.db.execute(
                "SELECT id, start_date, end_date, note, version FROM note_ranges WHERE id = ?",
                (note_id,),
            ) as range_cursor:
                row = await range_cursor.fetchone()
            if not row:
                await self.db.rollback()
                raise ValueError("note_not_found")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return NoteRange(int(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]))

    async def delete_note_range(self, note_id: int, expected_version: int) -> None:
        await self.db.execute("BEGIN")
        try:
            cursor = await self.db.execute(
                "DELETE FROM note_ranges WHERE id = ? AND version = ?",
                (note_id, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def update_password(
        self,
        user: AuthenticatedUser,
        current_password: str,
        new_password: str,
        expected_version: int,
    ) -> UserSnapshot:
        if not user.is_admin:
            raise ValueError("read_only")
        if len(new_password) < 8:
            raise ValueError("password_too_short")
        await self.db.execute("BEGIN")
        try:
            async with self.db.execute(
                "SELECT password_hash, version FROM users WHERE id = ?",
                (user.id,),
            ) as cursor:
                row = await cursor.fetchone()
            if not row or not verify_password(current_password, str(row[0])):
                await self.db.rollback()
                raise ValueError("invalid_credentials")
            current_version = int(row[1])
            if current_version != expected_version:
                await self.db.rollback()
                raise ValueError("version_conflict")
            cursor = await self.db.execute(
                """
                UPDATE users
                SET password_hash = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (hash_password(new_password), user.id, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return UserSnapshot(
            id=user.id,
            version=expected_version + 1,
            role=user.role,
            categoryIds=sorted(user.category_ids),
        )

    async def list_managed_users(self) -> List[ManagedUser]:
        users: dict[int, ManagedUser] = {}
        async with self.db.execute(
            "SELECT id, COALESCE(name, 'user-' || id), role, is_active, version FROM users ORDER BY id"
        ) as cursor:
            async for row in cursor:
                users[int(row[0])] = ManagedUser(
                    id=int(row[0]),
                    name=str(row[1]),
                    role=str(row[2]),
                    isActive=bool(row[3]),
                    version=int(row[4]),
                    categoryIds=[],
                )
        async with self.db.execute(
            "SELECT user_id, category_id FROM user_category_permissions ORDER BY user_id, category_id"
        ) as cursor:
            async for row in cursor:
                user = users.get(int(row[0]))
                if user:
                    user.categoryIds.append(int(row[1]))
        return list(users.values())

    async def _assert_categories_exist(self, category_ids: set[int]) -> None:
        if not category_ids:
            return
        placeholders = ",".join("?" for _ in category_ids)
        async with self.db.execute(
            f"SELECT id FROM categories WHERE id IN ({placeholders})",
            tuple(sorted(category_ids)),
        ) as cursor:
            found = {int(row[0]) async for row in cursor}
        if found != category_ids:
            raise ValueError("invalid_category")

    async def create_managed_user(
        self,
        name: str,
        role: str,
        password: str,
        category_ids: set[int],
    ) -> ManagedUser:
        if role == ADMIN_ROLE and category_ids:
            raise ValueError("admin_permissions_not_supported")
        await self._assert_categories_exist(category_ids)
        await self.db.execute("BEGIN")
        try:
            cursor = await self.db.execute(
                """
                INSERT INTO users (name, role, password_hash, is_active, created_at, version)
                VALUES (?, ?, ?, 1, ?, 1)
                """,
                (name, role, hash_password(password), now_iso()),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise RuntimeError("user_create_failed")
            async with self.db.execute("SELECT last_insert_rowid()") as id_cursor:
                row = await id_cursor.fetchone()
            user_id = int(row[0])
            for category_id in sorted(category_ids):
                await self.db.execute(
                    "INSERT INTO user_category_permissions (user_id, category_id) VALUES (?, ?)",
                    (user_id, category_id),
                )
            await self.db.commit()
        except aiosqlite.IntegrityError as exc:
            await self.db.rollback()
            raise ValueError("duplicate_user") from exc
        except Exception:
            await self.db.rollback()
            raise
        return ManagedUser(
            id=user_id,
            name=name,
            role=role,
            isActive=True,
            version=1,
            categoryIds=sorted(category_ids),
        )

    async def update_managed_user(
        self,
        user_id: int,
        *,
        expected_version: int,
        role: str,
        category_ids: set[int],
        password: Optional[str],
        is_active: bool,
    ) -> ManagedUser:
        if role == ADMIN_ROLE and category_ids:
            raise ValueError("admin_permissions_not_supported")
        await self._assert_categories_exist(category_ids)
        await self.db.execute("BEGIN")
        try:
            async with self.db.execute(
                "SELECT id FROM users WHERE id = ? AND version = ?",
                (user_id, expected_version),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                await self.db.rollback()
                raise ValueError("version_conflict")
            params: list[Any] = [role, int(is_active)]
            sql = "UPDATE users SET role = ?, is_active = ?, version = version + 1"
            if password is not None:
                sql += ", password_hash = ?"
                params.append(hash_password(password))
            sql += " WHERE id = ? AND version = ?"
            params.extend([user_id, expected_version])
            cursor = await self.db.execute(sql, tuple(params))
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.execute(
                "DELETE FROM user_category_permissions WHERE user_id = ?",
                (user_id,),
            )
            for category_id in sorted(category_ids):
                await self.db.execute(
                    "INSERT INTO user_category_permissions (user_id, category_id) VALUES (?, ?)",
                    (user_id, category_id),
                )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        async with self.db.execute(
            "SELECT COALESCE(name, 'user-' || id) FROM users WHERE id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return ManagedUser(
            id=user_id,
            name=str(row[0]),
            role=role,
            isActive=is_active,
            version=expected_version + 1,
            categoryIds=sorted(category_ids),
        )


def ensure_origin_allowed(request: web.Request) -> None:
    if not ALLOWED_ORIGINS:
        return
    origin = request.headers.get("Origin")
    if origin and origin not in ALLOWED_ORIGINS:
        raise web.HTTPForbidden(text="Origin not allowed")


def token_from_request(request: web.Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME, "").strip()
    if cookie_token:
        return cookie_token
    raise web.HTTPUnauthorized(text="Missing session")


async def require_http_user(request: web.Request) -> AuthenticatedUser:
    user_id = jwt_verify(token_from_request(request))
    return await get_user_by_id(request.app["db"], user_id)


def ensure_admin(user: AuthenticatedUser) -> None:
    if not user.is_admin:
        raise web.HTTPForbidden(text="Admin access required")


async def login_handler(request: web.Request) -> web.Response:
    ensure_origin_allowed(request)
    data = await request.json()
    password = str(data.get("password", ""))
    user = await find_user_by_password(request.app["db"], password)
    if user is None:
        raise web.HTTPUnauthorized(text="Invalid credentials")
    token = jwt_issue(user)
    response = web.json_response({"role": user.role})
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="Strict",
        secure=request.secure,
        path="/",
        max_age=60 * 60 * 24 * 14,
    )
    return response




async def logout_handler(request: web.Request) -> web.Response:
    ensure_origin_allowed(request)
    response = web.json_response({"ok": True})
    response.del_cookie(SESSION_COOKIE_NAME, path="/")
    return response


async def me_handler(request: web.Request) -> web.Response:
    ensure_origin_allowed(request)
    user = await require_http_user(request)
    return web.json_response(
        asdict(
            UserSnapshot(
                id=user.id,
                version=user.version,
                role=user.role,
                categoryIds=sorted(user.category_ids),
            )
        )
    )


async def list_users_handler(request: web.Request) -> web.Response:
    ensure_origin_allowed(request)
    user = await require_http_user(request)
    ensure_admin(user)
    state: AppState = request.app["state"]
    return web.json_response({"users": [asdict(item) for item in await state.list_managed_users()]})


async def create_user_handler(request: web.Request) -> web.Response:
    ensure_origin_allowed(request)
    admin = await require_http_user(request)
    ensure_admin(admin)
    payload = await request.json()
    try:
        name, role, password, category_ids = parse_user_payload(payload, require_password=True)
        state: AppState = request.app["state"]
        user = await state.create_managed_user(name, role, password or "", category_ids)
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc)) from exc
    await state.refresh_sessions_for_user_ids([admin.id])
    return web.json_response(asdict(user), status=201)


async def update_user_handler(request: web.Request) -> web.Response:
    ensure_origin_allowed(request)
    admin = await require_http_user(request)
    ensure_admin(admin)
    payload = await request.json()
    expected_value = payload.get("expectedVersion")
    is_active = payload.get("isActive")
    if not isinstance(expected_value, (int, str)):
        raise web.HTTPBadRequest(text="invalid_version")
    if not isinstance(is_active, bool):
        raise web.HTTPBadRequest(text="invalid_active")
    try:
        expected_version = int(expected_value)
        user_id = int(request.match_info["user_id"])
        name, role, password, category_ids = parse_user_payload(payload, require_password=False)
        state: AppState = request.app["state"]
        user = await state.update_managed_user(
            user_id,
            expected_version=expected_version,
            role=role,
            category_ids=category_ids,
            password=password,
            is_active=is_active,
        )
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc)) from exc
    await state.refresh_sessions_for_user_ids([user_id, admin.id])
    return web.json_response(asdict(user))


async def auth_ws(
    ws: web.WebSocketResponse,
    db: aiosqlite.Connection,
    request: web.Request,
) -> Optional[AuthenticatedUser]:
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME, "").strip()
    if cookie_token:
        try:
            return await get_user_by_id(db, jwt_verify(cookie_token))
        except AuthError:
            await ws.send_str(
                encode_message(ErrorMessage(type="error", message=AUTH_FAILED))
            )

    for _ in range(3):
        msg = await ws.receive()
        if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
            return None
        if msg.type != WSMsgType.TEXT:
            await ws.send_str(
                encode_message(ErrorMessage(type="error", message=AUTH_REQUIRED))
            )
            continue
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            await ws.send_str(
                encode_message(ErrorMessage(type="error", message=INVALID_JSON))
            )
            continue
        msg_type, parsed, _error = parse_message(payload)
        if msg_type != "auth" or not isinstance(parsed, AuthCommand):
            await ws.send_str(
                encode_message(ErrorMessage(type="error", message=AUTH_REQUIRED))
            )
            continue
        try:
            return await get_user_by_id(db, jwt_verify(parsed.token))
        except AuthError:
            await ws.send_str(
                encode_message(ErrorMessage(type="error", message=AUTH_FAILED))
            )
            continue
    await ws.close(code=4001, message=b"auth_failed")
    return None


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ensure_origin_allowed(request)
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    state: AppState = request.app["state"]

    authed_user = await auth_ws(ws, state.db, request)
    if authed_user is None:
        return ws

    await state.register_ws(ws, authed_user)
    await ws.send_str(encode_message(await state.build_snapshot(authed_user)))

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                payload = json.loads(msg.data)
            except json.JSONDecodeError:
                await ws.send_str(
                    encode_message(ErrorMessage(type="error", message=INVALID_JSON))
                )
                continue
            msg_type, parsed, error = parse_message(payload)
            if parsed is None:
                await ws.send_str(
                    encode_message(
                        ErrorMessage(type="error", message=error or "invalid_message")
                    )
                )
                continue
            try:
                active_user = await get_user_by_id(state.db, authed_user.id)
            except AuthError:
                await ws.send_str(
                    encode_message(ErrorMessage(type="error", message=AUTH_FAILED))
                )
                break
            handler = WS_COMMAND_HANDLERS.get(type(parsed))
            if handler is None:
                await send_ws_error(ws, UNKNOWN_MESSAGE)
                continue
            await handler(state, ws, active_user, parsed)
            continue
        if msg.type == WSMsgType.ERROR:
            break

    await state.unregister_ws(ws)
    return ws


async def index_handler(request: web.Request) -> web.StreamResponse:
    ensure_origin_allowed(request)
    return web.FileResponse(path="static/index.html")


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def create_app() -> web.Application:
    app = web.Application()
    db = await aiosqlite.connect(DB_PATH)
    await init_db(db)
    await ensure_bootstrap_user(db)

    state = AppState(db)
    app["state"] = state
    app["db"] = db

    app.router.add_get("/", index_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_post("/api/login", login_handler)
    app.router.add_post("/api/logout", logout_handler)
    app.router.add_get("/api/me", me_handler)
    app.router.add_get("/api/users", list_users_handler)
    app.router.add_post("/api/users", create_user_handler)
    app.router.add_put("/api/users/{user_id}", update_user_handler)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static/", path="static", name="static")

    async def close_db(app: web.Application) -> None:
        await app["db"].close()

    app.on_cleanup.append(close_db)  # type: ignore[arg-type]
    return app


def main() -> None:
    web.run_app(create_app(), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
