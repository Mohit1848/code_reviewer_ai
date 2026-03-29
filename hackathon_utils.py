import difflib
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
