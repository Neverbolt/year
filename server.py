from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import aiosqlite
import jwt
from aiohttp import WSMsgType, web
from passlib.context import CryptContext

DB_PATH = os.environ.get("YEAR_DB_PATH", "year.db")
HOST = os.environ.get("YEAR_HOST", "0.0.0.0")
PORT = int(os.environ.get("YEAR_PORT", "8000"))
BOOTSTRAP_PASSWORD = os.environ.get("YEAR_APP_PASSWORD")
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get("YEAR_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}
JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALG = "HS256"

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
class DayEntry:
    date: str
    category_id: int
    note: Optional[str]
    version: int


@dataclass(frozen=True)
class UserSnapshot:
    id: int
    version: int


@dataclass(frozen=True)
class ErrorMessage:
    type: str
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class SnapshotMessage:
    type: str
    categories: List[Category]
    days: List[DayEntry]
    palette: List[str]
    user: UserSnapshot
    serverTime: str


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
class PasswordUpdatedMessage:
    type: str
    user: UserSnapshot


@dataclass(frozen=True)
class AuthMessage:
    token: str

    @staticmethod
    def parse(payload: Dict[str, Any]) -> Tuple[Optional["AuthMessage"], str]:
        token = payload.get("token")
        if not isinstance(token, str):
            return None, "invalid_token"
        return AuthMessage(token=token), ""


@dataclass(frozen=True)
class CreateCategoryMessage:
    name: str
    color: str

    @staticmethod
    def parse(payload: Dict[str, Any]) -> Tuple[Optional["CreateCategoryMessage"], str]:
        name = payload.get("name")
        color = payload.get("color")
        if not isinstance(name, str) or not isinstance(color, str):
            return None, "invalid_category"
        name = name.strip()
        color = color.strip()
        if not name or not color:
            return None, "invalid_category"
        return CreateCategoryMessage(name=name, color=color), ""


@dataclass(frozen=True)
class UpdateCategoryMessage:
    id: int
    name: str
    color: str
    expected_version: int

    @staticmethod
    def parse(payload: Dict[str, Any]) -> Tuple[Optional["UpdateCategoryMessage"], str]:
        category_value = payload.get("id")
        version_value = payload.get("expectedVersion")
        if not isinstance(category_value, (int, str)) or not isinstance(
            version_value, (int, str)
        ):
            return None, "invalid_category"
        try:
            category_id = int(category_value)
            expected_version = int(version_value)
        except (TypeError, ValueError):
            return None, "invalid_category"
        name = payload.get("name")
        color = payload.get("color")
        if not isinstance(name, str) or not isinstance(color, str):
            return None, "invalid_category"
        name = name.strip()
        color = color.strip()
        if not name or not color:
            return None, "invalid_category"
        return UpdateCategoryMessage(
            id=category_id,
            name=name,
            color=color,
            expected_version=expected_version,
        ), ""


@dataclass(frozen=True)
class DeleteCategoryMessage:
    id: int
    expected_version: int

    @staticmethod
    def parse(payload: Dict[str, Any]) -> Tuple[Optional["DeleteCategoryMessage"], str]:
        category_value = payload.get("id")
        version_value = payload.get("expectedVersion")
        if not isinstance(category_value, (int, str)) or not isinstance(
            version_value, (int, str)
        ):
            return None, "invalid_category"
        try:
            category_id = int(category_value)
            expected_version = int(version_value)
        except (TypeError, ValueError):
            return None, "invalid_category"
        return DeleteCategoryMessage(id=category_id, expected_version=expected_version), ""


@dataclass(frozen=True)
class SetDayMessage:
    date: str
    category_id: Optional[int]
    note: Optional[str]
    expected_version: Optional[int]

    @staticmethod
    def parse(payload: Dict[str, Any]) -> Tuple[Optional["SetDayMessage"], str]:
        date = payload.get("date")
        if not isinstance(date, str) or not date:
            return None, "invalid_date"
        category_value = payload.get("categoryId")
        if category_value in (None, "", 0):
            category_id = None
        else:
            if not isinstance(category_value, (int, str)):
                return None, "invalid_category"
            try:
                category_id = int(category_value)
            except (TypeError, ValueError):
                return None, "invalid_category"
        note = payload.get("note")
        if note is not None and not isinstance(note, str):
            return None, "invalid_note"
        expected_value = payload.get("expectedVersion")
        expected_version = None
        if expected_value is not None:
            if not isinstance(expected_value, (int, str)):
                return None, "invalid_version"
            try:
                expected_version = int(expected_value)
            except (TypeError, ValueError):
                return None, "invalid_version"
        if category_id is None and expected_version is None:
            return None, "invalid_version"
        return SetDayMessage(
            date=date,
            category_id=category_id,
            note=note,
            expected_version=expected_version,
        ), ""


@dataclass(frozen=True)
class UpdatePasswordMessage:
    current_password: str
    new_password: str
    expected_version: int

    @staticmethod
    def parse(payload: Dict[str, Any]) -> Tuple[Optional["UpdatePasswordMessage"], str]:
        current_password = payload.get("currentPassword")
        new_password = payload.get("newPassword")
        expected_value = payload.get("expectedVersion")
        if not isinstance(expected_value, (int, str)):
            return None, "invalid_version"
        try:
            expected_version = int(expected_value)
        except (TypeError, ValueError):
            return None, "invalid_version"
        if not isinstance(current_password, str) or not isinstance(new_password, str):
            return None, "invalid_password"
        return UpdatePasswordMessage(
            current_password=current_password,
            new_password=new_password,
            expected_version=expected_version,
        ), ""


class AuthError(Exception):
    pass


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, stored: str) -> bool:
    return pwd_context.verify(password, stored)


def jwt_issue(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
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


async def init_db(db: aiosqlite.Connection) -> None:
    await db.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        PRAGMA foreign_keys=ON;
        PRAGMA busy_timeout=5000;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            password_hash TEXT NOT NULL,
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

        CREATE TABLE IF NOT EXISTS days (
            date TEXT PRIMARY KEY,
            category_id INTEGER NOT NULL,
            note TEXT,
            version INTEGER NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT
        );
        """
    )
    if not await ensure_column(db, "users", "version"):
        await db.execute("ALTER TABLE users ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
    if not await ensure_column(db, "categories", "version"):
        await db.execute(
            "ALTER TABLE categories ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
        )
    await db.commit()


async def ensure_bootstrap_user(db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT id FROM users LIMIT 1") as cursor:
        row = await cursor.fetchone()
    if row:
        return
    if not BOOTSTRAP_PASSWORD:
        raise RuntimeError(
            "No users found. Set YEAR_APP_PASSWORD to bootstrap the first account."
        )
    password_hash = hash_password(BOOTSTRAP_PASSWORD)
    await db.execute(
        "INSERT INTO users (password_hash, created_at, version) VALUES (?, ?, 1)",
        (password_hash, now_iso()),
    )
    await db.commit()


async def get_user(db: aiosqlite.Connection) -> tuple[int, str, int]:
    async with db.execute(
        "SELECT id, password_hash, version FROM users LIMIT 1"
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("No user configured")
    return int(row[0]), str(row[1]), int(row[2])


def parse_message(payload: Dict[str, Any]) -> tuple[str, Any, str]:
    msg_type = payload.get("type")
    if not isinstance(msg_type, str):
        return "invalid_type", None, "invalid_type"
    parser_map = {
        "auth": AuthMessage.parse,
        "create_category": CreateCategoryMessage.parse,
        "update_category": UpdateCategoryMessage.parse,
        "delete_category": DeleteCategoryMessage.parse,
        "set_day": SetDayMessage.parse,
        "update_password": UpdatePasswordMessage.parse,
    }
    parser = parser_map.get(msg_type)
    if parser is None:
        return "unknown_message", None, "unknown_message"
    parsed, error = parser(payload)
    return msg_type, parsed, error


class AppState:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        self._websockets: List[web.WebSocketResponse] = []
        self._lock = asyncio.Lock()

    async def register_ws(self, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            self._websockets.append(ws)

    async def unregister_ws(self, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            if ws in self._websockets:
                self._websockets.remove(ws)

    async def _snapshot_websockets(self) -> List[web.WebSocketResponse]:
        async with self._lock:
            return list(self._websockets)

    async def broadcast(self, message: Any) -> None:
        payload = encode_message(message)
        websockets = await self._snapshot_websockets()
        dead: List[web.WebSocketResponse] = []
        send_tasks = [
            asyncio.create_task(self._send_ws(ws, payload, dead)) for ws in websockets
        ]
        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)
        if dead:
            async with self._lock:
                self._websockets = [ws for ws in self._websockets if ws not in dead]

    async def _send_ws(
        self, ws: web.WebSocketResponse, payload: str, dead: List[web.WebSocketResponse]
    ) -> None:
        if ws.closed:
            dead.append(ws)
            return
        try:
            await asyncio.wait_for(ws.send_str(payload), timeout=2)
        except (asyncio.TimeoutError, ConnectionResetError):
            dead.append(ws)

    async def fetch_categories(self) -> List[Category]:
        categories: List[Category] = []
        async with self.db.execute(
            "SELECT id, name, color, version FROM categories ORDER BY id"
        ) as cursor:
            async for row in cursor:
                categories.append(
                    Category(int(row[0]), str(row[1]), str(row[2]), int(row[3]))
                )
        return categories

    async def fetch_days(self) -> List[DayEntry]:
        days: List[DayEntry] = []
        async with self.db.execute(
            "SELECT date, category_id, note, version FROM days ORDER BY date"
        ) as cursor:
            async for row in cursor:
                days.append(DayEntry(str(row[0]), int(row[1]), row[2], int(row[3])))
        return days

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
        category_id: int,
        note: Optional[str],
        expected_version: Optional[int],
    ) -> DayEntry:
        await self.db.execute("BEGIN")
        try:
            if expected_version in (None, 0):
                cursor = await self.db.execute(
                    """
                    INSERT INTO days (date, category_id, note, version)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(date) DO NOTHING
                    """,
                    (date, category_id, note),
                )
                if cursor.rowcount != 1:
                    await self.db.rollback()
                    raise ValueError("version_conflict")
                await self.db.commit()
                return DayEntry(date, category_id, note, 1)
            cursor = await self.db.execute(
                """
                UPDATE days
                SET category_id = ?, note = ?, version = version + 1
                WHERE date = ? AND version = ?
                """,
                (category_id, note, date, expected_version),
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
        return DayEntry(date, category_id, note, expected_version + 1)

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

    async def update_password(
        self,
        current_password: str,
        new_password: str,
        expected_version: int,
    ) -> UserSnapshot:
        if len(new_password) < 8:
            raise ValueError("password_too_short")
        await self.db.execute("BEGIN")
        try:
            user_id, password_hash, current_version = await get_user(self.db)
            if not verify_password(current_password, password_hash):
                await self.db.rollback()
                raise ValueError("invalid_credentials")
            if current_version != expected_version:
                await self.db.rollback()
                raise ValueError("version_conflict")
            new_hash = hash_password(new_password)
            cursor = await self.db.execute(
                """
                UPDATE users
                SET password_hash = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (new_hash, user_id, expected_version),
            )
            if cursor.rowcount != 1:
                await self.db.rollback()
                raise ValueError("version_conflict")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return UserSnapshot(id=user_id, version=expected_version + 1)


def ensure_origin_allowed(request: web.Request) -> None:
    if not ALLOWED_ORIGINS:
        return
    origin = request.headers.get("Origin")
    if origin and origin not in ALLOWED_ORIGINS:
        raise web.HTTPForbidden(text="Origin not allowed")


async def login_handler(request: web.Request) -> web.Response:
    ensure_origin_allowed(request)
    data = await request.json()
    password = str(data.get("password", ""))
    user_id, password_hash, _ = await get_user(request.app["db"])
    if not verify_password(password, password_hash):
        raise web.HTTPUnauthorized(text="Invalid credentials")
    token = jwt_issue(user_id)
    return web.json_response({"token": token})


async def auth_ws(ws: web.WebSocketResponse) -> Optional[int]:
    for _ in range(3):
        msg = await ws.receive()
        if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
            return None
        if msg.type != WSMsgType.TEXT:
            await ws.send_str(
                encode_message(ErrorMessage(type="error", message="auth_required"))
            )
            continue
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            await ws.send_str(
                encode_message(ErrorMessage(type="error", message="invalid_json"))
            )
            continue
        msg_type, parsed, error = parse_message(payload)
        if msg_type != "auth" or not isinstance(parsed, AuthMessage):
            await ws.send_str(
                encode_message(ErrorMessage(type="error", message="auth_required"))
            )
            continue
        try:
            return jwt_verify(parsed.token)
        except AuthError:
            await ws.send_str(
                encode_message(ErrorMessage(type="error", message="auth_failed"))
            )
            continue
    await ws.close(code=4001, message=b"auth_failed")
    return None


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ensure_origin_allowed(request)
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    state: AppState = request.app["state"]

    authed_user = await auth_ws(ws)
    if authed_user is None:
        return ws

    await state.register_ws(ws)

    categories = await state.fetch_categories()
    days = await state.fetch_days()
    user_id, _, user_version = await get_user(state.db)
    await ws.send_str(
        encode_message(
            SnapshotMessage(
                type="snapshot",
                categories=categories,
                days=days,
                palette=COLOR_PALETTE,
                user=UserSnapshot(id=user_id, version=user_version),
                serverTime=now_iso(),
            )
        )
    )

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                payload = json.loads(msg.data)
            except json.JSONDecodeError:
                await ws.send_str(
                    encode_message(ErrorMessage(type="error", message="invalid_json"))
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
            match parsed:
                case CreateCategoryMessage(name=name, color=color):
                    category = await state.create_category(name, color)
                    await state.broadcast(
                        CategoryCreatedMessage(
                            type="category_created", category=category
                        )
                    )
                case UpdateCategoryMessage(
                    id=category_id,
                    name=name,
                    color=color,
                    expected_version=expected_version,
                ):
                    try:
                        category = await state.update_category(
                            category_id,
                            name,
                            color,
                            expected_version,
                        )
                    except ValueError:
                        await ws.send_str(
                            encode_message(
                                ErrorMessage(type="error", message="version_conflict")
                            )
                        )
                        continue
                    await state.broadcast(
                        CategoryUpdatedMessage(
                            type="category_updated", category=category
                        )
                    )
                case DeleteCategoryMessage(id=category_id, expected_version=expected_version):
                    try:
                        await state.delete_category(
                            category_id, expected_version
                        )
                    except aiosqlite.IntegrityError:
                        await ws.send_str(
                            encode_message(
                                ErrorMessage(type="error", message="category_in_use")
                            )
                        )
                        continue
                    except ValueError:
                        await ws.send_str(
                            encode_message(
                                ErrorMessage(type="error", message="version_conflict")
                            )
                        )
                        continue
                    await state.broadcast(
                        CategoryDeletedMessage(type="category_deleted", id=category_id)
                    )
                case SetDayMessage(
                    date=date,
                    category_id=category_id,
                    note=note,
                    expected_version=expected_version,
                ):
                    try:
                        if category_id is None:
                            await state.delete_day(
                                date, expected_version
                            )
                            await state.broadcast(
                                DayDeletedMessage(type="day_deleted", date=date)
                            )
                        else:
                            entry = await state.upsert_day(
                                date,
                                category_id,
                                note,
                                expected_version,
                            )
                            await state.broadcast(
                                DayUpdatedMessage(type="day_updated", day=entry)
                            )
                    except ValueError as exc:
                        await ws.send_str(
                            encode_message(
                                ErrorMessage(type="error", message=str(exc))
                            )
                        )
                        continue
                case UpdatePasswordMessage(
                    current_password=current_password,
                    new_password=new_password,
                    expected_version=expected_version,
                ):
                    try:
                        user = await state.update_password(
                            current_password,
                            new_password,
                            expected_version,
                        )
                    except ValueError as exc:
                        await ws.send_str(
                            encode_message(
                                ErrorMessage(type="error", message=str(exc))
                            )
                        )
                        continue
                    await ws.send_str(
                        encode_message(
                            PasswordUpdatedMessage(type="password_updated", user=user)
                        )
                    )
                case _:
                    await ws.send_str(
                        encode_message(
                            ErrorMessage(type="error", message="unknown_message")
                        )
                    )
            continue
        elif msg.type == WSMsgType.ERROR:
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
