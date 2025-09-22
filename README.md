# Smart Doc Checker — Minimal Prototype

## What this prototype contains
- `backend/app.py` — FastAPI prototype with:
  - `/upload` endpoint (accepts up to 3 files)
  - `/analyze` endpoint (runs simple rule-based conflict detection)
  - `/pathway/webhook` endpoint (mock)
  - `/billing/charge` endpoint (mock Flexprice)
- `frontend/index.html` — Minimal single-page UI to upload files and run analysis
- `sample_docs/doc_a.txt` and `sample_docs/doc_b.txt` — example docs to test
- `requirements.txt` — dependencies

## How to run (locally)
1. Create a Python virtual env:
   ```bash
   python -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Start the FastAPI backend:
   ```bash
   uvicorn backend.app:app --reload --port 8000
   ```
3. Open `frontend/index.html` in your browser (File -> Open). The frontend uses `fetch` to call the backend at http://localhost:8000.
4. Or use curl/postman to upload files to `POST http://localhost:8000/upload` then POST to `/analyze`.

## Notes
- This is a minimal hackathon prototype. The LLM-based contradiction checks are mocked — you can replace `mock_llm_contradiction` in `backend/app.py` with a real OpenAI call.
- Pathway integration is simulated via `/pathway/webhook`: POST a JSON payload with `{"doc_id": "policy-1", "new_text": "..."}` to trigger re-analysis.
