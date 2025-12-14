# MAIS Frontend (React + Vite)

## Prereqs
- Node.js 18+ (recommended)

## Setup

```bash
cd frontend
npm install
```

## Configure

Optional env:
- Copy `frontend/env.example` to `frontend/.env` and set `VITE_BACKEND_URL=http://localhost:8000`
- Or leave it empty and use the built-in **Vite proxy** to `http://localhost:8000` (see `vite.config.ts`)

## Run

```bash
npm run dev
```

The UI will be at `http://localhost:5173`.

## Tests

```bash
npm test
```
