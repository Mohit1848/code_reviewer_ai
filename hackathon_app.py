import textwrap

import streamlit as st

from hackathon_utils import collect_python_files_from_directory, generate_diff, load_uploaded_python_files
from reviewer_engine import analyze_project


st.set_page_config(page_title="Agentic AI Code Reviewer", layout="wide")

st.title("Agentic AI Code Reviewer")
st.caption("Hackathon-ready reviewer with static analysis, optional LLM feedback, scoring, and validation.")

with st.sidebar:
    st.header("Inputs")
    review_mode = st.radio(
        "Choose analysis mode",
        options=["Paste code", "Upload files", "Analyze local folder"],
    )
    st.markdown(
        """
        `LLM_API_KEY` enables optional semantic review.

        Optional env vars:
        `LLM_API_BASE`
        `LLM_MODEL`
        """
    )

sources: list[tuple[str, str]] = []

if review_mode == "Paste code":
    code = st.text_area("Paste Python code", height=320, placeholder="def add(a, b):\n    return a + b")
    snippet_name = st.text_input("Snippet name", value="snippet.py")
    if code.strip():
        sources = [(snippet_name, code)]

elif review_mode == "Upload files":
    uploaded_files = st.file_uploader(
        "Upload one or more Python files",
        type=["py"],
        accept_multiple_files=True,
    )
    sources = load_uploaded_python_files(uploaded_files)

else:
    folder_path = st.text_input("Local project path", value="D:\\code_review")
    max_files = st.slider("Max files", min_value=1, max_value=20, value=8)
    if folder_path.strip():
        sources = collect_python_files_from_directory(folder_path, max_files=max_files)
        if folder_path.strip() and not sources:
            st.warning("No Python files found in that folder, or the folder is inaccessible.")

analyze_clicked = st.button("Analyze Project", type="primary", use_container_width=True)

if analyze_clicked:
    if not sources:
        st.error("Provide Python code, upload files, or point to a folder with Python files.")
    else:
        with st.status("Agent loop running...", expanded=True) as status:
            st.write("Step 1: ingesting sources")
            st.write("Step 2: running AST heuristics and PyLint")
            st.write("Step 3: requesting optional LLM review")
            st.write("Step 4: validating suggested improvements")
            review = analyze_project(sources)
            status.update(label="Review complete", state="complete")

        summary = review["project_summary"]
        files = review["file_reviews"]

        metric1, metric2, metric3, metric4 = st.columns(4)
        metric1.metric("Files", summary["files_analyzed"])
        metric2.metric("Issues", summary["issues_found"])
        metric3.metric("Score Before", summary["score_before"])
        metric4.metric("Score After", summary["score_after"], delta=summary["score_after"] - summary["score_before"])

        st.subheader("Agent Timeline")
        for file_review in files:
            with st.expander(f"{file_review['path']} timeline", expanded=False):
                for step in file_review["agent_steps"]:
                    st.write(f"- {step}")

        st.subheader("Review Results")
        selected_path = st.selectbox("Choose a file", options=[item["path"] for item in files])
        selected_review = next(item for item in files if item["path"] == selected_path)

        left, right = st.columns([1.2, 1])

        with left:
            st.markdown("### Summary")
            st.write(selected_review["summary"])

            st.markdown("### Issues")
            for issue in selected_review["issues"]:
                severity = issue["severity"].upper()
                st.markdown(
                    textwrap.dedent(
                        f"""
                        **[{severity}] {issue['title']}**  
                        `{issue['category']}` from `{issue['source']}`  
                        {issue['details']}  
                        Suggestion: {issue['suggestion']}
                        """
                    )
                )

            st.markdown("### Validation")
            validation = selected_review["validation"]
            status_label = "PASS" if validation["status"] == "passed" else "FAIL"
            st.code(f"{status_label}: {validation['details']}")

        with right:
            st.markdown("### Diff")
            diff = generate_diff(selected_review["original_code"], selected_review["improved_code"])
            st.code(diff, language="diff")

            st.markdown("### Improved Code")
            st.code(selected_review["improved_code"], language="python")

            with st.expander("Raw PyLint output", expanded=False):
                st.code(selected_review["lint_output"] or "No PyLint output.")

st.divider()
st.subheader("Why this stands out in a demo")
st.markdown(
    """
    - Shows an agent-style loop instead of a single LLM response.
    - Combines deterministic static analysis with optional LLM reasoning.
    - Produces before/after quality scores, validation results, and code diffs.
    - Works locally even without an API key, which is useful for hackathon demos.
    """
)
