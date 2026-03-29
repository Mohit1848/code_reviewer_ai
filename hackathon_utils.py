import difflib
import shutil
import subprocess
import tempfile
from pathlib import Path


def generate_diff(old_code: str, new_code: str) -> str:
    diff = difflib.unified_diff(
        old_code.splitlines(),
        new_code.splitlines(),
        fromfile="before.py",
        tofile="after.py",
        lineterm="",
    )
    return "\n".join(diff) or "No code changes suggested."


def collect_python_files_from_directory(directory: str, max_files: int = 12) -> list[tuple[str, str]]:
    base = Path(directory).expanduser()
    if not base.exists() or not base.is_dir():
        return []

    ignored_parts = {".git", ".venv", "venv", "__pycache__", "site-packages", "node_modules", "test"}
    results: list[tuple[str, str]] = []

    for path in base.rglob("*.py"):
        if any(part in ignored_parts for part in path.parts):
            continue
        try:
            results.append((str(path.relative_to(base)), path.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            continue
        if len(results) >= max_files:
            break
    return results


def load_uploaded_python_files(uploaded_files) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for uploaded_file in uploaded_files or []:
        if not uploaded_file.name.endswith(".py"):
            continue
        sources.append((uploaded_file.name, uploaded_file.getvalue().decode("utf-8")))
    return sources


def clone_github_repo(repo_url: str) -> tuple[str | None, str | None]:
    if not repo_url.strip():
        return None, "Enter a GitHub repository URL."

    git_path = shutil.which("git")
    if not git_path:
        return None, "Git is not installed or not available on PATH."

    temp_dir = tempfile.mkdtemp(prefix="agentic-review-")
    target_dir = str(Path(temp_dir) / "repo")

    try:
        result = subprocess.run(
            [git_path, "clone", "--depth", "1", repo_url, target_dir],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return None, "Cloning the repository timed out."
    except Exception as exc:
        return None, f"Failed to clone repository: {exc}"

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout).strip() or "Git clone failed."
        return None, error_text

    return target_dir, None
