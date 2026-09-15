"""Conservative comparison of supplied measurements; no medical inference."""

from memory.contracts import SourceKind, SourceSnapshot


def contradicts(a: SourceSnapshot, b: SourceSnapshot) -> bool:
    return (
        a.reference.kind == b.reference.kind == SourceKind.OBSERVATION
        and a.reference.field == b.reference.field
        and a.reference.field in {"value_numeric", "value_text"}
        and a.event.precision == b.event.precision == "datetime"
        and a.event == b.event
        and a.semantic_identity == b.semantic_identity
        and a.value is not None
        and b.value is not None
        and a.value != b.value
    )
