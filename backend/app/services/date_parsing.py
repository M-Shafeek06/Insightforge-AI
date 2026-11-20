from __future__ import annotations

import re
from typing import Optional

import pandas as pd


# Explicit column-name hints take precedence over value-based inference.
_NAME_FORMATS = (
    (re.compile(r"(?:^|[_\\W])(?:US|AMERICAN)(?:[_\\W]|$)|MM[_-]?DD[_-]?YYYY", re.I), "%m/%d/%Y"),
    (re.compile(r"(?:^|[_\\W])(?:UK|EU|EUROPEAN)(?:[_\\W]|$)|DD[_-]?MM[_-]?YYYY", re.I), "%d/%m/%Y"),
    (re.compile(r"YYYY[_-]?MM[_-]?DD", re.I), "%Y-%m-%d"),
    (re.compile(r"YYYYMMDD", re.I), "%Y%m%d"),
)

_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y%m%d",
)


class DateFormatAmbiguityError(ValueError):
    """Raised when dates cannot be interpreted without guessing."""


def _parse_with_format(values: pd.Series, date_format: str) -> pd.Series:
    return pd.to_datetime(values, format=date_format, errors="coerce")


def parse_date_series(
    series: pd.Series,
    column: Optional[str] = None,
    *,
    allow_ambiguous: bool = False,
) -> pd.Series:
    """
    Parse mixed date representations independently and deterministically.

    Each non-empty value is tested against supported formats. A value is
    accepted only when all matching formats agree on the same timestamp.
    Ambiguous slash dates remain NaT rather than being guessed. If the
    entire populated column is ambiguous and no value can be safely parsed,
    raise DateFormatAmbiguityError so the caller can request a format choice.
    """
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return series.copy()

    non_null = series.dropna()
    if non_null.empty:
        return pd.to_datetime(series, errors="coerce")

    if pd.api.types.is_numeric_dtype(series.dtype):
        raise ValueError("Numeric columns require an explicit date encoding.")

    text = series.astype("string").str.strip()
    non_empty = text.notna() & text.ne("")
    if not non_empty.any():
        return pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    values = text[non_empty]
    if values.str.fullmatch(r"[+-]?\\d+(?:\\.\\d+)?").all():
        raise ValueError("Numeric-only values require an explicit date encoding.")

    # A declared source format is authoritative. Do not silently reinterpret
    # values under other formats when the column name explicitly specifies one.
    if column:
        for pattern, hinted_format in _NAME_FORMATS:
            if pattern.search(str(column)):
                return _parse_with_format(text, hinted_format)

    parsed_by_format = [
        _parse_with_format(text, fmt)
        for fmt in _FORMATS
    ]

    output = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    safely_parsed = 0
    ambiguous_values = []

    for index in values.index:
        candidates = []
        for parsed in parsed_by_format:
            value = parsed.loc[index]
            if pd.notna(value):
                timestamp = pd.Timestamp(value)
                if timestamp not in candidates:
                    candidates.append(timestamp)

        if len(candidates) == 1:
            output.loc[index] = candidates[0]
            safely_parsed += 1
        elif len(candidates) > 1:
            ambiguous_values.append(str(text.loc[index]))

    if ambiguous_values and safely_parsed == 0 and not allow_ambiguous:
        raise DateFormatAmbiguityError(
            f"Column '{column or series.name or 'column'}' contains an "
            "ambiguous date format that cannot be determined safely. "
            "Specify the source format."
        )

    return output
