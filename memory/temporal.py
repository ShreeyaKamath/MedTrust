"""Explicit temporal precision and transparent research confidence components."""

from datetime import UTC, datetime

from memory.contracts import ConfidenceComponents, EntryType, EventTime


def event_visible(event: EventTime, as_of: datetime) -> bool:
    if event.precision == "datetime":
        return event.datetime_value <= as_of
    if event.precision == "date":
        # Date-only data applies to the supplied calendar day; no midnight is invented.
        return event.date_value <= as_of.astimezone(UTC).date()
    return True


def confidence(
    kind: EntryType, event: EventTime, as_of: datetime, freshness_days: int, contradicted: bool
) -> ConfidenceComponents:
    if event.precision == "datetime":
        age = max(0.0, (as_of - event.datetime_value).total_seconds() / 86400)
    elif event.precision == "date":
        age = max(0, (as_of.astimezone(UTC).date() - event.date_value).days)
    else:
        age = None
    return ConfidenceComponents(
        source_quality=1.0 if kind == EntryType.SOURCE_FACT else 0.0,
        provenance_completeness=1.0,
        freshness=max(0.0, 1.0 - age / freshness_days) if age is not None else 0.0,
        temporal_reliability={"datetime": 1.0, "date": 0.5, "unknown": 0.0}[event.precision],
        consistency=0.0 if contradicted else 1.0,
    )
