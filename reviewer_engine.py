import ast
import json
import os
import re
import subprocess
import tempfile
import textwrap
from dataclasses import asdict, dataclass
from typing import Any

from dotenv import load_dotenv


load_dotenv()


SYSTEM_PROMPT = """You are a senior software engineer acting as an AI code reviewer.
Review the supplied code and respond as JSON with this exact schema:
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
  "improved_code": "full improved code"
}
Only return valid JSON.
"""


LANGUAGE_LABELS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".c": "C",
    ".cs": "C#",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".rs": "Rust",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".html": "HTML",
    ".css": "CSS",
    ".sql": "SQL",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".sh": "Shell",
}


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
    llm_status: dict[str, Any]


def detect_language(source_name: str) -> tuple[str, bool]:
    extension = os.path.splitext(source_name)[1].lower()
    language = LANGUAGE_LABELS.get(extension, "Code")
    return language, extension == ".py"


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


def _is_open_call(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id == "open"


def _is_subprocess_shell_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if not isinstance(node.func.value, ast.Name) or node.func.value.id != "subprocess":
        return False
    return any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords)


def _contains_zero_division(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Div):
            if isinstance(child.right, ast.Constant) and child.right.value == 0:
                return True
    return False


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
    files_opened_without_context = 0
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
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                issues.append(
                    ReviewIssue(
                        title="Exception swallowed with pass",
                        severity="medium",
                        category="bug",
                        details="This exception handler suppresses failures completely, which can hide production issues and make debugging much harder.",
                        suggestion="Log the exception or return an explicit error path instead of silently passing.",
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

        if isinstance(node, ast.Call) and _is_subprocess_shell_call(node):
            issues.append(
                ReviewIssue(
                    title="shell=True in subprocess",
                    severity="high",
                    category="security",
                    details="Using subprocess with shell=True can enable command injection when any part of the command is influenced by user input.",
                    suggestion="Pass the command as a list and avoid shell=True unless there is a clear, controlled need for a shell.",
                    source=source_name,
                )
            )

        if isinstance(node, ast.Call) and _is_open_call(node):
            files_opened_without_context += 1

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
            if _contains_zero_division(node):
                issues.append(
                    ReviewIssue(
                        title="Literal division by zero",
                        severity="high",
                        category="bug",
                        details=f"Function `{node.name}` contains a division where the denominator is literally zero, so this path will always raise ZeroDivisionError.",
                        suggestion="Guard the denominator before dividing or correct the expression so the divisor cannot be zero.",
                        source=source_name,
                    )
                )

    for node in tree.body:
        if isinstance(node, ast.With):
            for item in node.items:
                if isinstance(item.context_expr, ast.Call) and _is_open_call(item.context_expr):
                    files_opened_without_context = max(0, files_opened_without_context - 1)

        if isinstance(node, ast.Expr) and _contains_zero_division(node):
            issues.append(
                ReviewIssue(
                    title="Runtime crash from zero division",
                    severity="high",
                    category="bug",
                    details="Top-level executable code contains a division by zero, so the script will fail immediately when run.",
                    suggestion="Protect the denominator or remove the crashing demo call before execution.",
                    source=source_name,
                )
            )

    if files_opened_without_context:
        issues.append(
            ReviewIssue(
                title="File opened without context manager",
                severity="medium",
                category="maintainability",
                details="This file uses open() without a with-statement, which can leak file handles if an exception occurs before close().",
                suggestion="Use `with open(...) as handle:` so the file is always closed cleanly.",
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


def _friendly_llm_error(config: dict[str, str], error_text: str) -> str:
    lowered = error_text.lower()
    if "403" in error_text and "inference providers" in lowered:
        return (
            f"{config['model']} is configured, but this HF token cannot call Inference Providers. "
            "Use a token with Inference Providers permission or set HF_ENDPOINT_URL to a dedicated deployed endpoint."
        )
    if "403" in error_text:
        return f"{config['model']} request was rejected by Hugging Face. Check model access and token permissions."
    if "401" in error_text:
        return "Hugging Face authentication failed. Check HF_TOKEN."
    if "429" in error_text:
        return "Hugging Face rate limit reached. Retry in a moment or use a dedicated endpoint."
    if "timeout" in lowered:
        return f"{config['model']} timed out. Retry or switch to a dedicated endpoint."
    return f"{config['model']} request failed: {error_text}"


def get_llm_config() -> dict[str, str]:
    api_key = (
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        or os.getenv("LLM_API_KEY")
        or ""
    )
    endpoint_url = os.getenv("HF_ENDPOINT_URL", "")
    return {
        "provider": "Hugging Face Inference Providers",
        "api_key": api_key,
        "api_base": os.getenv("HF_API_BASE", "https://router.huggingface.co/v1"),
        "model": os.getenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct:novita"),
        "endpoint_url": endpoint_url,
        "mode": "endpoint" if endpoint_url else "hub-model",
    }


def _call_llm(code: str, source_name: str, language: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    config = get_llm_config()

    if not config["api_key"]:
        return None, {
            "enabled": False,
            "provider": config["provider"],
            "model": config["model"],
            "message": f"HF token not configured. Set HF_TOKEN to enable {config['model']} review.",
        }

    try:
        from huggingface_hub import InferenceClient

        client = InferenceClient(
            model=config["endpoint_url"] or None,
            api_key=config["api_key"],
        )

        completion = client.chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Review this {language} file named `{source_name}` and improve it when appropriate. "
                        "Focus on correctness, security, maintainability, and performance. "
                        "If the code should not be rewritten heavily, keep the improved version close to the original.\n\n"
                        f"```{language.lower()}\n{code}\n```"
                    ),
                },
            ],
            model=None if config["endpoint_url"] else config["model"],
            max_tokens=1400,
            temperature=0.2,
            response_format={"type": "json_object"},
            extra_body={"reasoning_effort": "medium"},
        )
        content = completion.choices[0].message.content
        return json.loads(content), {
            "enabled": True,
            "provider": config["provider"],
            "model": config["model"],
            "message": f"{config['model']} review completed through Hugging Face.",
        }
    except Exception as exc:
        error_message = _friendly_llm_error(config, str(exc))
        return None, {
            "enabled": True,
            "provider": config["provider"],
            "model": config["model"],
            "message": error_message,
        }


def _score_issues(issues: list[ReviewIssue]) -> int:
    penalties = {"high": 20, "medium": 10, "low": 4}
    score = 100
    for issue in issues:
        score -= penalties.get(issue.severity, 4)
    return max(score, 0)


def _issue_fingerprint(issue: ReviewIssue) -> str:
    title = issue.title.lower()
    details = issue.details.lower()

    if "eval" in title or "eval" in details:
        return "eval"
    if "shell=true" in title or ("subprocess" in title and "shell" in details):
        return "subprocess-shell"
    if "division by zero" in title or "zerodivisionerror" in details:
        return "division-by-zero"
    if "docstring" in title:
        return f"docstring:{issue.details}"
    if "open()" in title or "file handle" in details or "with open" in issue.suggestion.lower():
        return "open-without-context"
    if "bare except" in title or "exception swallowed" in title:
        return "bare-except"
    return f"{issue.title}|{issue.details}"


def _issue_strength(issue: ReviewIssue) -> tuple[int, int, int]:
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    source_rank = {"snippet.py": 0}
    title = issue.title.lower()
    specificity_bonus = 0
    if "subprocess.call()" in title or "eval()" in title or "division by zero" in title:
        specificity_bonus = -1
    return (
        severity_rank.get(issue.severity, 3),
        specificity_bonus,
        source_rank.get(issue.source, 1),
    )


def _deduplicate_issues(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    best_by_fingerprint: dict[str, ReviewIssue] = {}

    for issue in issues:
        fingerprint = _issue_fingerprint(issue)
        current = best_by_fingerprint.get(fingerprint)
        if current is None or _issue_strength(issue) < _issue_strength(current):
            best_by_fingerprint[fingerprint] = issue

    return list(best_by_fingerprint.values())


def _prioritize_issues(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    seen_docstrings = 0
    prioritized: list[ReviewIssue] = []

    for issue in sorted(
        _deduplicate_issues(issues),
        key=lambda item: (
            severity_rank.get(item.severity, 3),
            item.category,
            item.title,
        ),
    ):
        if issue.title == "Missing function docstring":
            seen_docstrings += 1
            if seen_docstrings > 2:
                continue
        prioritized.append(issue)

    return prioritized


def _validate_python(code: str) -> dict[str, Any]:
    try:
        compile(code, "<review>", "exec")
        return {"status": "passed", "details": "Syntax check passed."}
    except SyntaxError as exc:
        return {
            "status": "failed",
            "details": f"Syntax check failed at line {exc.lineno}: {exc.msg}",
        }


def _validate_generic(code: str, language: str) -> dict[str, Any]:
    if not code.strip():
        return {"status": "failed", "details": "No code was available to validate."}
    return {"status": "passed", "details": f"{language} rewrite generated. No local syntax validator is configured for this language."}


def analyze_python_file(code: str, source_name: str = "snippet.py") -> FileReview:
    cleaned_code = _clean_code(code)
    static_issues, ast_summary = _run_ast_checks(cleaned_code, source_name)
    lint_output = _run_pylint(cleaned_code)
    lint_issues = _issues_from_pylint(lint_output, source_name)

    llm_payload, llm_status = _call_llm(cleaned_code, source_name, "Python")
    llm_issues: list[ReviewIssue] = []
    llm_summary = llm_status["message"]
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

    combined_issues = _prioritize_issues(static_issues + lint_issues + llm_issues)
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
        (
            f"Asked {llm_status['model']} via {llm_status['provider']} for semantic review."
            if llm_payload
            else llm_status["message"]
        ),
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
        llm_status=llm_status,
    )


def analyze_generic_file(code: str, source_name: str, language: str) -> FileReview:
    cleaned_code = _clean_code(code)
    static_issues: list[ReviewIssue] = []
    lint_output = f"Language-aware local linting is not configured for {language}."

    if not cleaned_code.strip():
        static_issues.append(
            ReviewIssue(
                title="Empty input",
                severity="high",
                category="bug",
                details="The submitted source is empty, so there is nothing to execute or review.",
                suggestion="Paste code or upload at least one source file before running analysis.",
                source=source_name,
            )
        )
        ast_summary = "No code provided."
    else:
        static_issues.append(
            ReviewIssue(
                title=f"{language} semantic review",
                severity="low",
                category="maintainability",
                details=f"This file is being reviewed with the model-assisted path because deeper local analyzers are currently only configured for Python.",
                suggestion=f"Use the suggested rewrite and issues panel to inspect correctness, security, and maintainability risks for this {language} file.",
                source=source_name,
            )
        )
        ast_summary = f"Prepared {language} source for model-assisted review."

    llm_payload, llm_status = _call_llm(cleaned_code, source_name, language)
    llm_issues: list[ReviewIssue] = []
    llm_summary = llm_status["message"]
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

    combined_issues = _prioritize_issues(static_issues + llm_issues)
    quality_score = _score_issues(combined_issues)
    validation = _validate_generic(improved_code, language)
    improved_score = min(100, quality_score + 6) if validation["status"] == "passed" else quality_score

    summary = textwrap.shorten(
        f"{ast_summary} {llm_summary}",
        width=180,
        placeholder="...",
    )

    agent_steps = [
        f"Ingested `{source_name}` and normalized the {language} source.",
        f"Skipped Python-only AST and PyLint stages because this file is {language}.",
        (
            f"Asked {llm_status['model']} via {llm_status['provider']} for semantic review."
            if llm_payload
            else llm_status["message"]
        ),
        f"Prepared the suggested {language} rewrite for side-by-side comparison.",
        f"Validation note: {validation['details']}",
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
        llm_status=llm_status,
    )


def analyze_source_file(code: str, source_name: str = "snippet.py") -> FileReview:
    language, is_python = detect_language(source_name)
    if is_python:
        return analyze_python_file(code, source_name)
    return analyze_generic_file(code, source_name, language)


def analyze_project(sources: list[tuple[str, str]]) -> dict[str, Any]:
    file_reviews = [analyze_source_file(code, path) for path, code in sources]
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
