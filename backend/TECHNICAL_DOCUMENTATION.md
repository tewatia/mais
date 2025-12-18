# MAIS Backend — Technical Documentation (MVP)

## Purpose
The MAIS backend is a **FastAPI** service responsible for:
- Validating simulation configuration (topic, agents, mode, limits, moderator)
- Calling LLMs through **LangChain** (multi-provider)
- Running a **turn-based simulation loop** (Debate / Collaboration / Interaction)
- Streaming tokens/messages to clients using **Server-Sent Events (SSE)**
- Supporting **stop** and **download transcript**

## Run & configuration

### Env loading (dotenv)
The backend loads env vars at runtime using `python-dotenv`:
- Primary file: `backend/.env`
- Fallback file: `backend/env`

OS environment variables are used as well. By default `.env` does **not** override already-set env vars.
To force override for local dev, set `DOTENV_OVERRIDE=true`.

See `backend/env.example` for all variables.

### Start the server
From repo root (venv active):

```bash
uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

## API overview
Base URL: `http://localhost:8000`

### Health
#### `GET /healthz`
- **Use**: liveness check
- **Response 200**:
```json
{ "status": "ok" }
```

## Simulation APIs
All simulation endpoints live under `/api`.

### 0) List available models
#### `GET /api/models`
Returns the model catalog used by the frontend dropdowns.

The catalog is loaded from:
- default: `backend/model_catalog.json`
- override (optional): `MODEL_CATALOG_PATH` environment variable

**Response 200**
```json
{
  "models": [
    { "id": "gpt-4o-mini", "display_name": "GPT-4o Mini", "provider": "openai" }
  ]
}
```

### 1) Start simulation
#### `POST /api/simulations`
Creates a simulation and starts an async background task to run it.

**Request body**
```json
{
  "topic": "Is AI sentient?",
  "mode": "debate",
  "stage": "This is a debate setting. Participants must argue for or against the topic and challenge weak assumptions.",
  "turn_limit": 10,
  "agents": [
    {
      "name": "Actor 1",
      "model": "gpt-4o-mini",
      "persona": "Custom",
      "system_prompt": "Be concise.",
      "debate_side": "for",
      "provider": "openai",
      "temperature": 0.7,
      "max_tokens": 1024,
      "context_size": null
    },
    {
      "name": "Actor 2",
      "model": "claude-3-sonnet",
      "persona": "Custom",
      "system_prompt": "Be skeptical.",
      "debate_side": "against",
      "provider": "anthropic",
      "temperature": null,
      "max_tokens": null,
      "context_size": null
    }
  ],
  "moderator": {
    "enabled": false,
    "model": "gpt-4o-mini",
    "provider": "openai",
    "frequency_turns": 2,
    "system_prompt": "Optional moderator prompt...",
    "temperature": null,
    "max_tokens": null,
    "context_size": null
  },
  "synthesizer": {
    "enabled": false,
    "model": "gpt-4o-mini",
    "provider": "openai",
    "frequency_turns": 2,
    "system_prompt": "Optional synthesizer prompt...",
    "temperature": null,
    "max_tokens": null,
    "context_size": null
  }
}
```

**Notes**
- `mode` options:
  - `debate`, `collaboration`, `interaction`, `custom`
- `stage` is provided by the frontend and is **prepended to each agent's system prompt**. The backend does not hardcode mode instructions.
- `agents` must be **2..4**, and agent names must be **unique**
- `turn_limit` is capped by server config (default max 40)
- `provider` is optional; if omitted, the backend infers it from the model name
- **Debate auto side (deterministic)**:
  - If an actor omits `debate_side` (Auto), the backend assigns it deterministically:
    - odd actor index (`agent_id` 1, 3, ...) → `for`
    - even actor index (`agent_id` 2, 4, ...) → `against`
- **Turn limit semantics**:
  - `turn_limit` is interpreted as **"number of rounds"** where each agent speaks once per round
  - Effective max actor turns = `turn_limit` × number of agents
  - Example: `turn_limit=2` with 3 agents → each agent speaks 2 times → 6 total actor turns
  - Moderator and synthesizer turns do NOT count against this limit
- **Moderator frequency**:
  - `frequency_turns` is based on **actor turns**, not global turn counter
  - Example: `frequency_turns=2` means moderator runs after 2 actor turns, 4 actor turns, etc.
  - Moderator **always runs once at the end** as a final summary (if enabled), even if not scheduled
- **Synthesizer frequency**:
  - `frequency_turns` is based on **collaboration rounds** (full passes where all agents speak once)
  - Synthesizer **always runs once at the end** as a final summary (if enabled), even if not scheduled
- **Generation settings (optional)**:
  - `temperature` (float, 0.0-2.0): controls randomness; `null` uses provider default
  - `max_tokens` (int): max output tokens; `null` or `0` omits this param → provider default
  - `context_size` (int): context window size; `null` or `0` omits this param; only Ollama (`num_ctx`) supports override
  - These fields are available for **agents**, **moderator**, and **synthesizer**
  - In the UI, these settings appear in a collapsible section right below the model dropdown
- **Removed limits**: 
  - Server no longer enforces `max_topic_chars`, `max_prompt_chars`, or `max_stage_chars`
  - Pydantic still enforces basic min/max on model/persona names, but allows arbitrarily long topics, stages, and system prompts

**Response 200**
```json
{ "simulation_id": "b3f2c4e6-...." }
```

**Common errors**
- `400`: invalid payload / limits exceeded
- `409`: another simulation is already running (MVP allows one active simulation at a time)
- `500`: unexpected server error (server logs include full stack trace)

### 2) Stream simulation events (SSE)
#### `GET /api/simulations/{simulation_id}/events`
Streams events as **SSE** (`text/event-stream`).

**How clients should use it**
- Browser: `new EventSource(url)`
- CLI: `curl -N <url>`

**Keepalive**
If no events are available for 15 seconds, the server emits a keepalive comment:
```
: keepalive
```

#### Event types
Each SSE frame is emitted as:
```
event: <type>
data: <json>
```

Supported `event` values:
- **`status`**: lifecycle/typing updates
- **`token`**: incremental token chunks while an agent turn is streaming
- **`message`**: completed message for a turn
- **`error`**: friendly error message intended for the UI

#### `status` event
Examples:
```json
{ "status": "connected" }
```
```json
{ "status": "started" }
```
```json
{ "status": "typing", "name": "Agent A", "turn": 1 }
```
```json
{ "status": "finished" }
```
```json
{ "status": "stopped" }
```

#### `token` event
```json
{ "name": "Actor 1", "turn": 1, "token": "Hello", "role": "agent", "agent_id": 1 }
```

#### `message` event
```json
{
  "name": "Actor 1",
  "turn": 1,
  "content": "Hello world.",
  "role": "agent",
  "model": "gpt-4o-mini",
  "agent_id": 1
}
```

#### `error` event
```json
{ "message": "OpenAI API key is not configured on the server." }
```

### 3) Stop a simulation
#### `POST /api/simulations/{simulation_id}/stop`
Stops the simulation.

**Behavior (MVP)**
- Sets the in-memory cancel flag
- Cancels the running asyncio task (so stop is immediate)

**Response 200**
```json
{ "status": "ok" }
```

**Errors**
- `404`: unknown simulation id

### 4) Download transcript
#### `GET /api/simulations/{simulation_id}/download`
Returns the full transcript (JSON).

**Response 200**
```json
{
  "simulation_id": "b3f2c4e6-....",
  "topic": "Is AI sentient?",
  "mode": "debate",
  "messages": [
    { "role": "agent", "name": "Agent A", "content": "...", "turn": 1, "model": "gpt-4o-mini" }
  ]
}
```

**Errors**
- `409`: transcript not available yet (simulation still running)
- `404`: unknown simulation id

## Execution flow (end-to-end)
1. Client calls `POST /api/simulations` with configuration.
2. Backend creates an in-memory `SimulationState` and starts an async background task to run the simulation.
3. Client opens an SSE stream: `GET /api/simulations/{id}/events`.
4. The simulation runner loops turn-by-turn, streams tokens, and publishes events to all SSE subscribers.
5. The simulation ends by reaching `turn_limit` or by a stop request; the transcript becomes available via `/download`.

## Detailed interaction handling (what happens after “Start Simulation”)
This section describes the runtime behavior and how agent interactions are produced and streamed.

### Components involved
- **API handler**: `backend/app/api/simulations.py`
  - Creates the simulation and returns a `simulation_id`.
- **Simulation manager**: `backend/app/simulations/manager.py`
  - Stores all simulations in-memory in a dict: `{simulation_id -> SimulationState}`
  - Starts the background asyncio task that runs the simulation.
- **Simulation state**: `backend/app/simulations/state.py`
  - Holds cancel flags, transcript, and **subscriber queues** for streaming.
- **Runner**: `backend/app/simulations/runner.py`
  - Implements the turn-based loop and emits events (`status`, `token`, `message`, `error`).
- **SSE endpoint**: `GET /api/simulations/{id}/events` in `backend/app/api/simulations.py`
  - Subscribes the client to events by attaching an `asyncio.Queue` to the simulation state.

### Timeline / sequence (high level)
You can think of the flow like this:

1. **Start request**
   - Client sends `StartSimulationRequest` to `POST /api/simulations`.
   - Server validates bounds (topic length, turn limit, etc.).
   - Server creates `SimulationState(simulation_id, request=body)`.
   - Server starts a background task: `asyncio.create_task(run_simulation(...))`.
   - Response returns immediately: `{ "simulation_id": "..." }`.

2. **Client opens SSE**
   - Client calls `GET /api/simulations/{id}/events`.
   - Server calls `state.subscribe()` which creates a new `asyncio.Queue` and stores it in `state.subscribers`.
   - Server sends an initial `status` event: `{ "status": "connected" }`.
   - From this point, the server yields any queued events as SSE frames.

3. **Runner publishes events**
   - The runner publishes events using `await state.publish(event)`.
   - `publish()` pushes the event to every subscriber queue (`q.put_nowait(event)`).
   - Each connected SSE client receives the events independently (fan-out).

### SSE streaming mechanics (important details)
- **Keepalive**: if no events arrive for ~15 seconds, the SSE endpoint emits a comment `: keepalive` so proxies/browsers don’t time out the connection.
- **Connection close**: the SSE loop exits when:
  - the client disconnects, or
  - the simulation is finished **and** the queue is empty (no more events to flush).
- **No replay**: events are not persisted for late subscribers. If a client connects mid-simulation, it will only see events emitted **after** it subscribed. (The final transcript is always available via `/download` once ready.)

### Turn-based interaction loop (how agent-to-agent messages are produced)
The core loop is in `run_simulation(...)`:

- A list `transcript: list[TranscriptMessage]` is maintained in memory.
- The loop increments a shared **turn counter**.
- Each agent gets a turn in order (`for agent in req.agents`), and for each turn the runner:
  1. Builds the model instance via `build_chat_model(...)` (provider key must exist).
  2. Builds a **message array** (not one big user prompt):
     - **SystemMessage** includes:
       - `Topic: <topic>`
       - `You are <name>`
       - participant awareness (who you are speaking with)
       - mode rules (Debate side, Collaboration responsibility, etc.)
       - persona prompt (if any)
       - `Setting: <stage>`
     - History uses:
       - **AIMessage** for the current speaker’s own prior messages
       - **HumanMessage** for everything else (other actors + moderator/synthesizer), grouped as needed to keep a clean alternating structure
  3. Emits `status: typing` for that agent and turn.
  4. Calls `llm.astream([SystemMessage(...), HumanMessage(...)])` and streams partial chunks:
     - For each chunk, extracts `chunk.content` and publishes `token` events.
  5. When streaming completes, it concatenates all tokens into a final string, appends to transcript, and publishes a final `message` event.

#### History grouping rules (important)
- If there are only 2 actors, “other actor” history can be sent without name prefixes.
- With 3+ actors, “other” messages are grouped into a HumanMessage and prefixed like:
  - `Alice: ...`
  - `Bob: ...`
- Moderator and Synthesizer messages are always included in the “other” HumanMessage history (prefixed).

### Moderator behavior (MVP)
Moderator is **optional** and only used when:
- `moderator.enabled == true`
- `mode == debate`
- `moderator.model` is provided
- `turn % moderator.frequency_turns == 0`

When invoked, it runs as another streamed turn (role: `"moderator"`, name: `"Moderator"`) and emits the same `status/token/message` events.

### Synthesizer behavior (Collaboration)
Synthesizer/Lead is **optional** and only used when:
- `synthesizer.enabled == true`
- `mode == collaboration`
- `synthesizer.model` is provided

Scheduling:
- It triggers after every N **collaboration rounds** (a full pass through all actors), where N is `synthesizer.frequency_turns`.
- It also runs **once at the end** if enabled, even if not scheduled by frequency.

The synthesizer receives history in the same message structure as actors and outputs JSON (see below).

### Structured JSON termination (moderator/synthesizer)
Moderator and Synthesizer can end the simulation early using a JSON response:
```json
{"terminate": true, "message": "..." }
```
The JSON contract is appended by the backend (frontend does not need to include it in prompts).

### Stop / cancellation behavior
When the client calls `POST /api/simulations/{id}/stop`:
- The manager sets `state.cancel_event`.
- The manager also cancels `state.task` to stop the background task promptly.
- The runner checks `state.cancel_event.is_set()`:
  - before starting new turns
  - during token streaming (inside the `async for chunk in llm.astream(...)` loop)
- When cancellation is observed, the runner exits and emits `status: stopped`.

### Orphan auto-stop (no listeners)
To avoid burning tokens unintentionally, the runner stops automatically when nobody is listening:
- If no SSE client connects soon after start, the runner will stop after `ORPHAN_GRACE_SECONDS` (default 5s).
- If all SSE subscribers disconnect mid-simulation, the simulation is cancelled after the same grace window.

### Error handling during interactions
Two categories matter:
- **FriendlyLLMError** (safe to show):
  - e.g., missing API key, unsupported provider/model, server-side bounds exceeded
  - the runner publishes an `error` event with a user-safe message, then `status: error`, and stops.
- **Unexpected exceptions** (not safe to show raw):
  - logged with stack trace on the server
  - the SSE stream receives a generic `error` event such as “A model call failed…” and `status: error`.

### Concurrency notes (MVP)
- One simulation runs in a single asyncio task.
- Multiple clients can subscribe to the same simulation; events are fanned out to all of them.
- State is in-memory; restarting the server loses all running simulations and transcripts.

## Logging & tracing
### Request ID
The backend generates/propagates `x-request-id` for every HTTP request:
- included in server logs
- returned to the client in the response header

### Exception traces
Unhandled server errors are logged with full stack traces (`logger.exception(...)`).
User-facing responses remain friendly and do not expose sensitive details.

## Security & limits (MVP)
- Provider keys are **server-side only** (never sent from UI)
- Turn/topic/prompt sizes are bounded
- CORS restricted to configured origins
- In-memory rate limiting middleware protects endpoints (MVP; not multi-instance safe)

## Known MVP limitations
- Simulation state is stored **in-memory** (lost on restart; single-node only)
- Rate limiter is in-memory (not shared across instances)
- No persistent storage for transcripts yet


