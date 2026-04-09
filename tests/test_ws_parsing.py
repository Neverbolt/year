import unittest

from ws_commands import AuthCommand, CreateCategoryCommand, DeleteDayLabelCommand, SetDayCommand
from ws_parsing import parse_message


class ParseMessageTests(unittest.TestCase):
    def test_auth_message_is_parsed_to_typed_command(self) -> None:
        msg_type, parsed, error = parse_message({"type": "auth", "token": "abc"})
        self.assertEqual(msg_type, "auth")
        self.assertEqual(error, "")
        self.assertIsInstance(parsed, AuthCommand)
        assert isinstance(parsed, AuthCommand)
        self.assertEqual(parsed.token, "abc")

    def test_create_category_trims_values(self) -> None:
        msg_type, parsed, error = parse_message(
            {"type": "create_category", "name": "  Work ", "color": " #f00 "}
        )
        self.assertEqual(msg_type, "create_category")
        self.assertEqual(error, "")
        self.assertIsInstance(parsed, CreateCategoryCommand)
        assert isinstance(parsed, CreateCategoryCommand)
        self.assertEqual(parsed.name, "Work")
        self.assertEqual(parsed.color, "#f00")

    def test_set_day_supports_legacy_label_id(self) -> None:
        msg_type, parsed, error = parse_message(
            {"type": "set_day", "date": "2026-01-01", "labelId": "3"}
        )
        self.assertEqual(msg_type, "set_day")
        self.assertEqual(error, "")
        self.assertIsInstance(parsed, SetDayCommand)
        assert isinstance(parsed, SetDayCommand)
        self.assertEqual(parsed.corner_label_id, 3)
        self.assertIsNone(parsed.circle_label_id)

    def test_set_day_invalid_expected_version_maps_to_existing_error(self) -> None:
        msg_type, parsed, error = parse_message(
            {"type": "set_day", "date": "2026-01-01", "expectedVersion": "not-an-int"}
        )
        self.assertEqual(msg_type, "set_day")
        self.assertIsNone(parsed)
        self.assertEqual(error, "invalid_version")

    def test_note_range_invalid_dates_still_return_invalid_date(self) -> None:
        msg_type, parsed, error = parse_message(
            {"type": "create_note_range", "startDate": "", "endDate": "2026-01-31", "note": "n"}
        )
        self.assertEqual(msg_type, "create_note_range")
        self.assertIsNone(parsed)
        self.assertEqual(error, "invalid_date")

    def test_delete_day_label_is_distinct_command(self) -> None:
        msg_type, parsed, error = parse_message(
            {"type": "delete_day_label", "id": "4", "expectedVersion": "2"}
        )
        self.assertEqual(msg_type, "delete_day_label")
        self.assertEqual(error, "")
        self.assertIsInstance(parsed, DeleteDayLabelCommand)
        assert isinstance(parsed, DeleteDayLabelCommand)
        self.assertEqual(parsed.id, 4)
        self.assertEqual(parsed.expected_version, 2)

    def test_invalid_update_password_payload_maps_to_invalid_password(self) -> None:
        msg_type, parsed, error = parse_message(
            {
                "type": "update_password",
                "currentPassword": 123,
                "newPassword": "password-2",
                "expectedVersion": "1",
            }
        )
        self.assertEqual(msg_type, "update_password")
        self.assertIsNone(parsed)
        self.assertEqual(error, "invalid_password")

    def test_unknown_message_type_returns_unknown_message(self) -> None:
        msg_type, parsed, error = parse_message({"type": "does_not_exist"})
        self.assertEqual(msg_type, "unknown_message")
        self.assertIsNone(parsed)
        self.assertEqual(error, "unknown_message")


if __name__ == "__main__":
    unittest.main()
