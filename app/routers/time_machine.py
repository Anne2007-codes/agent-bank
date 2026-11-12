"""Money Time Machine: detect subscriptions, replay "what if I'd invested it", apply the fix going forward."""
import statistics
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import payments  # noqa: F401
from .. import policy
from ..db import get_db
from ..deps import current_user
from ..models import SavingsPlan, Simulation, Txn, User, now

router = APIRouter(tags=["time-machine"])


def _months_between(a, b) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def detect_subscriptions(txns: list[Txn]) -> list[dict]:
    by: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        by[t.counterparty.strip().lower()].append(t)
    out = []
    for items in by.values():
        if len(items) < 3:
            continue
        items.sort(key=lambda x: x.ts)
        gaps = [(b.ts - a.ts).days for a, b in zip(items, items[1:])]
        amts = [i.amount_cents for i in items]
        med_amt = statistics.median(amts)
        if not (25 <= statistics.median(gaps) <= 35) or any(abs(a - med_amt) > 0.4 * med_amt for a in amts):
            continue
        out.append({"merchant": items[0].counterparty, "monthly_cents": int(med_amt), "charges": len(items),
                    "first_seen": items[0].ts, "last_seen": items[-1].ts, "active": (now() - items[-1].ts).days <= 45,
                    "total_spent_cents": sum(amts)})
    return sorted(out, key=lambda s: -s["total_spent_cents"])


def simulate_series(charges: list[Txn], annual_return: float) -> dict:
    charges = sorted(charges, key=lambda c: c.ts)
    start, rm = charges[0].ts, (1 + annual_return) ** (1 / 12) - 1
    idx = [_months_between(start, c.ts) for c in charges]
    months = _months_between(start, now())
    series = []
    for m in range(months + 1):
        y, mo = start.year + (start.month - 1 + m) // 12, (start.month - 1 + m) % 12 + 1
        spent = sum(c.amount_cents for c, i in zip(charges, idx) if i <= m)
        value = sum(c.amount_cents * (1 + rm) ** (m - i) for c, i in zip(charges, idx) if i <= m)
        series.append({"month": f"{y}-{mo:02d}", "spent_cents": int(spent), "invested_value_cents": int(round(value))})
    last = series[-1]
    return {
        "series": series, "months": months + 1, "charges": len(charges),
        "monthly_cents": int(statistics.median(c.amount_cents for c in charges)),
        "total_spent_cents": last["spent_cents"], "final_value_cents": last["invested_value_cents"],
        "gain_cents": last["invested_value_cents"] - last["spent_cents"], "annual_return_assumed": annual_return,
        "disclaimer": "Illustrative only: assumes a constant annual return. Not investment advice.",
    }


@router.get("/subscriptions")
def subscriptions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    txns = db.scalars(select(Txn).where(Txn.user_id == user.id, Txn.kind == "spend")).all()
    return detect_subscriptions(txns)


class SimIn(BaseModel):
    merchant: str
    years: float = Field(3.0, gt=0, le=10)
    annual_return: float = Field(0.10, ge=0, le=0.5)


@router.post("/simulate")
def simulate(body: SimIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cutoff = now() - timedelta(days=int(365 * body.years))
    charges = db.scalars(select(Txn).where(Txn.user_id == user.id, Txn.kind == "spend", Txn.ts >= cutoff,
                                           Txn.counterparty.ilike(body.merchant))).all()
    if not charges:
        raise HTTPException(404, f"no '{body.merchant}' charges in the last {body.years} years")
    res = simulate_series(list(charges), body.annual_return)
    sim = Simulation(user_id=user.id, merchant=charges[0].counterparty, params=body.model_dump(), result=res)
    db.add(sim)
    db.commit()
    return {"simulation_id": sim.id, "merchant": sim.merchant, **res}


@router.post("/simulate/{sim_id}/apply")
def apply_fix(sim_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Redirect the saved money going forward: records a savings plan and opens a PayPal order for the first monthly deposit.
    (Recurring auto-debit = PayPal Subscriptions API; kept as a follow-up.)"""
    sim = db.get(Simulation, sim_id)
    if not sim or sim.user_id != user.id:
        raise HTTPException(404, "simulation not found")
    monthly = sim.result["monthly_cents"]
    plan = SavingsPlan(user_id=user.id, simulation_id=sim.id, merchant=sim.merchant, monthly_cents=monthly)
    db.add(plan)
    db.flush()
    res = policy.run_action(db, user, "create_order", {"amount_cents": monthly, "ref": f"plan:{plan.id}",
                            "description": f"First monthly deposit (redirected from {sim.merchant})"}, monthly)
    plan.status = {"done": "awaiting_first_payment", "pending_approval": "pending_approval"}.get(res["status"], "blocked")
    db.commit()
    return {"plan_id": plan.id, "monthly_cents": monthly, "plan_status": plan.status, "policy": res}
