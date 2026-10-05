# DisputeLens

Local RAG for merchant disputes. The planned assistant retrieves relevant passages from fictional policies, answers with source citations, and admits when evidence is missing.

## Current state

Step 1: Python project scaffold. Retrieval, local model calls and evaluation are not implemented yet.

## Setup

Use Python 3.11 or newer. The initial environment was verified with Python 3.14.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
python -c "import disputelens, httpx, numpy, dotenv, pytest; print('Environment ready')"
```

`requirements-lock.txt` records the resolved dependency versions for the initial environment. To reproduce those versions:

```bash
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
```

## Next steps

1. Verify LM Studio chat using Qwen 4B.
2. Verify a separate local embedding model.
3. Build document ingestion, retrieval, grounded answers and error handling.
4. Evaluate ten questions, then compare Qwen 4B and 9B with identical retrieved context.
5. Document actual results and rehearse a terminal demo.

The local `DisputeLens.xlsx` workbook holds the build plan and evaluation templates. It is ignored by Git.

## Layout

- `src/disputelens/`: application code
- `tests/`: targeted checks added as functionality is implemented
- `data/sample/`: explicitly fictional policy documents
- `eval/`: questions and safe evaluation summaries
- `docs/`: implementation decisions and demo notes

LM Studio will run inference on your laptop. GitHub hosts the code, not a live model server. Codex assists with development; source verification and evaluation remain human-reviewed.
