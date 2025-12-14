# MAIS (Multi-Agent Interaction Studio)

![Banner](./assets/banner.png)


MAIS is a web app for running **turn-based, multi-actor LLM simulations** with real-time streaming.

## What if…?
What if large language models could talk to each other?
What if Gemini 3 Pro could debate GPT-5.2 on safety versus capability, or argue with Claude about whether reasoning should be cautious or bold?
What if Isaac Newton could debate Friedrich Nietzsche on determinism and free will?
What if Marie Curie challenged Steve Jobs on whether innovation should prioritize safety or speed?
What if Nelson Mandela sat across from Niccolò Machiavelli to argue whether moral compromise is ever justified for power?

This project creates a round table where multiple AI models talk to each other—not just different personas, but different systems. Imagine ChatGPT debating Gemini on strategy, Claude critiquing both for hidden assumptions, or a local open-source model playing the skeptic.

You can configure:
- **Interaction modes**: Debate, Collaboration, Interaction, Custom
- **Actors**: persona, model, optional system prompt
- **Debate**: per-actor side (For/Against/Auto) + optional Moderator
- **Collaboration**: per-actor responsibility + optional Synthesizer/Lead

The UI renders messages as **Markdown** (code blocks, lists, etc.) and streams tokens live via **Server-Sent Events (SSE)**.

---

## Repository structure
- `backend/`: FastAPI + LangChain (multi-provider LLM calls)
- `frontend/`: React + Vite + TypeScript
- `FUNCTIONAL_REQUIREMENTS.md`: product requirements (MVP)
- `TECHNICAL_DOCUMENTATION.md`: high-level architecture
- `backend/TECHNICAL_DOCUMENTATION.md`: detailed backend API + flow

---

## Prerequisites
- **Python 3.11+**
- **Node.js 18+**

---

## Quickstart (local dev)

### 1) Backend (FastAPI)
From repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
copy backend\env.example backend\.env
```

Edit `backend/.env` and set at least one provider key (depending on models you use):
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`

Run:

```powershell
uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

Backend runs at `http://localhost:8000`.

### 2) Frontend (React)
From repo root:

```powershell
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

---

## How to use (UI)
1. Pick an interaction mode in the left panel.
2. Set the topic and configure actors in the center panel.
3. Click **Start Simulation** and watch the Live Stage stream.
4. Click **Stop** to cancel the run.
5. Click **Download** to save the transcript JSON.

Notes:
- The server enforces **one active simulation at a time** (starting a second returns `409`).
- If no client is listening to the SSE stream, the backend auto-stops after `ORPHAN_GRACE_SECONDS`.

---

## API examples (curl)

### Health check

```bash
curl http://localhost:8000/healthz
```

### Fetch available models (catalog)

The frontend pulls model options from the backend:

```bash
curl http://localhost:8000/api/models
```

The catalog is defined in `backend/model_catalog.json` (editable).

### Start a debate (2 actors + moderator)

```bash
curl -X POST http://localhost:8000/api/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Should AI systems be open source?",
    "mode": "debate",
    "stage": "This is a debate setting. Participants must argue for or against the topic and challenge weak assumptions.",
    "turn_limit": 6,
    "agents": [
      { "name": "Alice", "model": "gpt-4o-mini", "debate_side": "for" },
      { "name": "Bob",   "model": "gpt-4o-mini", "debate_side": "against" }
    ],
    "moderator": { "enabled": true, "model": "gpt-4o-mini", "frequency_turns": 2 },
    "synthesizer": { "enabled": false }
  }'
```

### Start a collaboration (2 actors + synthesizer)

```bash
curl -X POST http://localhost:8000/api/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Plan a 2-day weekend trip to Kyoto",
    "mode": "collaboration",
    "stage": "This is a collaborative setting. Build on each other and converge on a practical plan.",
    "turn_limit": 7,
    "agents": [
      { "name": "Alice", "model": "gpt-4o-mini", "responsibility": "logistics + schedule" },
      { "name": "Bob",   "model": "gpt-4o-mini", "responsibility": "budget + food recommendations" }
    ],
    "moderator": { "enabled": false },
    "synthesizer": { "enabled": true, "model": "gpt-4o-mini", "frequency_turns": 2 }
  }'
```

### Stream events (SSE)

```bash
curl -N http://localhost:8000/api/simulations/<SIM_ID>/events
```

### Stop a simulation

```bash
curl -X POST http://localhost:8000/api/simulations/<SIM_ID>/stop
```

### Download transcript JSON

```bash
curl http://localhost:8000/api/simulations/<SIM_ID>/download
```

---

## Tests

Backend:

```powershell
cd backend
pytest -q
```

Frontend:

```powershell
cd frontend
npm test
```

---

## Documentation
- Backend API + execution flow: `backend/TECHNICAL_DOCUMENTATION.md`


