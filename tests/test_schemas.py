import pytest
from pydantic import ValidationError

from splendor.schemas import SourceRecord


def test_source_record_validation_accepts_valid_payload() -> None:
    record = SourceRecord(
        source_id="src-1234567890abcdef",
        title="Spec",
        source_type="md",
        path="raw/sources/src-123/spec.md",
        checksum="a" * 64,
        added_at="2026-04-10T15:00:00+00:00",
        pipeline_version="0.1.0a0",
    )

    assert record.kind == "source"


def test_source_record_validation_rejects_bad_checksum() -> None:
    with pytest.raises(ValidationError):
        SourceRecord(
            source_id="src-1234567890abcdef",
            title="Spec",
            source_type="md",
            path="raw/sources/src-123/spec.md",
            checksum="short",
            added_at="2026-04-10T15:00:00+00:00",
            pipeline_version="0.1.0a0",
        )


def test_source_record_validation_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SourceRecord(
            source_id="src-1234567890abcdef",
            title="Spec",
            source_type="md",
            path="raw/sources/src-123/spec.md",
            checksum="a" * 64,
            added_at="2026-04-10T15:00:00+00:00",
            pipeline_version="0.1.0a0",
            unexpected_field="nope",
        )
