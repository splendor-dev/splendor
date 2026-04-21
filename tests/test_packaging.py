import os
import subprocess
import sys
from pathlib import Path


def test_built_wheel_exposes_splendor_cli(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(repo_root / "src")}
    subprocess.run(
        ["uv", "build", "--out-dir", str(tmp_path / "dist")],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    wheel_path = next((tmp_path / "dist").glob("*.whl"))

    venv_dir = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", str(venv_dir), "--python", sys.executable],
        check=True,
        capture_output=True,
        text=True,
    )
    bin_dir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    subprocess.run(
        ["uv", "pip", "install", "--python", str(bin_dir / "python"), str(wheel_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [str(bin_dir / "splendor"), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Splendor knowledge compiler CLI" in result.stdout
    assert "add-source" in result.stdout
