"""Temporal selection, conservative contradiction rules, and explicit heuristics."""

from datetime import UTC, date, datetime, timedelta

import pytest

from backend.app.models import Medication
from memory.contracts import EntryType, EventTime, RelationType, SelectionRequest, SourceReference
from memory.temporal import confidence, event_visible


def test_availability_and_future_event_cutoffs(memory_env):
    e = memory_env
    old_time = e.clock.now
    initial = e.ingest(e.observation(100, when=old_time - timedelta(days=1)))
    future_event = e.ingest(e.observation(200, when=old_time + timedelta(days=2)))
    assert [i.id for i in e.selection().entries] == [initial.id]
    e.clock.now += timedelta(days=1)
    later = e.ingest(e.observation(300, when=old_time - timedelta(days=1)))
    historical = e.service.select(
        SelectionRequest(scope_id=e.scope.id, case_id=e.cases[0].id, as_of=old_time)
    )
    assert [i.id for i in historical.entries] == [initial.id]
    assert later.id not in {i.id for i in historical.entries}
    assert future_event.id not in {i.id for i in historical.entries}


def test_unknown_event_and_date_precision(memory_env):
    e = memory_env
    unknown = e.ingest(e.observation())
    assert unknown.event["precision"] == "unknown"
    row = Medication(
        clinical_case_id=e.cases[0].id,
        name="Synthetic reported medication",
        status="active",
        start_date=date(2029, 12, 1),
        created_at=e.clock.now,
    )
    e.session.add(row)
    e.session.flush()
    entry = e.service.ingest_source(
        e.scope.id,
        e.cases[0].id,
        SourceReference(kind="medication", record_id=row.id, field="status"),
    )
    assert entry.event == {"precision": "date", "date_value": "2029-12-01", "datetime_value": None}
    assert len(e.selection().entries) == 2


def test_contradiction_same_instant_only(memory_env):
    e = memory_env
    t = e.clock.now
    a = e.ingest(e.observation(100, t))
    b = e.ingest(e.observation(110, t, case_index=1))
    changed = e.ingest(e.observation(120, t - timedelta(days=1)))
    unknown = e.ingest(e.observation(130))
    items = {i.id: i for i in e.selection().entries}
    assert items[a.id].conflicts == [b.id]
    assert items[b.id].components.consistency == 0
    assert not items[changed.id].conflicts and not items[unknown.id].conflicts


def test_stable_facts_not_independent_contradictions(memory_env):
    e = memory_env
    a = e.ingest(e.observation(100, e.clock.now))
    b = e.ingest(e.observation(100, e.clock.now, case_index=1))
    assert a.id != b.id
    assert all(not item.conflicts for item in e.selection().entries)


def test_correction_applies_only_after_availability(memory_env):
    e = memory_env
    a, b = e.ingest(e.observation()), e.ingest(e.observation(110))
    before = e.clock.now
    e.clock.now += timedelta(days=1)
    e.service.relate(e.scope.id, b.id, a.id, RelationType.CORRECTS)
    assert [i.id for i in e.selection().entries] == [b.id]
    old = e.service.select(
        SelectionRequest(scope_id=e.scope.id, case_id=e.cases[0].id, as_of=before)
    )
    assert {i.id for i in old.entries} == {a.id, b.id}


def test_selection_order_limits_and_omissions(memory_env):
    e = memory_env
    for i in range(5):
        e.ingest(e.observation(i))
    a, b = e.selection(max_entries=2), e.selection(max_entries=2)
    assert a == b and len(a.entries) == 2 and a.omitted_count == 3
    bounded = e.selection(max_characters=1024)
    assert len(bounded.model_dump_json()) <= 1024
    assert bounded.omitted_count == 5 - len(bounded.entries)


def test_stale_and_unknown_components_are_explicit():
    now = datetime(2030, 1, 1, tzinfo=UTC)
    unknown = confidence(EntryType.SOURCE_FACT, EventTime(), now, 365, False)
    assert unknown.freshness == unknown.temporal_reliability == 0
    stale = confidence(
        EntryType.SOURCE_FACT,
        EventTime(precision="date", date_value=date(2020, 1, 1)),
        now,
        365,
        False,
    )
    assert stale.freshness == 0 and stale.temporal_reliability == 0.5
    derived = confidence(EntryType.DERIVED_ASSERTION, EventTime(), now, 365, True)
    assert derived.source_quality == 0 and derived.consistency == 0
    assert derived == confidence(EntryType.DERIVED_ASSERTION, EventTime(), now, 365, True)
    assert event_visible(EventTime(), now)


def test_source_received_in_future_is_rejected(memory_env):
    from backend.app.services.clinical_memory import MemoryRejected

    e = memory_env
    row = e.observation()
    row.created_at += timedelta(days=1)
    e.session.flush()
    with pytest.raises(MemoryRejected, match="not_yet_available"):
        e.ingest(row)


def test_later_episode_membership_cannot_be_replayed_early(memory_env):
    from backend.app.models import ClinicalCase
    from backend.app.services.clinical_memory import MemoryRejected

    e = memory_env
    before = e.clock.now
    e.clock.now += timedelta(days=1)
    case = ClinicalCase(
        external_case_id="LATE",
        title="Synthetic",
        summary="Synthetic",
        source_type="synthetic",
        created_at=before,
    )
    e.session.add(case)
    e.session.flush()
    e.service.add_episode(e.scope.id, case.id)
    with pytest.raises(MemoryRejected, match="episode_not_in_scope"):
        e.service.select(SelectionRequest(scope_id=e.scope.id, case_id=case.id, as_of=before))


def test_changed_unit_is_not_automatic_conflict(memory_env):
    e = memory_env
    a = e.observation(100, e.clock.now)
    b = e.observation(5, e.clock.now)
    b.unit = "mmol/L"
    e.session.flush()
    e.ingest(a)
    e.ingest(b)
    assert all(not i.conflicts for i in e.selection().entries)
