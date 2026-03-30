import os

from reviewer_engine import analyze_generic_file, analyze_project, analyze_python_file, analyze_source_file
from reviewer_engine import detect_language, get_llm_config


def _disable_llm(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACEHUB_API_TOKEN", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("HF_MODEL", raising=False)
    monkeypatch.delenv("HF_API_BASE", raising=False)
    monkeypatch.delenv("HF_ENDPOINT_URL", raising=False)


def test_analyze_python_file_flags_syntax_error():
    os.environ.pop("HF_TOKEN", None)
    review = analyze_python_file("def broken(:\n    pass\n", "broken.py")

    assert any(issue.title == "Syntax error" for issue in review.issues)
    assert any(issue.title == "Syntax error" for issue in review.issues)


def test_analyze_project_returns_summary_counts(monkeypatch):
    _disable_llm(monkeypatch)
    result = analyze_project([("sample.py", "def add(a, b):\n    return a + b\n")])

    assert result["project_summary"]["files_analyzed"] == 1
    assert len(result["file_reviews"]) == 1


def test_analyze_python_file_preserves_valid_code_when_llm_is_disabled(monkeypatch):
    _disable_llm(monkeypatch)
    source = "def add(a, b):\n    return a + b\n"

    review = analyze_python_file(source, "sample.py")

    assert review.original_code == source
    assert review.improved_code == source
    assert review.validation["status"] == "passed"


def test_get_llm_config_defaults_to_hugging_face(monkeypatch):
    _disable_llm(monkeypatch)
    monkeypatch.setenv("HF_MODEL", "deepseek-ai/DeepSeek-R1")
    monkeypatch.setenv("HF_API_BASE", "https://router.huggingface.co/v1")

    config = get_llm_config()

    assert config["provider"] == "Hugging Face Inference Providers"
    assert config["model"] == "deepseek-ai/DeepSeek-R1"
    assert config["api_base"] == "https://router.huggingface.co/v1"
    assert config["api_key"] == ""
    assert config["endpoint_url"] == ""
    assert config["mode"] == "hub-model"


def test_get_llm_config_uses_endpoint_mode(monkeypatch):
    monkeypatch.setenv("HF_ENDPOINT_URL", "https://example.endpoints.huggingface.cloud")

    config = get_llm_config()

    assert config["endpoint_url"] == "https://example.endpoints.huggingface.cloud"
    assert config["mode"] == "endpoint"


def test_analyze_python_file_detects_high_signal_security_and_runtime_issues(monkeypatch):
    _disable_llm(monkeypatch)
    source = (
        "import subprocess\n"
        "\n"
        "def read_config(path):\n"
        "    f = open(path, 'r')\n"
        "    return f.read()\n"
        "\n"
        "def deploy(branch_name):\n"
        "    try:\n"
        "        subprocess.call('git checkout ' + branch_name, shell=True)\n"
        "    except:\n"
        "        pass\n"
        "\n"
        "print(10 / 0)\n"
    )

    review = analyze_python_file(source, "demo.py")
    titles = {issue.title for issue in review.issues}

    assert "shell=True in subprocess" in titles
    assert "File opened without context manager" in titles
    assert "Bare except block" in titles
    assert "Runtime crash from zero division" in titles


def test_analyze_python_file_prioritizes_severe_issues(monkeypatch):
    _disable_llm(monkeypatch)
    source = (
        "def a(x):\n"
        "    return eval(x)\n"
        "\n"
        "def b():\n"
        "    return 1\n"
        "\n"
        "def c():\n"
        "    return 2\n"
        "\n"
        "def d():\n"
        "    return 3\n"
    )

    review = analyze_python_file(source, "demo.py")
    titles = [issue.title for issue in review.issues]

    assert titles[0] == "Use of eval"
    assert titles.count("Missing function docstring") == 2


def test_analyze_python_file_deduplicates_overlapping_findings(monkeypatch):
    _disable_llm(monkeypatch)

    source = (
        "import subprocess\n"
        "\n"
        "def run_user_code(code):\n"
        "    return eval(code)\n"
        "\n"
        "def deploy(branch_name):\n"
        "    subprocess.call('git checkout ' + branch_name, shell=True)\n"
        "\n"
        "print(10 / 0)\n"
    )

    review = analyze_python_file(source, "snippet.py")
    titles = [issue.title for issue in review.issues]

    assert titles.count("Use of eval") <= 1
    assert titles.count("shell=True in subprocess") <= 1


def test_detect_language_marks_python_and_generic_files():
    assert detect_language("main.py") == ("Python", True)
    assert detect_language("index.js") == ("JavaScript", False)
    assert detect_language("service.java") == ("Java", False)


def test_analyze_source_file_uses_generic_path_for_non_python(monkeypatch):
    _disable_llm(monkeypatch)
    source = "function add(a, b) {\n  return a + b;\n}\n"

    review = analyze_source_file(source, "app.js")

    assert review.path == "app.js"
    assert "JavaScript" in review.summary
    assert review.lint_output == "Language-aware local linting is not configured for JavaScript."
    assert review.validation["status"] == "passed"
    assert any("model-assisted" in issue.details for issue in review.issues)


def test_analyze_generic_file_handles_empty_input_without_llm(monkeypatch):
    _disable_llm(monkeypatch)

    review = analyze_generic_file("", "schema.sql", "SQL")

    assert review.validation["status"] == "failed"
    assert any(issue.title == "Empty input" for issue in review.issues)


def test_analyze_project_supports_mixed_language_sources(monkeypatch):
    _disable_llm(monkeypatch)
    result = analyze_project(
        [
            ("sample.py", "def add(a, b):\n    return a + b\n"),
            ("frontend.js", "function x() { return 1; }\n"),
        ]
    )

    assert result["project_summary"]["files_analyzed"] == 2
    assert {review["path"] for review in result["file_reviews"]} == {"sample.py", "frontend.js"}
