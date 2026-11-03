from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import ValidationError

from errors import (
    INVALID_CATEGORY,
    INVALID_DATE,
    INVALID_DAY,
    INVALID_DAY_LABEL,
    INVALID_MESSAGE,
    INVALID_NOTE,
    INVALID_PASSWORD,
    INVALID_TOKEN,
    INVALID_TYPE,
    INVALID_VERSION,
    UNKNOWN_MESSAGE,
)
from ws_commands import (
    AuthCommand,
    PopulateWeekendsCommand,
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
    WsCommand,
    WsIncomingCommand,
)

COMMAND_MODELS: dict[str, type[WsCommand]] = {
    "populate_weekends": PopulateWeekendsCommand,
    "auth": AuthCommand,
    "create_category": CreateCategoryCommand,
    "create_day_label": CreateDayLabelCommand,
    "update_category": UpdateCategoryCommand,
    "update_day_label": UpdateDayLabelCommand,
    "delete_category": DeleteCategoryCommand,
    "delete_day_label": DeleteDayLabelCommand,
    "set_day": SetDayCommand,
    "create_note_range": CreateNoteRangeCommand,
    "update_note_range": UpdateNoteRangeCommand,
    "delete_note_range": DeleteNoteRangeCommand,
    "update_password": UpdatePasswordCommand,
}

MESSAGE_ERROR_CODES: dict[str, str] = {
    "auth": INVALID_TOKEN,
    "create_category": INVALID_CATEGORY,
    "update_category": INVALID_CATEGORY,
    "delete_category": INVALID_CATEGORY,
    "create_day_label": INVALID_DAY_LABEL,
    "update_day_label": INVALID_DAY_LABEL,
    "delete_day_label": INVALID_DAY_LABEL,
    "update_note_range": INVALID_NOTE,
    "delete_note_range": INVALID_NOTE,
}

SET_DAY_FIELD_ERRORS: tuple[tuple[set[str], str], ...] = (
    ({"date"}, INVALID_DATE),
    ({"category_id", "categoryId"}, INVALID_CATEGORY),
    (
        {
            "corner_label_id",
            "circle_label_id",
            "label_id",
            "cornerLabelId",
            "circleLabelId",
            "labelId",
        },
        INVALID_DAY_LABEL,
    ),
    ({"expected_version", "expectedVersion"}, INVALID_VERSION),
)

CREATE_NOTE_RANGE_FIELD_ERRORS: tuple[tuple[set[str], str], ...] = (
    ({"start_date", "end_date", "startDate", "endDate"}, INVALID_DATE),
)

UPDATE_PASSWORD_FIELD_ERRORS: tuple[tuple[set[str], str], ...] = (
    ({"expected_version", "expectedVersion"}, INVALID_VERSION),
)


def _validation_error_fields(exc: ValidationError) -> set[str]:
    return {str(error["loc"][0]) for error in exc.errors() if error.get("loc")}


def _first_matching_error(
    fields: set[str],
    rules: tuple[tuple[set[str], str], ...],
) -> Optional[str]:
    for rule_fields, error_code in rules:
        if fields.intersection(rule_fields):
            return error_code
    return None


def _map_validation_error(msg_type: str, exc: ValidationError) -> str:
    fields = _validation_error_fields(exc)

    if msg_type == "set_day":
        return _first_matching_error(fields, SET_DAY_FIELD_ERRORS) or INVALID_DAY
    if msg_type == "create_note_range":
        return _first_matching_error(fields, CREATE_NOTE_RANGE_FIELD_ERRORS) or INVALID_NOTE
    if msg_type == "update_password":
        return _first_matching_error(fields, UPDATE_PASSWORD_FIELD_ERRORS) or INVALID_PASSWORD
    return MESSAGE_ERROR_CODES.get(msg_type, INVALID_MESSAGE)


def parse_message(payload: Dict[str, Any]) -> tuple[str, Optional[WsIncomingCommand], str]:
    msg_type = payload.get("type")
    if not isinstance(msg_type, str):
        return INVALID_TYPE, None, INVALID_TYPE
    model = COMMAND_MODELS.get(msg_type)
    if model is None:
        return UNKNOWN_MESSAGE, None, UNKNOWN_MESSAGE
    try:
        return msg_type, model.model_validate(payload), ""
    except ValidationError as exc:
        return msg_type, None, _map_validation_error(msg_type, exc)
