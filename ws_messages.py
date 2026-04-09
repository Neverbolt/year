from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server import Category, DayEntry, DayLabel, NoteRange, UserSnapshot


@dataclass(frozen=True)
class DayLabelCreatedMessage:
    type: str
    dayLabel: "DayLabel"


@dataclass(frozen=True)
class DayLabelUpdatedMessage:
    type: str
    dayLabel: "DayLabel"


@dataclass(frozen=True)
class DayLabelDeletedMessage:
    type: str
    id: int


@dataclass(frozen=True)
class CategoryCreatedMessage:
    type: str
    category: "Category"


@dataclass(frozen=True)
class CategoryUpdatedMessage:
    type: str
    category: "Category"


@dataclass(frozen=True)
class CategoryDeletedMessage:
    type: str
    id: int


@dataclass(frozen=True)
class DayUpdatedMessage:
    type: str
    day: "DayEntry"


@dataclass(frozen=True)
class DayDeletedMessage:
    type: str
    date: str


@dataclass(frozen=True)
class NoteRangeCreatedMessage:
    type: str
    noteRange: "NoteRange"


@dataclass(frozen=True)
class NoteRangeUpdatedMessage:
    type: str
    noteRange: "NoteRange"


@dataclass(frozen=True)
class NoteRangeDeletedMessage:
    type: str
    id: int


@dataclass(frozen=True)
class PasswordUpdatedMessage:
    type: str
    user: "UserSnapshot"
