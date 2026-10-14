"""Numbers in a text, and whether each one is in given data: the check that no number comes from a model alone.

A model writes from data it was given (tool outputs, facts, sources). Every number of what it wrote must then be in
that data, as written or rounded: "0.08 s" matches 0.077. Lap times count as their seconds (1:18.792 is 78.792).
Numbers written in words ("deux arrêts") are not checked.
"""

import re
from collections.abc import Iterable
from typing import Any

# A lap or race time (1:18.792, 1:42:06.304), or a number with an optional decimal part, with a point or a comma.
_LAP_TIME = re.compile(r"(?<![\d.,:])(?:(\d):)?(\d{1,2}):(\d{2}(?:[.,]\d{1,3})?)(?![\d])")
# Not inside a word (Q1, FP2, S1) unless a position (P2).
_NUMBER = re.compile(r"(?:(?<![\w.,:])|(?<=\bP))(\d+(?:[.,]\d+)?)")


def numbers(text: str) -> list[tuple[str, float, int]]:
    """Each number of a text: as written, its value, its decimals. A lap time counts as its seconds."""
    found = []
    for match in _LAP_TIME.finditer(text):
        hours, minutes, seconds = int(match.group(1) or 0), int(match.group(2)), match.group(3).replace(",", ".")
        decimals = len(seconds.partition(".")[2])
        found.append((match.group(0), hours * 3600 + minutes * 60 + float(seconds), decimals))
    rest = _LAP_TIME.sub(" ", text)
    for match in _NUMBER.finditer(rest):
        written = match.group(1).replace(",", ".")
        found.append((match.group(1), float(written), len(written.partition(".")[2])))
    return found


def unverified_numbers(text: str, data: Any) -> list[str]:
    """The numbers of the text that are not in the data, as written. A number matches a value when the value,
    rounded to the decimals written, gives it: "0.08 s" matches 0.077. Signs are ignored: a gap can be told either
    way. Numbers written in words ("deux arrêts") are not checked."""
    known = {abs(value) for value in _fact_values(data)}
    return [
        written
        for written, value, decimals in numbers(text)
        if not any(abs(round(fact, decimals) - value) < 1e-9 for fact in known)
    ]


def _fact_values(value: Any) -> Iterable[float]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        yield float(value)
    elif isinstance(value, str):
        yield from (number for _, number, _ in numbers(value))
    elif isinstance(value, dict):
        for item in value.values():
            yield from _fact_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _fact_values(item)
