import json
import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from errors import READ_ONLY, VERSION_CONFLICT
from ws_commands import CreateCategoryCommand, UpdateCategoryCommand
from ws_handlers import handle_create_category, handle_update_category


class FakeWs:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def send_str(self, payload: str) -> None:
        self.messages.append(json.loads(payload))


@dataclass
class FakeUser:
    is_admin: bool


class WsHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_category_requires_admin(self) -> None:
        ws = FakeWs()
        state = SimpleNamespace(
            create_category_called=False,
            broadcast_filtered=lambda *_args, **_kwargs: None,
            refresh_readonly_sessions=lambda: None,
        )

        async def create_category(*_args):
            state.create_category_called = True
            return None

        async def broadcast_filtered(*_args):
            return None

        async def refresh_readonly_sessions():
            return None

        state.create_category = create_category
        state.broadcast_filtered = broadcast_filtered
        state.refresh_readonly_sessions = refresh_readonly_sessions

        command = CreateCategoryCommand(type="create_category", name="A", color="#fff")
        await handle_create_category(state, ws, FakeUser(is_admin=False), command)

        self.assertFalse(state.create_category_called)
        self.assertEqual(ws.messages, [{"type": "error", "message": READ_ONLY}])

    async def test_update_category_maps_version_conflict(self) -> None:
        ws = FakeWs()

        async def update_category(*_args):
            raise ValueError("version_conflict")

        state = SimpleNamespace(update_category=update_category)
        command = UpdateCategoryCommand(
            type="update_category",
            id=1,
            name="A",
            color="#fff",
            expectedVersion=2,
        )

        await handle_update_category(state, ws, FakeUser(is_admin=True), command)

        self.assertEqual(ws.messages, [{"type": "error", "message": VERSION_CONFLICT}])


if __name__ == "__main__":
    unittest.main()
