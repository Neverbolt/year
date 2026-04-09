import unittest

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
from ws_handlers import WS_COMMAND_HANDLERS


class WsRegistryTests(unittest.TestCase):
    def test_handlers_registered_for_all_runtime_commands(self) -> None:
        expected_commands = {
            CreateDayLabelCommand,
            CreateCategoryCommand,
            UpdateDayLabelCommand,
            UpdateCategoryCommand,
            DeleteDayLabelCommand,
            DeleteCategoryCommand,
            SetDayCommand,
            CreateNoteRangeCommand,
            UpdateNoteRangeCommand,
            DeleteNoteRangeCommand,
            UpdatePasswordCommand,
        }
        self.assertEqual(set(WS_COMMAND_HANDLERS), expected_commands)


if __name__ == "__main__":
    unittest.main()
