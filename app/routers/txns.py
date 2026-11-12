from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..demo_data import seed
from ..models import Txn, User, now
from ..paypal import paypal

router = APIRouter(prefix="/txns", tags=["transactions"])


@router.post("/seed-demo")
def seed_demo(force: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if settings.env != "dev":
        raise HTTPException(403, "demo seeding disabled outside dev")
    out = seed(db, user.id, force)
    db.commit()
    return out


class SyncIn(BaseModel):
    days: int = Field(90, ge=1, le=1095)


@router.post("/sync")
def sync(body: SyncIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Import from PayPal Transaction Search (needs 'Transaction Search' enabled on the app; data lags up to ~3h).
    Counterparty mapping is best-effort - tweak for your account's payload shape."""
    if paypal.mock:
        raise HTTPException(409, "PayPal is in mock mode; use /txns/seed-demo instead")
    added = 0
    for it in paypal.transaction_search(body.days):
        info = it.get("transaction_info", {})
        tid = info.get("transaction_id")
        if not tid or info.get("transaction_status") != "S":
            continue
        if db.scalar(select(Txn.id).where(Txn.user_id == user.id, Txn.external_id == tid)):
            continue
        amt = Decimal(info["transaction_amount"]["value"])
        payer = it.get("payer_info", {})
        name = ((payer.get("payer_name") or {}).get("alternate_full_name") or payer.get("email_address")
                or info.get("transaction_subject") or "Unknown")
        ts = datetime.fromisoformat(info["transaction_initiation_date"].replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        db.add(Txn(user_id=user.id, external_id=tid, ts=ts, kind="sale" if amt > 0 else "spend", counterparty=name[:120],
                   amount_cents=int(abs(amt) * 100), category=info.get("transaction_event_code", ""),
                   note=(info.get("transaction_note") or info.get("transaction_subject") or "")[:500],
                   capture_id=tid if amt > 0 else None))
        added += 1
    db.commit()
    return {"added": added}


@router.get("")
def list_txns(kind: Optional[str] = None, days: int = 30, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Txn).where(Txn.user_id == user.id, Txn.ts >= now() - timedelta(days=days))
    if kind:
        q = q.where(Txn.kind == kind)
    rows = db.scalars(q.order_by(Txn.ts.desc()).limit(200)).all()
    return [{"id": t.id, "ts": t.ts, "kind": t.kind, "counterparty": t.counterparty, "amount_cents": t.amount_cents,
             "category": t.category, "note": t.note, "refunded_cents": t.refunded_cents} for t in rows]
