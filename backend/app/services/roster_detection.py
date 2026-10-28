import re
from dataclasses import dataclass

from app.services.excel_parser import ParsedExcel
from app.services.roster_cells import clean_roster_cell
from app.services.student_matching import detect_student_name


_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_NAME_HEADERS = {"student", "studentname", "name"}
_ROLL_HEADERS = {
    "rollno",
    "rollnumber",
    "enrollment",
    "enrollmentno",
    "enrollmentnumber",
    "regno",
    "registration",
    "registrationno",
}
_TOPIC_HEADERS = {
    "project",
    "topic",
    "topics",
    "title",
    "subject",
    "projecttopics",
}


@dataclass(frozen=True)
class RosterLayout:
    sheet_index: int
    sheet_name: str
    header_row: int
    name_column: int
    roll_column: int | None
    topic_column: int | None
    row_count: int
    distinct_name_count: int


def _header_key(value: str) -> str:
    return _NON_ALPHANUMERIC.sub("", clean_roster_cell(value).text.casefold())


def detect_roster_layouts(
    parsed: ParsedExcel, filename: str = ""
) -> tuple[RosterLayout, ...]:
    layouts: list[RosterLayout] = []
    single_student_signal = detect_student_name(parsed, filename)
    has_single_student_signal = any(
        signal.source == "labeled_cell" and signal.confidence >= 0.9
        for signal in single_student_signal.candidates
    )
    for sheet_index, sheet in enumerate(parsed.sheets):
        source_row_numbers = sheet.source_row_numbers
        for header_index, header in enumerate(sheet.rows[:10]):
            header_row = (
                source_row_numbers[header_index]
                if header_index < len(source_row_numbers)
                else header_index + 1
            )
            if header_row > 10:
                continue
            header_keys = [_header_key(value) for value in header]
            name_columns = [
                index for index, key in enumerate(header_keys) if key in _NAME_HEADERS
            ]
            if not name_columns:
                continue
            name_column = name_columns[0]
            roll_column = next(
                (index for index, key in enumerate(header_keys) if key in _ROLL_HEADERS),
                None,
            )
            topic_column = next(
                (index for index, key in enumerate(header_keys) if key in _TOPIC_HEADERS),
                None,
            )
            names: list[str] = []
            for row in sheet.rows[header_index + 1 :]:
                if name_column >= len(row):
                    continue
                name = clean_roster_cell(row[name_column]).text
                if name:
                    names.append(name)
            distinct_names = {name.casefold() for name in names}
            has_roster_columns = roll_column is not None or topic_column is not None
            enough_names = len(distinct_names) >= 10
            if not (has_roster_columns or enough_names):
                continue
            if has_single_student_signal and len(distinct_names) < 10:
                continue
            layouts.append(
                RosterLayout(
                    sheet_index=sheet_index,
                    sheet_name=sheet.name,
                    header_row=header_row,
                    name_column=name_column,
                    roll_column=roll_column,
                    topic_column=topic_column,
                    row_count=len(names),
                    distinct_name_count=len(distinct_names),
                )
            )
            break
    return tuple(layouts)


def roster_layout_payload(layout: RosterLayout) -> dict[str, int | str | None]:
    return {
        "sheet_index": layout.sheet_index,
        "sheet_name": layout.sheet_name,
        "header_row": layout.header_row,
        "name_column": layout.name_column,
        "roll_column": layout.roll_column,
        "topic_column": layout.topic_column,
        "row_count": layout.row_count,
        "distinct_name_count": layout.distinct_name_count,
    }
