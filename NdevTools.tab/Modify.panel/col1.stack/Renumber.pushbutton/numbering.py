# -*- coding: utf-8 -*-
"""Exact sequence arithmetic shared by all NdevTools Renumber categories."""

import re
from decimal import Decimal, InvalidOperation, localcontext

try:
    _text = unicode
except NameError:
    _text = str

_NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
_VALUE = re.compile(r"^(?:" + _NUMBER + r")$")
_ITEM = re.compile(
    r"^\s*(" + _NUMBER + r")(?:\s*(?:-|to)\s*(" + _NUMBER + r"))?\s*$", re.I
)


class Exclusions(list):
    """Numeric intervals plus exact identifiers and identifier ranges."""

    def __init__(self):
        list.__init__(self)
        self.identifiers = set()
        self.identifier_ranges = []


def _identifier_key(value):
    """Order like identifier counters: A, B, ... Z, AA; A2 before A10."""
    result = []
    for part in re.findall(r"[0-9]+|[A-Za-z]+|[^A-Za-z0-9]+", value):
        if part.isdigit():
            result.append((0, int(part)))
        elif part.isalpha() and re.match(r"^[A-Za-z]+$", part):
            rank = 0
            for char in part.upper():
                rank = rank * 26 + ord(char) - ord("A") + 1
            result.append((1, rank))
        else:
            result.append((2, part))
    return tuple(result)


def _identifier_shape(value):
    return re.sub(r"[0-9]+", "#", re.sub(r"[A-Za-z]+", "@", value))


def numeric_value(text):
    """Return an exact numeric identifier, or None for a letter-based identifier."""
    text = _text(text).strip()
    return Decimal(text) if _VALUE.match(text) else None


def parse_exclusions(text):
    """Accept literal identifiers, numeric ranges and matching identifier ranges.

    Commas separate entries. Double quotes force a literal, including commas
    and identifiers that would otherwise be interpreted as ranges.
    """
    result = Exclusions()
    if not text.strip():
        return result
    intervals = []
    tokens = re.findall(r'\s*"(?:[^"]|"")*"|[^,]+', text)
    for item in tokens:
        item = item.strip()
        if not item:
            continue
        if item.startswith('"') and item.endswith('"'):
            result.identifiers.add(item[1:-1].replace('""', '"'))
            continue
        match = _ITEM.match(item)
        if not match:
            endpoints = re.split(r"\s+to\s+|\s*-\s*", item, flags=re.I)
            if (
                len(endpoints) == 2
                and all(endpoints)
                and _identifier_shape(endpoints[0]) == _identifier_shape(endpoints[1])
                and re.search(r"[A-Za-z0-9]", endpoints[0])
            ):
                first, last = map(_identifier_key, endpoints)
                if last < first:
                    raise ValueError('Range "{}" must run from smaller to larger.'.format(item))
                result.identifier_ranges.append((_identifier_shape(endpoints[0]), first, last))
            else:
                result.identifiers.add(item)
            continue
        first = Decimal(match.group(1))
        last = Decimal(match.group(2)) if match.group(2) else first
        if last < first:
            raise ValueError('Range "{}" must run from smaller to larger.'.format(item))
        intervals.append((first, last))
    merged = []
    for first, last in sorted(intervals):
        if merged and first <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(last, merged[-1][1]))
        else:
            merged.append((first, last))
    result.extend(merged)
    return result


def is_excluded(number, exclusions):
    """Match literal identifiers, identifier ranges, or numeric intervals."""
    number = _text(number).strip()
    if number in getattr(exclusions, "identifiers", ()):
        return True
    if any(
        shape == _identifier_shape(number) and first <= _identifier_key(number) <= last
        for shape, first, last in getattr(exclusions, "identifier_ranges", ())
    ):
        return True
    value = numeric_value(number)
    return value is not None and any(
        first <= value <= last for first, last in exclusions
    )


def next_room_number(number, exclusions, increment):
    """Preserve room suffix counting while bypassing excluded numeric replacements."""
    if numeric_value(number) is None:
        candidate = increment(number)
        seen = set([number])
        while is_excluded(candidate, exclusions):
            if candidate in seen:
                raise ValueError("The identifier counter cannot advance past the exclusions.")
            seen.add(candidate)
            candidate = increment(candidate)
        return candidate
    return NumberSequence(
        number, exclusions=exclusions, increment=increment, skip_initial=False
    ).advance()


def _precision(text):
    return len(text.split(".")[1]) if "." in text else 0


class NumberSequence(object):
    """Advance on the configured decimal lattice without any document access.

    Letter-based identifiers retain pyRevit's original Increase by 1 behavior.
    Numeric output keeps leading zeroes and the precision of start and step.
    """

    def __init__(
        self,
        start,
        step="1",
        direction="increase",
        exclusions=(),
        increment=None,
        skip_initial=True,
    ):
        self.start = _text(start).strip()
        self.step_text = _text(step).strip()
        if not self.start:
            raise ValueError("Enter a starting number.")
        try:
            self.step = Decimal(self.step_text)
        except InvalidOperation:
            raise ValueError("Step must be a positive number, such as 1, 2 or 0.2.")
        if (
            not self.step.is_finite()
            or self.step <= 0
            or not _VALUE.match(self.step_text)
        ):
            raise ValueError("Step must be a positive number greater than zero.")
        if direction not in ("increase", "decrease"):
            raise ValueError("Choose Increase or Decrease.")
        self.direction = direction
        self.exclusions = exclusions
        self.increment = increment
        self.value = numeric_value(self.start)
        self.places = max(_precision(self.start), _precision(self.step_text))
        unsigned = self.start.lstrip("+-")
        integer_part = unsigned.split(".")[0]
        self.width = (
            len(integer_part)
            if len(integer_part) > 1 and integer_part.startswith("0")
            else 1
        )
        self.plus_sign = self.start.startswith("+")
        self.number = self.start
        if self.value is None:
            if self.step != 1 or direction != "increase":
                raise ValueError(
                    "Letter-based identifiers support Increase by 1. Excluded identifiers and ranges are allowed."
                )
            if increment is None:
                raise ValueError("The original identifier counter is unavailable.")
            if skip_initial and is_excluded(self.number, exclusions):
                self.advance()
        else:
            with localcontext() as context:
                context.prec = self._context_precision()
                if skip_initial:
                    self.value = self._allowed(self.value)
                self.number = self._format(self.value)
                while is_excluded(self.number, exclusions):
                    self.advance()

    def _context_precision(self):
        values = [self.value, self.step]
        values.extend(bound for interval in self.exclusions for bound in interval)
        return max(
            28,
            sum(
                len(value.as_tuple().digits) + abs(value.as_tuple().exponent)
                for value in values
            )
            + self.places
            + 16,
        )

    def _allowed(self, value):
        intervals = (
            self.exclusions
            if self.direction == "increase"
            else reversed(self.exclusions)
        )
        for first, last in intervals:
            if first <= value <= last:
                distance = (
                    last - value if self.direction == "increase" else value - first
                )
                jumps = (distance // self.step) + 1
                value += self.step * jumps * (1 if self.direction == "increase" else -1)
        return value

    def _format(self, value):
        text = format(abs(value), ".{}f".format(self.places))
        parts = text.split(".")
        parts[0] = parts[0].zfill(self.width)
        text = ".".join(parts)
        return ("-" if value < 0 else "+" if self.plus_sign else "") + text

    def advance(self):
        """Consume one configured step and bypass exclusions in either direction."""
        if self.value is None:
            seen = set([self.number])
            candidate = self.increment(self.number)
            while is_excluded(candidate, self.exclusions):
                if candidate in seen:
                    raise ValueError("The identifier counter cannot advance past the exclusions.")
                seen.add(candidate)
                candidate = self.increment(candidate)
            self.number = candidate
            return self.number
        with localcontext() as context:
            context.prec = self._context_precision()
            delta = self.step if self.direction == "increase" else -self.step
            self.value = self._allowed(self.value + delta)
            self.number = self._format(self.value)
            while is_excluded(self.number, self.exclusions):
                self.value = self._allowed(self.value + delta)
                self.number = self._format(self.value)
        return self.number

    def next_from(self, number):
        """Find a displaced element's next value using its own original formatting."""
        other = NumberSequence(
            number,
            self.step_text,
            self.direction,
            self.exclusions,
            self.increment,
            skip_initial=False,
        )
        return other.advance()
