import pytest
from pydantic import ValidationError

from splendor.schemas import SourcePointerArtifact, SourceRecord


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


def test_source_record_validation_accepts_valid_expanded_payload() -> None:
    record = SourceRecord(
        source_id="src-1234567890abcdef",
        title="Spec",
        source_type="md",
        path="raw/sources/src-123/spec.md",
        checksum="a" * 64,
        added_at="2026-04-10T15:00:00+00:00",
        pipeline_version="0.1.0a0",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        storage_mode="none",
        storage_path=None,
        materialized_at="2026-04-10T15:01:00+00:00",
        source_commit="abc123",
    )

    assert record.source_ref == "docs/spec.md"
    assert record.storage_mode == "none"


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


def test_source_record_validation_rejects_invalid_source_ref_kind() -> None:
    with pytest.raises(ValidationError):
        SourceRecord(
            source_id="src-1234567890abcdef",
            title="Spec",
            source_type="md",
            path="raw/sources/src-123/spec.md",
            checksum="a" * 64,
            added_at="2026-04-10T15:00:00+00:00",
            pipeline_version="0.1.0a0",
            source_ref_kind="bogus",
        )


def test_source_record_validation_rejects_invalid_storage_mode() -> None:
    with pytest.raises(ValidationError):
        SourceRecord(
            source_id="src-1234567890abcdef",
            title="Spec",
            source_type="md",
            path="raw/sources/src-123/spec.md",
            checksum="a" * 64,
            added_at="2026-04-10T15:00:00+00:00",
            pipeline_version="0.1.0a0",
            storage_mode="bogus",
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


def test_source_pointer_artifact_accepts_valid_payload() -> None:
    artifact = SourcePointerArtifact(
        source_id="src-1234567890abcdef",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="a" * 64,
        created_at="2026-04-10T15:00:00+00:00",
    )

    assert artifact.kind == "source-pointer"


def test_source_pointer_artifact_rejects_bad_checksum() -> None:
    with pytest.raises(ValidationError):
        SourcePointerArtifact(
            source_id="src-1234567890abcdef",
            source_ref="docs/spec.md",
            source_ref_kind="workspace_path",
            checksum="short",
            created_at="2026-04-10T15:00:00+00:00",
        )


def test_source_pointer_artifact_rejects_invalid_source_ref_kind() -> None:
    with pytest.raises(ValidationError):
        SourcePointerArtifact(
            source_id="src-1234567890abcdef",
            source_ref="docs/spec.md",
            source_ref_kind="bogus",
            checksum="a" * 64,
            created_at="2026-04-10T15:00:00+00:00",
        )


def test_source_pointer_artifact_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SourcePointerArtifact(
            source_id="src-1234567890abcdef",
            source_ref="docs/spec.md",
            source_ref_kind="workspace_path",
            checksum="a" * 64,
            created_at="2026-04-10T15:00:00+00:00",
            unexpected_field="nope",
        )
