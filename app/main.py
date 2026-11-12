import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import models  # noqa: F401  (register tables)
from . import ledger
from .config import settings
from .db import Base, SessionLocal, engine
from .events import bus
from .ledger import InsufficientFunds
from .paypal import PayPalError, paypal
from .routers import agent_bank, core, negotiator, scam_shield, time_machine, txns, voice_cfo


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # hackathon shortcut; use Alembic for real migrations
    bus.loop = asyncio.get_running_loop()
    with SessionLocal() as db:
        ledger.get_system_account(db)
        db.commit()
    yield


app = FastAPI(title="Agent Bank - PayPal-backed AI agents", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (core.router, txns.router, agent_bank.router, negotiator.router, time_machine.router, voice_cfo.router, scam_shield.router):
    app.include_router(r)


@app.exception_handler(PayPalError)
async def _paypal_err(_: Request, e: PayPalError):
    return JSONResponse({"error": "paypal_error", "detail": str(e)}, status_code=502)


@app.exception_handler(InsufficientFunds)
async def _funds_err(_: Request, e: InsufficientFunds):
    return JSONResponse({"error": "insufficient_funds", "detail": str(e)}, status_code=402)


@app.get("/health")
def health():
    return {"ok": True, "paypal_mock": paypal.mock, "env": settings.env}
