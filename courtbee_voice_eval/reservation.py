import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

FACILITY_PATH = Path(__file__).resolve().parent / "facility.json"

WEEKDAYS = ["pondelok", "utorok", "streda", "štvrtok", "piatok", "sobota", "nedeľa"]


class Reservation(BaseModel):
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_min: int | None = Field(default=None, gt=0)
    court: int | Literal["any"] | None = None
    question: str | None = None

    def missing(self) -> list[str]:
        fields = ("date", "start", "duration_min", "court")
        return [name for name in fields if getattr(self, name) is None]

    def is_complete(self) -> bool:
        return not self.missing()


def load_facility() -> dict:
    return json.loads(FACILITY_PATH.read_text(encoding="utf-8"))


def court_names() -> dict[int, str]:
    return {court["id"]: court["name"] for court in load_facility()["courts"]}


def format_date(value: str) -> str:
    day = date.fromisoformat(value)
    return f"{WEEKDAYS[day.weekday()]} {day.day}. {day.month}. {day.year}"


def format_court(value: int | str) -> str:
    if value == "any":
        return "ktorýkoľvek voľný"
    return court_names().get(value, f"Kurt {value}")
