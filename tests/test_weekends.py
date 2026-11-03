import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite

from server import AppState, init_db
from ws_commands import PopulateWeekendsCommand
from ws_handlers import handle_populate_weekends
from ws_parsing import parse_message


class WeekendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(':memory:')
        await init_db(self.db)
        self.state = AppState(self.db)
        self.label = await self.state.create_day_label('Weekend', '#a78bfa', 'corner')

    async def asyncTearDown(self):
        await self.db.close()

    async def test_preserves_categories_notes_other_slots_and_existing_markers(self):
        holiday = await self.state.create_day_label('Holiday', '#fbbf24', 'circle')
        occupied = await self.state.create_day_label('Special', '#ff0000', 'corner')
        category = await self.state.create_category('Time off', '#38bdf8')
        await self.state.upsert_day('2026-01-03', category.id, None, holiday.id, None)
        await self.state.upsert_day('2026-01-04', None, occupied.id, None, None)
        await self.state.create_note_range('2026-01-03', '2026-01-04', 'Keep this')
        self.assertEqual(await self.state.populate_weekends(2026, self.label.id), 103)
        days = {day.date: day for day in await self.state.fetch_days()}
        self.assertEqual((days['2026-01-03'].category_id, days['2026-01-03'].circle_label_id), (category.id, holiday.id))
        self.assertEqual(days['2026-01-04'].corner_label_id, occupied.id)
        self.assertNotIn('2026-01-02', days)
        self.assertTrue(all(day.startswith('2026-') for day in days))
        async with self.db.execute('SELECT note FROM note_ranges') as cursor:
            self.assertEqual((await cursor.fetchone())[0], 'Keep this')
        self.assertEqual(await self.state.populate_weekends(2026, self.label.id), 0)
        self.assertEqual(days, {day.date: day for day in await self.state.fetch_days()})

    async def test_leap_year_and_circle_slot(self):
        label = await self.state.create_day_label('Weekend circle', '#a78bfa', 'circle')
        # Leap year starting on a Saturday has 106 weekend days.
        self.assertEqual(await self.state.populate_weekends(2028, label.id), 106)
        days = await self.state.fetch_days()
        self.assertTrue(all(day.circle_label_id == label.id and day.corner_label_id is None for day in days))

    async def test_missing_label_rolls_back(self):
        with self.assertRaisesRegex(ValueError, 'invalid_day_label'):
            await self.state.populate_weekends(2026, 999)
        self.assertEqual(await self.state.fetch_days(), [])
        self.assertEqual(await self.state.populate_weekends(2026, self.label.id), 104)

    async def test_readonly_cannot_populate(self):
        state = SimpleNamespace(populate_weekends=AsyncMock())
        ws = SimpleNamespace(send_str=AsyncMock())
        await handle_populate_weekends(state, ws, SimpleNamespace(is_admin=False), PopulateWeekendsCommand(year=2026, labelId=1))
        state.populate_weekends.assert_not_awaited()
        self.assertEqual(json.loads(ws.send_str.call_args.args[0])['message'], 'read_only')

    async def test_handler_refreshes_authorized_snapshots_and_acknowledges(self):
        state = SimpleNamespace(populate_weekends=AsyncMock(return_value=104), refresh_all_sessions=AsyncMock())
        ws = SimpleNamespace(send_str=AsyncMock())
        await handle_populate_weekends(state, ws, SimpleNamespace(is_admin=True), PopulateWeekendsCommand(year=2026, labelId=1))
        state.refresh_all_sessions.assert_awaited_once()
        self.assertEqual(json.loads(ws.send_str.call_args.args[0]), {'type': 'weekends_populated', 'year': 2026, 'count': 104})

    async def test_rejects_invalid_years_and_labels(self):
        for payload in [dict(year=True, labelId=1), dict(year=10000, labelId=1), dict(year=0, labelId=1), dict(year=2026, labelId=0), dict(year='2026', labelId=1)]:
            with self.subTest(payload=payload):
                self.assertIsNone(parse_message({'type': 'populate_weekends', **payload})[1])
