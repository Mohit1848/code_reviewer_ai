# Agentic AI Code Reviewer

Hackathon-ready Streamlit app that reviews source code with:

- Deep Python-specific AST checks
- PyLint findings for Python
- Generic model-assisted review for other languages
- Hugging Face powered semantic review with `deepseek-ai/DeepSeek-R1`
- Suggested improved code
- Validation and before/after scoring

## Run

```powershell
python -m pip install -r requirements.txt
python -m streamlit run hackathon_app.py
```

## Optional LLM setup

Set these environment variables before launching the app:

```powershell
$env:HF_TOKEN="your-hugging-face-token"
$env:HF_MODEL="deepseek-ai/DeepSeek-R1"
$env:HF_API_BASE="https://router.huggingface.co/v1"
$env:HF_ENDPOINT_URL=""
```

Or create a `.env` file in the project root:

```env
HF_TOKEN=your-hugging-face-token
HF_MODEL=deepseek-ai/DeepSeek-R1
HF_API_BASE=https://router.huggingface.co/v1
HF_ENDPOINT_URL=
```

`HF_MODEL` uses a Hub model ID through Hugging Face Inference Providers. If you have a dedicated deployed Inference Endpoint, set `HF_ENDPOINT_URL` and the app will send requests there instead.

If you see a `403` mentioning "Inference Providers", your token can read the config but is not allowed to call Hugging Face's routed provider API. In that case either:

- create or use a token with Inference Providers permission, or
- deploy a dedicated Hugging Face Inference Endpoint and set `HF_ENDPOINT_URL`

If no token is set, the app still works using local static analysis only.

## Demo flow

1. Paste code, upload supported source files, or point to a local folder/repo.
2. Run analysis and walk judges through the agent timeline.
3. Show issues, quality score, validation result, and code diff.
4. Explain that Python gets the deepest local review, while other languages use the generic LLM review path.

## Language Support

- Deep local review: Python
- Generic LLM review: JavaScript, TypeScript, Java, C, C++, C#, Go, Ruby, PHP, Rust, Swift, Kotlin, Scala, HTML, CSS, SQL, JSON, YAML, Shell

The app keeps Python as the strongest path for hackathon demos, while still letting you review mixed-language folders and repositories.
