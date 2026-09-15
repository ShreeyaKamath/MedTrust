"""Memory input validation and reproducible structured canonicalization."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from memory.contracts import (
    ConfidenceComponents,
    EntryType,
    EventTime,
    RelationType,
    SelectionRequest,
    SourceReference,
    SourceSnapshot,
)
from memory.provenance import canonical_json, structured_digest


@pytest.mark.parametrize("enum,value", [(EntryType, "diagnosis"), (RelationType, "delete")])
def test_invalid_enums(enum, value):
    with pytest.raises(ValueError):
        enum(value)


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf"), True, "0.5"])
@pytest.mark.parametrize("field", list(ConfidenceComponents.model_fields))
def test_component_bounds(field, value):
    data = dict.fromkeys(ConfidenceComponents.model_fields, 0.5)
    with pytest.raises(ValidationError):
        ConfidenceComponents(**(data | {field: value}))


@pytest.mark.parametrize(
    "data",
    [
        {"precision": "unknown", "date_value": "2020-01-01"},
        {"precision": "date"},
        {"precision": "datetime"},
        {"precision": "datetime", "datetime_value": "2020-01-01T00:00:00"},
        {"precision": "date", "date_value": "2020-01-01", "datetime_value": "2020-01-01T00:00:00Z"},
    ],
)
def test_invalid_event_time(data):
    with pytest.raises(ValidationError):
        EventTime.model_validate(data)


def test_invalid_reference_and_selection():
    with pytest.raises(ValidationError):
        SourceReference(kind="invented", record_id=uuid4(), field="value")
    with pytest.raises(ValidationError):
        SelectionRequest(
            scope_id=uuid4(), case_id=uuid4(), as_of=datetime.now(UTC), max_entries=True
        )


def test_canonicalization_is_structured_and_preserves_whitespace():
    assert structured_digest({"b": 2, "a": "cafe\u0301"}) == structured_digest(
        {"a": "café", "b": 2}
    )
    assert structured_digest("a  b") != structured_digest("a b")
    assert structured_digest([1, 2]) != structured_digest([2, 1])
    assert structured_digest(1) != structured_digest("1")
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})
    with pytest.raises(ValueError):
        canonical_json({"é": 1, "e\u0301": 2})


def test_snapshot_hash_validation(memory_env):
    env = memory_env
    entry = env.ingest(env.observation())
    assert (
        SourceSnapshot.model_validate(entry.snapshot).reference.record_id == entry.source_record_id
    )
    for change in [{"digest": "bad"}, {"value": 900}, {"unknown_field": "forbidden"}]:
        with pytest.raises(ValidationError):
            SourceSnapshot.model_validate(entry.snapshot | change)
