# LLM Chatbot with Key Failover and Response Caching

React + FastAPI + SQLite chatbot using LiteLLM for key failover and caching.

## 1. Live URLs

- Frontend: https://lyft-chatbot.vercel.app
- Backend: https://lyft-chatbot-backend.onrender.com (health: `/health`, docs: `/docs`)
- Repo: https://github.com/vinitsoni21/lyft_chatbot

Note: the backend is on Render's free plan, so the first request after idle can take 30-50 seconds.

## 2. Run locally

### With Docker
```bash
cp backend/.env.example .env   # then put 2 real keys in LLM_API_KEYS
make up                        # frontend :3000, backend :8000
make down
```

### Without Docker
Backend:
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # add 2 real keys
uvicorn app.main:app --port 8000
```
Frontend:
```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```
Tests: `cd backend && python -m pytest tests -v`

## 3. Design decisions

- **Key fallback:** keys come from `LLM_API_KEYS` (key_1, key_2, ...). For each request the keys are tried in order; any failure (429, quota, 5xx, timeout, empty reply) moves to the next key. If all fail, the API returns 503 `{"detail": "all providers unavailable"}`. LiteLLM internal retries are off so failover is fast and predictable. `X-Simulate-Failure` (enabled by `ENABLE_FAILURE_SIMULATION=true`) makes chosen keys fail for one request only.
- **Caching:** LiteLLM's built-in in-memory cache. The cache key is the model plus the full message list (system prompt + history + new message), so the same first message in a new session is a hit, and different messages never are. Hits report `LLM_CACHE`, `key_id: null`, and the stored token usage. The cache is in memory, so it resets on restart.
- **SQLite session storage:** history is stored per `session_id` in the `messages` table (path from `DATABASE_URL`, on a Docker volume at `/data`). The user and assistant messages are saved together only after a successful reply, so failed requests (422/503) leave no trace. Note: Render's free plan has no persistent disk, so history there resets on restart.
- **Tokens:** reported per request (system + history + new message), never as a running total.

## 4. Verification

Replace `$URL` with the backend URL.

```bash
# Cache hit: send the same first message in two different sessions
curl -s -X POST $URL/chat -H "Content-Type: application/json" -d '{"session_id":"a","message":"What is the capital of France?"}'
curl -s -X POST $URL/chat -H "Content-Type: application/json" -d '{"session_id":"b","message":"What is the capital of France?"}'   # LLM_CACHE

# Failover
curl -s -X POST $URL/chat -H "Content-Type: application/json" -H "X-Simulate-Failure: key_1=429" -d '{"session_id":"c","message":"Name a colour."}'   # key_2, fallback_attempts 1
curl -s -i -X POST $URL/chat -H "Content-Type: application/json" -H "X-Simulate-Failure: *=429" -d '{"session_id":"d","message":"Name a fruit."}'     # 503

# History
curl -s $URL/sessions/a/messages
```

In the UI, each assistant reply shows source, model, latency and input/output tokens.

## 5. Setup Used

- Editor: VS Code
- AI tools: Claude (code assistant)
- Stack: React (Vite), FastAPI, LiteLLM, SQLite, Docker, Render, Vercel

## 6. Bonus features

- Optional system prompt field in the UI (stored per session).
- Backend tests (pytest) covering validation, failover, 503 and history.