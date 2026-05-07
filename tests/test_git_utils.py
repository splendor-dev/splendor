import splendor.utils.git as git_utils


class CustomPath:
    def __fspath__(self) -> str:
        return "from-fspath"

    def __str__(self) -> str:
        return "from-str"


def test_git_command_uses_fspath_for_pathlike_arguments(monkeypatch) -> None:
    monkeypatch.setattr(git_utils, "git_executable", lambda: "/usr/bin/git")

    assert git_utils.git_command("show", CustomPath()) == [
        "/usr/bin/git",
        "show",
        "from-fspath",
    ]


def test_run_git_reports_missing_executable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(git_utils, "git_executable", lambda: None)

    result = git_utils.run_git(tmp_path, ["status"])

    assert git_utils.is_git_executable_missing(result)
    assert result.args == ["git", "status"]
    assert result.stdout == ""
    assert result.stderr == git_utils.GIT_EXECUTABLE_NOT_FOUND
