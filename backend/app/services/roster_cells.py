import re
import unicodedata
from dataclasses import dataclass
from numbers import Real
from typing import Any


_TOPIC_NUMBER_PREFIX = re.compile(
    r"^(?:topic\s*)?(\d{1,5})\s*(?:[.)]|[-:])\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CleanedRosterCell:
    text: str
    topic_number: int | None = None


def clean_roster_cell(value: Any, *, is_topic: bool = False) -> CleanedRosterCell:
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    text = " ".join(text.split())
    topic_number = None
    if is_topic:
        match = _TOPIC_NUMBER_PREFIX.match(text)
        if match:
            topic_number = int(match.group(1))
            text = text[match.end() :].strip()
    return CleanedRosterCell(text=text, topic_number=topic_number)


def normalize_roll_no(value: Any) -> str | None:
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if numeric.is_integer():
            value = str(int(numeric))
    cleaned = clean_roster_cell(value).text
    if re.fullmatch(r"[+-]?\d+\.0+", cleaned):
        cleaned = cleaned.split(".", 1)[0]
    cleaned = cleaned.upper()
    return cleaned or None
