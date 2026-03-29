# Agentic AI Code Reviewer

Hackathon-ready Streamlit app that reviews Python code with:

- Static AST checks
- PyLint findings
- Optional LLM-powered semantic review
- Suggested improved code
- Validation and before/after scoring

## Run

```powershell
.\test\Scripts\python.exe -m streamlit run hackathon_app.py
```

## Optional LLM setup

Set these environment variables before launching the app:

```powershell
$env:LLM_API_KEY="your-key"
$env:LLM_API_BASE="https://openrouter.ai/api/v1"
$env:LLM_MODEL="openai/gpt-4o-mini"
```

If no API key is set, the app still works using local static analysis only.

## Demo flow

1. Paste code, upload `.py` files, or point to a local folder.
2. Run analysis and walk judges through the agent timeline.
3. Show issues, quality score, validation result, and code diff.
4. Explain that LLM review can be enabled by adding an API key.
