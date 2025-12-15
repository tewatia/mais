# MAIS Backend (FastAPI + LangChain)

## Prereqs

- Python 3.11+

## Setup

From repo root:

```bash
python -m venv .venv
```

Activate venv:

- Linux / macOS:

```bash
source .venv/bin/activate
```

- Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

Install:

```bash
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

> Note: always use a virtual environment (`.venv`) for MAIS. LangChain + provider SDKs move quickly, and a clean venv avoids dependency conflicts with other Python projects.

## Configure

Copy env file:

```bash
# Linux / macOS
cp backend/env.example backend/.env

# Windows
copy backend\env.example backend\.env
```

The backend loads `backend/.env` automatically using `python-dotenv` at startup.

Set at least one provider key (depending on the model(s) you choose):

- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- Google: `GOOGLE_API_KEY`

## Run

```bash
uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

Health:

- `GET http://localhost:8000/healthz`

## Runtime behavior notes (MVP)

- **Single active simulation**: the server allows only one running simulation at a time. Starting another returns `409` until the current one is stopped.
- **Stop is immediate**: `POST /api/simulations/{id}/stop` cancels the running asyncio task so the backend stops processing quickly (subject to provider SDK behavior).
- **Orphan auto-stop**: if nobody is listening on the SSE stream, the simulation auto-stops after `ORPHAN_GRACE_SECONDS` (default 5s) to avoid burning tokens unintentionally.

## Tests

```bash
pytest -q
```
