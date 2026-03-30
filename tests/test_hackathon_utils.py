from pathlib import Path

from hackathon_utils import (
    build_code_comparison_rows,
    collect_reviewable_files_from_directory,
    load_uploaded_reviewable_files,
    render_code_panel,
)


def test_build_code_comparison_rows_marks_added_and_removed_lines():
    rows = build_code_comparison_rows("a = 1\nb = 2\n", "a = 1\nb = 3\nc = 4\n")

    assert any(row["left_state"] == "removed" for row in rows)
    assert any(row["right_state"] == "added" for row in rows)


def test_render_code_panel_contains_line_numbers_and_states():
    rows = build_code_comparison_rows("print('bad')\n", "print('good')\n")

    html = render_code_panel(rows, "left")

    assert "compare-line-number" in html
    assert "compare-row--removed" in html


def test_collect_reviewable_files_from_directory_supports_multiple_languages(tmp_path):
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "index.js").write_text("console.log('hi')\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore me\n", encoding="utf-8")

    results = collect_reviewable_files_from_directory(str(tmp_path), max_files=10)
    names = {name for name, _ in results}

    assert "app.py" in names
    assert "index.js" in names
    assert "notes.txt" not in names


def test_load_uploaded_reviewable_files_filters_unsupported_extensions():
    class FakeUpload:
        def __init__(self, name: str, content: str):
            self.name = name
            self._content = content.encode("utf-8")

        def getvalue(self):
            return self._content

    uploads = [
        FakeUpload("main.py", "print('hi')\n"),
        FakeUpload("component.ts", "const x = 1;\n"),
        FakeUpload("notes.txt", "skip\n"),
    ]

    results = load_uploaded_reviewable_files(uploads)

    assert [name for name, _ in results] == ["main.py", "component.ts"]
