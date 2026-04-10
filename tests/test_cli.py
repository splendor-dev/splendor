from pathlib import Path

from splendor.cli import main


def test_cli_init_command(tmp_path: Path, capsys) -> None:
    exit_code = main(["--root", str(tmp_path), "init"])

    assert exit_code == 0
    assert (tmp_path / "wiki" / "index.md").exists()
    captured = capsys.readouterr()
    assert "Initialized Splendor workspace" in captured.out


def test_cli_add_source_command(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "add-source", str(source)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Registered source" in captured.out


def test_cli_add_source_resolves_relative_paths_against_root(tmp_path: Path, capsys) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    docs_dir = repo_root / "docs"
    docs_dir.mkdir()
    source = docs_dir / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    main(["--root", str(repo_root), "init"])
    exit_code = main(["--root", str(repo_root), "add-source", "docs/brief.md"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Registered source" in captured.out
