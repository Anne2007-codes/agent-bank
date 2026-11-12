import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import ledger, policy
from ..config import settings
from ..db import SessionLocal, get_db
from ..deps import current_user, user_account
from ..models import Account, AuditLog, Approval, LedgerEntry, Payment, User, WebhookEvent
from ..payments import create_checkout
from ..paypal import PayPalError, paypal

router = APIRouter(tags=["core"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    u = User(name=body.name, api_key=secrets.token_urlsafe(24))
    db.add(u)
    db.flush()
    ledger.create_account(db, "user", u.id, f"user:{u.id}")
    db.commit()
    return {"user_id": u.id, "api_key": u.api_key}


@router.get("/wallet")
def wallet(user: User = Depends(current_user), db: Session = Depends(get_db)):
    acc = user_account(db, user)
    rows = db.scalars(
        select(LedgerEntry).where(or_(LedgerEntry.debit_account_id == acc.id, LedgerEntry.credit_account_id == acc.id))
        .order_by(LedgerEntry.id.desc()).limit(20)
    ).all()
    return {
        "balance_cents": ledger.balance(db, acc.id), "currency": settings.currency,
        "entries": [{"id": e.id, "ts": e.ts, "memo": e.memo,
                     "amount_cents": e.amount_cents if e.credit_account_id == acc.id else -e.amount_cents} for e in rows],
    }


class AmountIn(BaseModel):
    amount_cents: int = Field(gt=0, le=500_000)


def settle_topup(db: Session, p: Payment):
    """Idempotent: credit the ledger exactly once per top-up payment."""
    if p.status == "COMPLETED":
        return
    acc = db.scalar(select(Account).where(Account.kind == "user", Account.owner_id == p.user_id))
    ledger.transfer(db, ledger.get_system_account(db).id, acc.id, p.amount_cents, "PayPal top-up", f"payment:{p.id}")
    p.status = "COMPLETED"


@router.post("/wallet/topup")
def topup(body: AmountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = create_checkout(db, user, body.amount_cents, "Agent Bank wallet top-up", kind="topup")
    db.commit()
    return {"payment_id": p.id, "order_id": p.paypal_id, "approve_url": p.meta["approve_url"]}


@router.post("/wallet/topup/{order_id}/capture")
def capture_topup(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(Payment).where(Payment.paypal_id == order_id, Payment.user_id == user.id, Payment.kind == "topup"))
    if not p:
        raise HTTPException(404, "top-up not found")
    if p.status != "COMPLETED":
        cap = paypal.capture_order(order_id)
        if cap["status"] != "COMPLETED":
            raise HTTPException(409, f"order status is {cap['status']} (buyer hasn't approved yet?)")
        p.capture_id = cap["capture_id"]
        settle_topup(db, p)
    db.commit()
    return {"status": p.status, "balance_cents": ledger.balance(db, user_account(db, user).id)}


@router.post("/wallet/faucet")
def faucet(body: AmountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Dev only: credit play money so demos don't need a PayPal round-trip."""
    if settings.env != "dev":
        raise HTTPException(403, "faucet disabled outside dev")
    acc = user_account(db, user)
    ledger.transfer(db, ledger.get_system_account(db).id, acc.id, body.amount_cents, "dev faucet")
    db.commit()
    return {"balance_cents": ledger.balance(db, acc.id)}


# ---------------- approvals / audit ----------------
@router.get("/approvals")
def approvals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Approval).where(Approval.user_id == user.id, Approval.status == "pending").order_by(Approval.id.desc())).all()
    return [{"id": a.id, "action": a.action, "amount_cents": a.amount_cents, "summary": a.summary, "created_at": a.created_at} for a in rows]


class DecideIn(BaseModel):
    approve: bool


@router.post("/approvals/{approval_id}/decide")
def decide(approval_id: int, body: DecideIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        out = policy.decide_approval(db, user, approval_id, body.approve)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return out


@router.get("/audit")
def audit_log(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.actor == f"user:{user.id}").order_by(AuditLog.id.desc()).limit(50)).all()
    return [{"ts": r.ts, "action": r.action, "detail": r.detail} for r in rows]


# ---------------- PayPal webhooks / redirects ----------------
def _handle_webhook(event: dict, headers: dict):
    if not paypal.verify_webhook(headers, event):
        raise HTTPException(400, "invalid webhook signature")
    with SessionLocal() as db:
        eid = event.get("id", "")
        if db.scalar(select(WebhookEvent.id).where(WebhookEvent.event_id == eid)):
            return {"ok": True, "duplicate": True}
        db.add(WebhookEvent(event_id=eid, event_type=event.get("event_type", ""), payload=event))
        res = event.get("resource", {})
        if event.get("event_type") == "PAYMENT.CAPTURE.COMPLETED":
            order_id = ((res.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
            p = db.scalar(select(Payment).where(Payment.paypal_id == order_id)) if order_id else None
            if p:
                p.capture_id = res.get("id")
                if p.kind == "topup":
                    settle_topup(db, p)
                else:
                    p.status = "COMPLETED"
        db.commit()
    return {"ok": True}


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    event = json.loads(await request.body())
    headers = {k.lower(): v for k, v in request.headers.items()}
    return await run_in_threadpool(_handle_webhook, event, headers)


@router.get("/paypal/return")
def paypal_return(token: str = ""):
    return {"ok": True, "order_id": token, "hint": "Buyer approved. Call the matching capture endpoint (or wait for the webhook)."}


@router.get("/paypal/cancel")
def paypal_cancel():
    return {"ok": False, "hint": "Buyer cancelled at PayPal."}


@router.get("/mock/paypal/approve/{order_id}")
def mock_approve(order_id: str):
    return {"mock": True, "order_id": order_id, "message": "Pretend-approved. Capture it via the API."}
