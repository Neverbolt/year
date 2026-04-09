from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Awaitable, Callable, Optional, Protocol, TypeAlias

import aiosqlite
from aiohttp import web

from errors import CATEGORY_IN_USE, READ_ONLY, VERSION_CONFLICT
from ws_commands import (
    CreateCategoryCommand,
    CreateDayLabelCommand,
    CreateNoteRangeCommand,
    DeleteCategoryCommand,
    DeleteDayLabelCommand,
    DeleteNoteRangeCommand,
    SetDayCommand,
    UpdateCategoryCommand,
    UpdateDayLabelCommand,
    UpdateNoteRangeCommand,
    UpdatePasswordCommand,
)
from ws_messages import (
    CategoryCreatedMessage,
    CategoryDeletedMessage,
    CategoryUpdatedMessage,
    DayDeletedMessage,
    DayLabelCreatedMessage,
    DayLabelDeletedMessage,
    DayLabelUpdatedMessage,
    DayUpdatedMessage,
    NoteRangeCreatedMessage,
    NoteRangeDeletedMessage,
    NoteRangeUpdatedMessage,
    PasswordUpdatedMessage,
)

WsRuntimeCommand: TypeAlias = (
    CreateDayLabelCommand
    | CreateCategoryCommand
    | UpdateDayLabelCommand
    | UpdateCategoryCommand
    | DeleteDayLabelCommand
    | DeleteCategoryCommand
    | SetDayCommand
    | CreateNoteRangeCommand
    | UpdateNoteRangeCommand
    | DeleteNoteRangeCommand
    | UpdatePasswordCommand
)


class AuthenticatedUserProtocol(Protocol):
    is_admin: bool


class WsStateProtocol(Protocol):
    async def create_day_label(self, name: str, color: str, marker_style: str) -> Any: ...
    async def update_day_label(self, label_id: int, name: str, color: str, marker_style: str, expected_version: int) -> Any: ...
    async def delete_day_label(self, label_id: int, expected_version: int) -> None: ...
    async def create_category(self, name: str, color: str) -> Any: ...
    async def update_category(self, category_id: int, name: str, color: str, expected_version: int) -> Any: ...
    async def delete_category(self, category_id: int, expected_version: int) -> None: ...
    async def delete_day(self, date: str, expected_version: Optional[int]) -> None: ...
    async def upsert_day(
        self,
        date: str,
        category_id: Optional[int],
        corner_label_id: Optional[int],
        circle_label_id: Optional[int],
        expected_version: Optional[int],
    ) -> Any: ...
    async def create_note_range(self, start_date: str, end_date: str, note: str) -> Any: ...
    async def update_note_range(self, note_id: int, note: str, expected_version: int) -> Any: ...
    async def delete_note_range(self, note_id: int, expected_version: int) -> None: ...
    async def update_password(self, active_user: Any, current_password: str, new_password: str, expected_version: int) -> Any: ...
    async def refresh_readonly_sessions(self) -> None: ...
    async def broadcast_filtered(self, builder: Callable[[AuthenticatedUserProtocol], Any]) -> None: ...


WsCommandHandler: TypeAlias = Callable[
    [WsStateProtocol, web.WebSocketResponse, AuthenticatedUserProtocol, WsRuntimeCommand],
    Awaitable[None],
]


async def send_ws_error(ws: web.WebSocketResponse, message: str) -> None:
    await ws.send_str(json.dumps({"type": "error", "message": message}))


async def ensure_admin_ws(
    ws: web.WebSocketResponse,
    active_user: AuthenticatedUserProtocol,
) -> bool:
    if active_user.is_admin:
        return True
    await send_ws_error(ws, READ_ONLY)
    return False


async def handle_create_day_label(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: CreateDayLabelCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    day_label = await state.create_day_label(command.name, command.color, command.marker_style)
    await state.broadcast_filtered(
        lambda user: DayLabelCreatedMessage(type="day_label_created", dayLabel=day_label)
    )


async def handle_create_category(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: CreateCategoryCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    category = await state.create_category(command.name, command.color)
    await state.broadcast_filtered(
        lambda user: CategoryCreatedMessage(type="category_created", category=category)
        if user.is_admin
        else None
    )
    await state.refresh_readonly_sessions()


async def handle_update_day_label(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: UpdateDayLabelCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    try:
        day_label = await state.update_day_label(
            command.id,
            command.name,
            command.color,
            command.marker_style,
            command.expected_version,
        )
    except ValueError:
        await send_ws_error(ws, VERSION_CONFLICT)
        return
    await state.broadcast_filtered(
        lambda user: DayLabelUpdatedMessage(type="day_label_updated", dayLabel=day_label)
    )


async def handle_update_category(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: UpdateCategoryCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    try:
        category = await state.update_category(
            command.id,
            command.name,
            command.color,
            command.expected_version,
        )
    except ValueError:
        await send_ws_error(ws, VERSION_CONFLICT)
        return
    await state.broadcast_filtered(
        lambda user: CategoryUpdatedMessage(type="category_updated", category=category)
        if user.is_admin
        else None
    )
    await state.refresh_readonly_sessions()


async def handle_delete_day_label(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: DeleteDayLabelCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    try:
        await state.delete_day_label(command.id, command.expected_version)
    except aiosqlite.IntegrityError:
        await send_ws_error(ws, CATEGORY_IN_USE)
        return
    except ValueError:
        await send_ws_error(ws, VERSION_CONFLICT)
        return
    await state.broadcast_filtered(
        lambda user: DayLabelDeletedMessage(type="day_label_deleted", id=command.id)
    )


async def handle_delete_category(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: DeleteCategoryCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    try:
        await state.delete_category(command.id, command.expected_version)
    except aiosqlite.IntegrityError:
        await send_ws_error(ws, CATEGORY_IN_USE)
        return
    except ValueError:
        await send_ws_error(ws, VERSION_CONFLICT)
        return
    await state.broadcast_filtered(
        lambda user: CategoryDeletedMessage(type="category_deleted", id=command.id)
        if user.is_admin
        else None
    )
    await state.refresh_readonly_sessions()


async def handle_set_day(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: SetDayCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    try:
        if command.category_id is None and command.corner_label_id is None and command.circle_label_id is None:
            await state.delete_day(command.date, command.expected_version)
            await state.broadcast_filtered(
                lambda user: DayDeletedMessage(type="day_deleted", date=command.date)
                if user.is_admin
                else None
            )
            await state.refresh_readonly_sessions()
            return
        entry = await state.upsert_day(
            command.date,
            command.category_id,
            command.corner_label_id,
            command.circle_label_id,
            command.expected_version,
        )
    except ValueError as exc:
        await send_ws_error(ws, str(exc))
        return
    await state.broadcast_filtered(
        lambda user: DayUpdatedMessage(type="day_updated", day=entry)
        if user.is_admin
        else None
    )
    await state.refresh_readonly_sessions()


async def handle_create_note_range(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: CreateNoteRangeCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    try:
        note_range = await state.create_note_range(command.start_date, command.end_date, command.note)
    except ValueError as exc:
        await send_ws_error(ws, str(exc))
        return
    await state.broadcast_filtered(
        lambda user: NoteRangeCreatedMessage(type="note_range_created", noteRange=note_range)
        if user.is_admin
        else None
    )
    await state.refresh_readonly_sessions()


async def handle_update_note_range(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: UpdateNoteRangeCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    try:
        note_range = await state.update_note_range(
            command.id,
            command.note,
            command.expected_version,
        )
    except ValueError as exc:
        await send_ws_error(ws, str(exc))
        return
    await state.broadcast_filtered(
        lambda user: NoteRangeUpdatedMessage(type="note_range_updated", noteRange=note_range)
        if user.is_admin
        else None
    )
    await state.refresh_readonly_sessions()


async def handle_delete_note_range(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: DeleteNoteRangeCommand) -> None:
    if not await ensure_admin_ws(ws, active_user):
        return
    try:
        await state.delete_note_range(command.id, command.expected_version)
    except ValueError as exc:
        await send_ws_error(ws, str(exc))
        return
    await state.broadcast_filtered(
        lambda user: NoteRangeDeletedMessage(type="note_range_deleted", id=command.id)
        if user.is_admin
        else None
    )
    await state.refresh_readonly_sessions()


async def handle_update_password(state: WsStateProtocol, ws: web.WebSocketResponse, active_user: AuthenticatedUserProtocol, command: UpdatePasswordCommand) -> None:
    try:
        user_snapshot = await state.update_password(
            active_user,
            command.current_password,
            command.new_password,
            command.expected_version,
        )
    except ValueError as exc:
        await send_ws_error(ws, str(exc))
        return
    await ws.send_str(
        json.dumps(asdict(PasswordUpdatedMessage(type="password_updated", user=user_snapshot)))
    )


WS_COMMAND_HANDLERS: dict[type[WsRuntimeCommand], WsCommandHandler] = {
    CreateDayLabelCommand: handle_create_day_label,
    CreateCategoryCommand: handle_create_category,
    UpdateDayLabelCommand: handle_update_day_label,
    UpdateCategoryCommand: handle_update_category,
    DeleteDayLabelCommand: handle_delete_day_label,
    DeleteCategoryCommand: handle_delete_category,
    SetDayCommand: handle_set_day,
    CreateNoteRangeCommand: handle_create_note_range,
    UpdateNoteRangeCommand: handle_update_note_range,
    DeleteNoteRangeCommand: handle_delete_note_range,
    UpdatePasswordCommand: handle_update_password,
}
