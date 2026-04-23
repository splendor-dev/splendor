import pytest
from pydantic import ValidationError

from splendor.schemas import (
    ContradictionAnnotation,
    ContradictionEvidence,
    KnowledgePageFrontmatter,
    ProvenanceLink,
    RunRecord,
    SourcePointerArtifact,
    SourceRecord,
)


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
        generated_by_run_ids=["run-src-123"],
        reviewed_at="2026-04-11T15:00:00+00:00",
        reviewed_by="reviewer@example.com",
        provenance_links=[
            ProvenanceLink(
                source_id="src-1234567890abcdef",
                run_id="run-src-123",
                path_ref="wiki/sources/src-1234567890abcdef.md",
                role="generated-page",
            )
        ],
    )

    assert record.source_ref == "docs/spec.md"
    assert record.storage_mode == "none"
    assert record.generated_by_run_ids == ["run-src-123"]
    assert record.reviewed_by == "reviewer@example.com"


def test_knowledge_page_frontmatter_defaults_review_and_provenance_fields() -> None:
    record = KnowledgePageFrontmatter(
        kind="concept",
        title="Overview",
        page_id="concept-overview",
    )

    assert record.review_state == "draft"
    assert record.last_generated_at is None
    assert record.provenance_links == []
    assert record.contradictions == []


def test_contradiction_annotation_accepts_evidence_payload() -> None:
    annotation = ContradictionAnnotation(
        contradiction_id="contradiction-a-b-1234567890",
        summary="The pages disagree about the supported storage mode.",
        detected_at="2026-04-22T10:00:00+00:00",
        related_page_ids=["src-a", "src-b"],
        related_source_ids=["src-a", "src-b"],
        review_task_id="task-review-src-a-src-b-1234567890",
        evidence=[
            ContradictionEvidence(
                page_id="src-a",
                source_id="src-a",
                run_id="run-a",
                path_ref="wiki/sources/src-a.md",
                excerpt="The source says storage mode is none.",
            )
        ],
    )

    assert annotation.review_task_id == "task-review-src-a-src-b-1234567890"
    assert annotation.evidence[0].page_id == "src-a"


def test_knowledge_page_frontmatter_accepts_expanded_provenance_payload() -> None:
    record = KnowledgePageFrontmatter(
        kind="source-summary",
        title="Spec",
        page_id="src-1234567890abcdef",
        status="active",
        review_state="machine-generated",
        source_refs=["src-1234567890abcdef"],
        generated_by_run_ids=["run-src-123"],
        last_generated_at="2026-04-10T15:02:00+00:00",
        provenance_links=[
            ProvenanceLink(
                source_id="src-1234567890abcdef",
                run_id="run-src-123",
                path_ref="state/manifests/sources/src-1234567890abcdef.json",
                role="generated-from",
            )
        ],
        contradictions=[
            ContradictionAnnotation(
                contradiction_id="contradiction-src-123-src-456-1234567890",
                summary="Two source summaries disagree about the pipeline version.",
                detected_at="2026-04-22T10:05:00+00:00",
                related_page_ids=["src-1234567890abcdef", "src-456"],
                related_source_ids=["src-1234567890abcdef", "src-456"],
                review_task_id="task-review-src-123456789-src-456-1234567890",
                evidence=[
                    ContradictionEvidence(
                        page_id="src-1234567890abcdef",
                        source_id="src-1234567890abcdef",
                        run_id="run-src-123",
                        path_ref="wiki/sources/src-1234567890abcdef.md",
                        excerpt="The summary says the pipeline is v1.",
                    )
                ],
            )
        ],
    )

    assert record.review_state == "machine-generated"
    assert record.provenance_links[0].role == "generated-from"
    assert record.contradictions[0].review_task_id.startswith("task-review-")


def test_run_record_accepts_expanded_provenance_payload() -> None:
    record = RunRecord(
        run_id="run-src-123",
        job_id="ingest-src-123",
        job_type="ingest_source",
        started_at="2026-04-10T15:00:00+00:00",
        finished_at="2026-04-10T15:01:00+00:00",
        status="succeeded",
        input_refs=["state/manifests/sources/src-1234567890abcdef.json"],
        output_refs=["wiki/sources/src-1234567890abcdef.md"],
        warnings=[],
        errors=[],
        pipeline_version="0.1.0a0",
        source_ids=["src-1234567890abcdef"],
        page_ids=["src-1234567890abcdef"],
        page_refs=["wiki/sources/src-1234567890abcdef.md"],
        contradiction_ids=["contradiction-src-123-src-456-1234567890"],
        task_ids=["task-review-src-123-src-456-1234567890"],
        provenance_links=[
            ProvenanceLink(
                source_id="src-1234567890abcdef",
                page_id="src-1234567890abcdef",
                run_id="run-src-123",
                path_ref="wiki/sources/src-1234567890abcdef.md",
                role="output",
            )
        ],
    )

    assert record.source_ids == ["src-1234567890abcdef"]
    assert record.page_refs == ["wiki/sources/src-1234567890abcdef.md"]
    assert record.task_ids == ["task-review-src-123-src-456-1234567890"]


def test_provenance_link_requires_an_identity_field() -> None:
    with pytest.raises(ValidationError):
        ProvenanceLink()


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
