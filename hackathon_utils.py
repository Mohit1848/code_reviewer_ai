import difflib
import html
import shutil
import subprocess
import tempfile
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".cpp",
    ".cc",
    ".cxx",
    ".c",
    ".cs",
    ".go",
    ".rb",
    ".php",
    ".rs",
    ".swift",
    ".kt",
    ".scala",
    ".html",
    ".css",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
    ".sh",
}


def generate_diff(old_code: str, new_code: str) -> str:
    diff = difflib.unified_diff(
        old_code.splitlines(),
        new_code.splitlines(),
        fromfile="before.py",
        tofile="after.py",
        lineterm="",
    )
    return "\n".join(diff) or "No code changes suggested."


def build_code_comparison_rows(old_code: str, new_code: str) -> list[dict[str, str | int | None]]:
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    rows: list[dict[str, str | int | None]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for old_index, new_index in zip(range(i1, i2), range(j1, j2)):
                rows.append(
                    {
                        "left_number": old_index + 1,
                        "left_text": old_lines[old_index],
                        "left_state": "unchanged",
                        "right_number": new_index + 1,
                        "right_text": new_lines[new_index],
                        "right_state": "unchanged",
                    }
                )
            continue

        span = max(i2 - i1, j2 - j1)
        for offset in range(span):
            old_index = i1 + offset
            new_index = j1 + offset
            has_old = old_index < i2
            has_new = new_index < j2

            rows.append(
                {
                    "left_number": old_index + 1 if has_old else None,
                    "left_text": old_lines[old_index] if has_old else "",
                    "left_state": "removed" if has_old else "empty",
                    "right_number": new_index + 1 if has_new else None,
                    "right_text": new_lines[new_index] if has_new else "",
                    "right_state": "added" if has_new else "empty",
                }
            )

    return rows


def render_code_panel(rows: list[dict[str, str | int | None]], side: str) -> str:
    number_key = f"{side}_number"
    text_key = f"{side}_text"
    state_key = f"{side}_state"
    html_rows: list[str] = []

    for row in rows:
        state = row[state_key] or "empty"
        line_number = "" if row[number_key] is None else str(row[number_key])
        line_text = row[text_key] or " "
        escaped_text = html.escape(str(line_text))
        html_rows.append(
            f"""
            <div class="compare-row compare-row--{state}">
                <span class="compare-line-number">{line_number}</span>
                <span class="compare-line-text">{escaped_text}</span>
            </div>
            """
        )

    return "".join(html_rows)


def collect_reviewable_files_from_directory(directory: str, max_files: int = 12) -> list[tuple[str, str]]:
    base = Path(directory).expanduser()
    if not base.exists() or not base.is_dir():
        return []

    ignored_parts = {".git", ".venv", "venv", "__pycache__", "site-packages", "node_modules", "test"}
    results: list[tuple[str, str]] = []

    for path in base.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if any(part in ignored_parts for part in path.parts):
            continue
        try:
            results.append((str(path.relative_to(base)), path.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            continue
        if len(results) >= max_files:
            break
    return results


def load_uploaded_reviewable_files(uploaded_files) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for uploaded_file in uploaded_files or []:
        if Path(uploaded_file.name).suffix.lower() not in SUPPORTED_EXTENSIONS:
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
