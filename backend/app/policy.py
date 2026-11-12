"""Policy engine: EVERY real-money action goes through run_action(). The LLM proposes, code decides.
allow -> execute | approval -> human must approve | deny -> blocked (limits)."""
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .ledger import InsufficientFunds
from .models import Approval, AuditLog, Payment, User, now

ACTIONS: dict[str, Callable[[Session, User, dict], dict]] = {}


def action(name: str):
    def deco(fn):
        ACTIONS[name] = fn
        return fn
    return deco


def audit(db: Session, actor: str, act: str, detail: dict | None = None):
    db.add(AuditLog(actor=actor, action=act, detail=detail or {}))


def evaluate(db: Session, user_id: int, amount_cents: int) -> tuple[str, str]:
    if amount_cents <= 0:
        return "deny", "amount must be positive"
    if amount_cents > settings.per_tx_limit_cents:
        return "deny", f"over per-transaction limit ({settings.per_tx_limit_cents} cents)"
    start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    spent = db.scalar(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.user_id == user_id,
            Payment.kind.in_(("order", "refund", "payout")),
            Payment.status.notin_(("FAILED", "CANCELLED", "HELD")),
            Payment.created_at >= start,
        )
    )
    if spent + amount_cents > settings.daily_limit_cents:
        return "deny", "daily limit reached"
    if amount_cents > settings.approval_threshold_cents:
        return "approval", "above auto-approve threshold"
    return "allow", ""


def run_action(db: Session, user: User, name: str, payload: dict, amount_cents: int, force: bool = False) -> dict:
    outcome, reason = evaluate(db, user.id, amount_cents)
    if outcome == "deny":
        audit(db, f"user:{user.id}", f"{name}.denied", {"reason": reason, "amount_cents": amount_cents})
        return {"status": "denied", "reason": reason}
    if outcome == "approval" and not force:
        ap = Approval(user_id=user.id, action=name, payload=payload, amount_cents=amount_cents,
                      summary=str(payload.get("description") or name)[:200])
        db.add(ap)
        db.flush()
        audit(db, f"user:{user.id}", f"{name}.needs_approval", {"approval_id": ap.id, "amount_cents": amount_cents})
        return {"status": "pending_approval", "approval_id": ap.id, "reason": reason}
    try:
        result = ACTIONS[name](db, user, payload)
    except InsufficientFunds as e:
        return {"status": "denied", "reason": str(e)}
    audit(db, f"user:{user.id}", f"{name}.done", {"amount_cents": amount_cents})
    return {"status": "done", "result": result}


def decide_approval(db: Session, user: User, approval_id: int, approve: bool) -> dict:
    ap = db.get(Approval, approval_id)
    if not ap or ap.user_id != user.id:
        raise LookupError("approval not found")
    if ap.status != "pending":
        raise ValueError(f"already {ap.status}")
    if not approve:
        ap.status = "rejected"
        audit(db, f"user:{user.id}", f"{ap.action}.rejected", {"approval_id": ap.id})
        return {"status": "rejected"}
    out = run_action(db, user, ap.action, ap.payload, ap.amount_cents, force=True)
    ap.status = "approved" if out["status"] == "done" else "failed"
    return out
