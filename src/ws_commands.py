from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VALID_MARKER_STYLES = {"corner", "circle"}


def _to_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("invalid_int")
    return int(value)


def _to_optional_entity_id(value: Any) -> Optional[int]:
    if value in (None, "", 0):
        return None
    return _to_int(value)


class ParseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class WsCommand(ParseModel):
    type: str


class VersionedIdCommand(WsCommand):
    id: int
    expected_version: int = Field(alias="expectedVersion")

    @field_validator("id", "expected_version", mode="before")
    @classmethod
    def parse_int_fields(cls, value: Any) -> int:
        return _to_int(value)


class AuthCommand(WsCommand):
    type: Literal["auth"] = "auth"
    token: str


class CreateCategoryCommand(WsCommand):
    type: Literal["create_category"] = "create_category"
    name: str
    color: str

    @field_validator("name", "color")
    @classmethod
    def normalize_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty")
        return value


class UpdateCategoryCommand(VersionedIdCommand):
    type: Literal["update_category"] = "update_category"
    name: str
    color: str

    @field_validator("name", "color")
    @classmethod
    def normalize_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty")
        return value


class DeleteCategoryCommand(VersionedIdCommand):
    type: Literal["delete_category"] = "delete_category"


class DeleteDayLabelCommand(VersionedIdCommand):
    type: Literal["delete_day_label"] = "delete_day_label"


class SetDayCommand(WsCommand):
    type: Literal["set_day"] = "set_day"
    date: str
    category_id: Optional[int] = Field(default=None, alias="categoryId")
    corner_label_id: Optional[int] = Field(default=None, alias="cornerLabelId")
    circle_label_id: Optional[int] = Field(default=None, alias="circleLabelId")
    label_id: Optional[int] = Field(default=None, alias="labelId")
    expected_version: Optional[int] = Field(default=None, alias="expectedVersion")

    @field_validator("date")
    @classmethod
    def require_date(cls, value: str) -> str:
        if not value:
            raise ValueError("invalid_date")
        return value

    @field_validator(
        "category_id",
        "corner_label_id",
        "circle_label_id",
        "label_id",
        mode="before",
    )
    @classmethod
    def parse_optional_entity_id(cls, value: Any) -> Optional[int]:
        return _to_optional_entity_id(value)

    @field_validator("expected_version", mode="before")
    @classmethod
    def parse_expected_version(cls, value: Any) -> Optional[int]:
        if value is None:
            return None
        return _to_int(value)

    @model_validator(mode="after")
    def apply_legacy_label(self) -> "SetDayCommand":
        if self.corner_label_id is None and self.circle_label_id is None and self.label_id is not None:
            self.corner_label_id = self.label_id
        if (
            self.category_id is None
            and self.corner_label_id is None
            and self.circle_label_id is None
            and self.expected_version is None
        ):
            raise ValueError("invalid_day")
        return self


class CreateDayLabelCommand(WsCommand):
    type: Literal["create_day_label"] = "create_day_label"
    name: str
    color: str
    marker_style: str = Field(default="corner", alias="markerStyle")

    @field_validator("name", "color")
    @classmethod
    def normalize_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty")
        return value

    @field_validator("marker_style")
    @classmethod
    def normalize_marker_style(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in VALID_MARKER_STYLES:
            raise ValueError("invalid_marker_style")
        return value


class UpdateDayLabelCommand(VersionedIdCommand):
    type: Literal["update_day_label"] = "update_day_label"
    name: str
    color: str
    marker_style: str = Field(default="corner", alias="markerStyle")

    @field_validator("name", "color")
    @classmethod
    def normalize_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty")
        return value

    @field_validator("marker_style")
    @classmethod
    def normalize_marker_style(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in VALID_MARKER_STYLES:
            raise ValueError("invalid_marker_style")
        return value


class CreateNoteRangeCommand(WsCommand):
    type: Literal["create_note_range"] = "create_note_range"
    start_date: str = Field(alias="startDate")
    end_date: str = Field(alias="endDate")
    note: str

    @field_validator("start_date", "end_date", "note")
    @classmethod
    def normalize_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty")
        return value


class DeleteNoteRangeCommand(VersionedIdCommand):
    type: Literal["delete_note_range"] = "delete_note_range"


class UpdateNoteRangeCommand(VersionedIdCommand):
    type: Literal["update_note_range"] = "update_note_range"
    note: str

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty")
        return value


class UpdatePasswordCommand(WsCommand):
    type: Literal["update_password"] = "update_password"
    current_password: str = Field(alias="currentPassword")
    new_password: str = Field(alias="newPassword")
    expected_version: int = Field(alias="expectedVersion")

    @field_validator("expected_version", mode="before")
    @classmethod
    def parse_expected_version(cls, value: Any) -> int:
        return _to_int(value)


WsIncomingCommand = (
    AuthCommand
    | CreateCategoryCommand
    | UpdateCategoryCommand
    | DeleteCategoryCommand
    | DeleteDayLabelCommand
    | SetDayCommand
    | CreateDayLabelCommand
    | UpdateDayLabelCommand
    | CreateNoteRangeCommand
    | UpdateNoteRangeCommand
    | DeleteNoteRangeCommand
    | UpdatePasswordCommand
)
