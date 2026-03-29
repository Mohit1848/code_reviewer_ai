import ast
import json
import os
import re
import subprocess
import tempfile
import textwrap
from dataclasses import asdict, dataclass
from typing import Any


SYSTEM_PROMPT = """You are a senior software engineer acting as an AI code reviewer.
Review the supplied Python code and respond as JSON with this exact schema:
{
  "summary": "short summary",
  "issues": [
    {
      "title": "short issue title",
      "severity": "high|medium|low",
      "category": "bug|performance|style|maintainability|security",
      "details": "one paragraph",
      "suggestion": "specific fix suggestion"
    }
  ],
  "improved_code": "full improved Python code"
}
Only return valid JSON.
"""


@dataclass
class ReviewIssue:
    title: str
    severity: str
    category: str
    details: str
    suggestion: str
    source: str


@dataclass
class FileReview:
    path: str
    summary: str
    issues: list[ReviewIssue]
    lint_output: str
    original_code: str
    improved_code: str
    quality_score: int
    improved_score: int
    validation: dict[str, Any]
    agent_steps: list[str]


def _clean_code(code: str) -> str:
    lines = [line.rstrip() for line in code.replace("\t", "    ").splitlines()]
    cleaned = "\n".join(lines).strip("\n")
    return f"{cleaned}\n" if cleaned else ""


def _extract_import_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.add(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            names.add(alias.asname or alias.name)
    return names


def _collect_used_names(tree: ast.AST) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    return used


def _run_ast_checks(code: str, source_name: str) -> tuple[list[ReviewIssue], str]:
    issues: list[ReviewIssue] = []
    if not code.strip():
        issues.append(
            ReviewIssue(
                title="Empty input",
                severity="high",
                category="bug",
                details="The submitted source is empty, so there is nothing to execute or review.",
                suggestion="Paste code or upload at least one Python file before running analysis.",
                source=source_name,
            )
        )
        return issues, "No code provided."

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        issues.append(
            ReviewIssue(
                title="Syntax error",
                severity="high",
                category="bug",
                details=f"Python could not parse the file: {exc.msg} at line {exc.lineno}.",
                suggestion="Fix the syntax error before running deeper validation.",
                source=source_name,
            )
        )
        return issues, "Syntax validation failed."

    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported_names.update(_extract_import_names(node))

        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(
                ReviewIssue(
                    title="Bare except block",
                    severity="medium",
                    category="bug",
                    details="A bare except catches system-exiting exceptions and makes failures harder to debug.",
                    suggestion="Catch the expected exception type explicitly and log or handle the failure path.",
                    source=source_name,
                )
            )

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "eval":
            issues.append(
                ReviewIssue(
                    title="Use of eval",
                    severity="high",
                    category="security",
                    details="Calling eval on dynamic input can execute arbitrary code and is risky in production code.",
                    suggestion="Replace eval with a safer parser or an explicit dispatch table.",
                    source=source_name,
                )
            )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not ast.get_docstring(node):
            issues.append(
                ReviewIssue(
                    title="Missing function docstring",
                    severity="low",
                    category="maintainability",
                    details=f"Function `{node.name}` has no docstring, which makes the review output less self-explanatory.",
                    suggestion="Add a short docstring for non-trivial functions so reviewers understand intent quickly.",
                    source=source_name,
                )
            )

    used_names = _collect_used_names(tree)
    unused_imports = sorted(name for name in imported_names if name not in used_names)
    if unused_imports:
        issues.append(
            ReviewIssue(
                title="Unused imports",
                severity="low",
                category="style",
                details=f"Unused imports detected: {', '.join(unused_imports)}.",
                suggestion="Remove unused imports to reduce clutter and avoid misleading readers.",
                source=source_name,
            )
        )

    if len(code.splitlines()) > 250:
        issues.append(
            ReviewIssue(
                title="Large file",
                severity="low",
                category="maintainability",
                details="This file is fairly large for a hackathon project and may be harder to reason about quickly.",
                suggestion="Split the file into smaller modules around analysis, UI, and integrations.",
                source=source_name,
            )
        )

    if not issues:
        issues.append(
            ReviewIssue(
                title="No obvious static issues",
                severity="low",
                category="maintainability",
                details="Basic AST checks did not find any obvious bugs in this file.",
                suggestion="Use the optional LLM review for deeper semantic suggestions and architecture feedback.",
                source=source_name,
            )
        )

    return issues, "AST validation passed."


def _run_pylint(code: str) -> str:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode="w", encoding="utf-8") as temp:
            temp.write(code)
            temp_path = temp.name

        result = subprocess.run(
            ["pylint", "--output-format=json", temp_path],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError:
        return "PyLint is not installed in the active environment."
    except subprocess.TimeoutExpired:
        return "PyLint timed out while analyzing the file."
    except Exception as exc:
        return f"PyLint failed: {exc}"
    finally:
        if "temp_path" in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if not stdout and stderr:
        return stderr
    return stdout or "PyLint did not return any findings."


def _issues_from_pylint(lint_output: str, source_name: str) -> list[ReviewIssue]:
    if not lint_output.strip().startswith("["):
        return []

    try:
        entries = json.loads(lint_output)
    except json.JSONDecodeError:
        return []

    issues: list[ReviewIssue] = []
    for entry in entries[:8]:
        category = entry.get("type", "style")
        severity = "high" if category in {"error", "fatal"} else "medium" if category == "warning" else "low"
        line = entry.get("line", "?")
        symbol = entry.get("symbol", "pylint")
        message = entry.get("message", "PyLint finding")
        issues.append(
            ReviewIssue(
                title=f"PyLint: {symbol}",
                severity=severity,
                category="style" if category in {"convention", "refactor"} else "bug",
                details=f"Line {line}: {message}",
                suggestion="Address the linter warning or suppress it with a clear justification if intentional.",
                source=source_name,
            )
        )
    return issues


def _extract_code_block(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _call_llm(code: str) -> dict[str, Any] | None:
    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
    model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

    if not api_key:
        return None

    try:
        import requests

        response = requests.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Review this Python file and improve it when appropriate.\n\n```python\n{code}\n```",
                    },
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            timeout=40,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return None


def _score_issues(issues: list[ReviewIssue]) -> int:
    penalties = {"high": 20, "medium": 10, "low": 4}
    score = 100
    for issue in issues:
        score -= penalties.get(issue.severity, 4)
    return max(score, 0)


def _validate_python(code: str) -> dict[str, Any]:
    try:
        compile(code, "<review>", "exec")
        return {"status": "passed", "details": "Syntax check passed."}
    except SyntaxError as exc:
        return {
            "status": "failed",
            "details": f"Syntax check failed at line {exc.lineno}: {exc.msg}",
        }


def analyze_python_file(code: str, source_name: str = "snippet.py") -> FileReview:
    cleaned_code = _clean_code(code)
    static_issues, ast_summary = _run_ast_checks(cleaned_code, source_name)
    lint_output = _run_pylint(cleaned_code)
    lint_issues = _issues_from_pylint(lint_output, source_name)

    llm_payload = _call_llm(cleaned_code)
    llm_issues: list[ReviewIssue] = []
    llm_summary = "LLM review skipped. Set LLM_API_KEY to enable semantic review."
    improved_code = cleaned_code

    if llm_payload:
        llm_summary = llm_payload.get("summary", "LLM review completed.")
        for item in llm_payload.get("issues", [])[:6]:
            llm_issues.append(
                ReviewIssue(
                    title=item.get("title", "LLM suggestion"),
                    severity=item.get("severity", "medium"),
                    category=item.get("category", "maintainability"),
                    details=item.get("details", "No details provided."),
                    suggestion=item.get("suggestion", "Review the recommendation and apply it if useful."),
                    source=source_name,
                )
            )
        candidate_code = llm_payload.get("improved_code", "") or _extract_code_block(json.dumps(llm_payload))
        if candidate_code.strip():
            improved_code = _clean_code(candidate_code)

    combined_issues = static_issues + lint_issues + llm_issues
    quality_score = _score_issues(combined_issues)
    validation = _validate_python(improved_code)
    improved_score = quality_score if validation["status"] != "passed" else min(100, quality_score + 8)

    summary = textwrap.shorten(
        f"{ast_summary} {llm_summary}",
        width=180,
        placeholder="...",
    )

    agent_steps = [
        f"Ingested `{source_name}` and normalized the Python source.",
        f"Ran AST heuristics and found {len(static_issues)} review signal(s).",
        f"Ran PyLint and surfaced {len(lint_issues)} linter-derived issue(s).",
        "Requested semantic review from the optional LLM." if llm_payload else "Skipped remote LLM review because no API key is configured.",
        f"Validated the proposed code update: {validation['details']}",
    ]

    return FileReview(
        path=source_name,
        summary=summary,
        issues=combined_issues,
        lint_output=lint_output,
        original_code=cleaned_code,
        improved_code=improved_code,
        quality_score=quality_score,
        improved_score=improved_score,
        validation=validation,
        agent_steps=agent_steps,
    )


def analyze_project(sources: list[tuple[str, str]]) -> dict[str, Any]:
    file_reviews = [analyze_python_file(code, path) for path, code in sources]
    all_issues = [asdict(issue) for review in file_reviews for issue in review.issues]
    avg_before = round(sum(review.quality_score for review in file_reviews) / len(file_reviews)) if file_reviews else 0
    avg_after = round(sum(review.improved_score for review in file_reviews) / len(file_reviews)) if file_reviews else 0

    return {
        "project_summary": {
            "files_analyzed": len(file_reviews),
            "issues_found": len(all_issues),
            "score_before": avg_before,
            "score_after": avg_after,
        },
        "file_reviews": [asdict(review) for review in file_reviews],
    }
