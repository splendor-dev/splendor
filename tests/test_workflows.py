from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_workflow(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def _workflow_triggers(workflow: dict) -> dict:
    # PyYAML still applies YAML 1.1 boolean coercion, so unquoted GitHub Actions `on`
    # can parse as True.
    return workflow.get("on") or workflow.get(True)


def test_generated_change_pr_workflow_contract() -> None:
    workflow = _load_workflow(".github/workflows/splendor-generated-change-pr.yml")

    assert workflow["name"] == "Splendor generated-change PR"
    assert set(_workflow_triggers(workflow)) == {"workflow_dispatch", "schedule"}
    assert workflow["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }

    steps = workflow["jobs"]["repo-refresh-pr"]["steps"]
    runs = [step.get("run") for step in steps]
    uses = [step.get("uses") for step in steps]

    assert "uv run splendor repo refresh" in runs
    assert "uv run splendor lint" in runs
    assert "peter-evans/create-pull-request@v8" in uses

    create_pr_step = next(
        step for step in steps if step.get("uses") == "peter-evans/create-pull-request@v8"
    )
    assert create_pr_step["with"]["branch"] == "codex/splendor-generated-repo-refresh"
    assert create_pr_step["with"]["commit-message"] == (
        "M8-P2.1 refresh Splendor generated wiki state"
    )
    assert create_pr_step["with"]["title"] == "M8-P2.1 Refresh Splendor generated wiki state"
    assert create_pr_step["with"]["add-paths"].split() == [
        "wiki/**",
        "state/manifests/sources/**",
        "raw/sources/**",
    ]
