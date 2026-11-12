# Agent Bank - PayPal-backed AI agent backend

One FastAPI backend, five demos: **Agent Bank, Negotiator Bot, Money Time Machine, Voice CFO, Scam Shield**.

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # empty PayPal/Gemini keys = MOCK mode, everything still works
uvicorn app.main:app --reload
# docs: http://localhost:8000/docs      tests: python -m pytest -q
```
Postgres: `docker compose up --build` (or set `DATABASE_URL`).

## Architecture
- `paypal/client.py` - Orders v2, Refunds, Payouts, Transaction Search, webhook verify (+ mock mode)
- `ledger.py` - double-entry ledger; agent wallets are ledger accounts, PayPal only at top-up / cash-out
- `policy.py` - **every** money action goes through `run_action()`: limits, approval threshold, audit log. LLM proposes, code decides
- `agent_runtime.py` - JSON tool loop; `llm.py` - Gemini wrapper with deterministic fallbacks
- `events.py` - in-process pub/sub -> WebSockets (swap for Redis if you run multiple workers)

## Demo flow (header `X-API-Key` from register)
```bash
KEY=$(curl -s -XPOST localhost:8000/auth/register -H 'content-type: application/json' -d '{"name":"Anu"}' | python -c 'import sys,json;print(json.load(sys.stdin)["api_key"])')
H="X-API-Key: $KEY"; J='content-type: application/json'
curl -XPOST localhost:8000/wallet/faucet -H "$H" -H "$J" -d '{"amount_cents":50000}'
# Agent Bank
curl -XPOST localhost:8000/agents -H "$H" -H "$J" -d '{"name":"Boss","role":"manager"}'
curl -XPOST localhost:8000/agents -H "$H" -H "$J" -d '{"name":"Writer","skills":["copy"]}'
curl -XPOST localhost:8000/agents/1/fund -H "$H" -H "$J" -d '{"amount_cents":10000}'
curl -XPOST localhost:8000/jobs -H "$H" -H "$J" -d '{"manager_agent_id":1,"title":"Write a blurb","description":"Product blurb","budget_cents":4000}'
curl -XPOST localhost:8000/jobs/1/run -H "$H"     # watch: ws://localhost:8000/ws/market ; then GET /dashboard
# Negotiator
curl -XPOST localhost:8000/negotiations -H "$H" -H "$J" -d '{"product":"Headphones","list_price_cents":4000,"budget_cents":3200}'
# Time Machine / CFO
curl -XPOST localhost:8000/txns/seed-demo -H "$H"
curl -XPOST localhost:8000/simulate -H "$H" -H "$J" -d '{"merchant":"Netflix","years":3}'
curl -XPOST localhost:8000/cfo/ask -H "$H" -H "$J" -d '{"text":"refund the angry customer from yesterday and tell me why sales dipped"}'
# Scam Shield
curl -XPOST localhost:8000/protected-payments -H "$H" -H "$J" -d '{"text":"pay me on WhatsApp, friends and family, urgent","description":"Camera","amount_cents":2500}'
```

## Notes
- **Voice**: frontend uses browser Web Speech API (SpeechRecognition + speechSynthesis) and calls `POST /cfo/ask`. Spoken "yes/confirm" is handled by code, never the LLM.
- **Real PayPal**: set sandbox creds + `PAYPAL_WEBHOOK_ID`; point the webhook to `/webhooks/paypal`. Enable *Transaction Search* on the app for `/txns/sync` (data lags ~3h). Verify exact endpoint payloads in PayPal docs.
- **Gemini**: set `GEMINI_API_KEY` (and `GEMINI_MODEL` if the default name is retired).
- **Not production**: `create_all` instead of migrations, API-key auth, unauthenticated WebSockets, in-memory bus. Harden before real money.
