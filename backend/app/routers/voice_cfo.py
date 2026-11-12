"""Voice CFO: text endpoint the frontend feeds from browser speech-to-text and reads back with speechSynthesis.
The agent can read sales, explain trends and request refunds - but refunds always pass through the policy engine."""
import re
import uuid
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import policy
from ..agent_runtime import run_tool_loop
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..models import Approval, Payment, Txn, User, now
from ..paypal import paypal
from ..util import usd

router = APIRouter(prefix="/cfo", tags=["voice-cfo"])
_HISTORY: dict[tuple, list] = defaultdict(list)
_YES = re.compile(r"\s*((yes|yeah|yep|confirm(ed)?|go ahead|do it|approve(d)?|sure|ok(ay)?|please)\W*)+", re.I)
_NO = re.compile(r"\s*((no|nope|cancel|stop|don'?t|reject)\W*(it\W*)?)+", re.I)

SYSTEM = ("You are the CFO assistant for a small shop owner, speaking aloud. Be brief and concrete. Use tools for every fact. "
          "For refunds: find the sale with list_sales, then call refund_sale. If the result is pending_approval, tell the owner "
          "the amount and customer and ask them to say 'confirm'. Never claim a refund happened unless the tool says status done.")

TOOL_DOCS = """get_sales_summary(days:int=7) -> totals for the last N days vs the N days before
list_sales(days:int=3, search:str|null=null) -> recent sales (id, customer, amount, category, note); search matches customer/note/category
explain_trend(days:int=7) -> per-category and per-day deltas, refunds, new/lost customers vs previous period (explain WHY sales moved)
refund_sale(txn_id:int, amount_cents:int|null=null, reason:str="") -> refund (full if amount omitted)"""


def _window(db, uid, days, offset=0):
    end = now() - timedelta(days=offset)
    return db.scalars(select(Txn).where(Txn.user_id == uid, Txn.kind == "sale", Txn.ts >= end - timedelta(days=days), Txn.ts < end)).all()


def _tot(rows):
    return sum(r.amount_cents - r.refunded_cents for r in rows)


@policy.action("refund")
def _refund(db: Session, user: User, p: dict) -> dict:
    t = db.get(Txn, p["txn_id"])
    if not t or t.user_id != user.id or t.kind != "sale":
        raise ValueError("sale not found")
    amount = p["amount_cents"]
    if amount > t.amount_cents - t.refunded_cents:
        raise ValueError("refund exceeds remaining amount")
    r = paypal.refund_capture(t.capture_id or "MOCK-NA", amount, p.get("reason") or "Refund", f"refund-{t.id}-{t.refunded_cents}-{amount}")
    t.refunded_cents += amount
    db.add(Payment(user_id=user.id, kind="refund", paypal_id=r["id"], amount_cents=amount, currency=settings.currency,
                   status=r["status"], ref=f"txn:{t.id}", meta={"customer": t.counterparty}))
    db.flush()
    return {"refund_id": r["id"], "customer": t.counterparty, "amount": usd(amount)}


def _tools(db: Session, user: User, pending: list):
    def get_sales_summary(days: int = 7):
        cur, prev = _window(db, user.id, days), _window(db, user.id, days, days)
        return {"days": days, "sales": len(cur), "revenue": usd(_tot(cur)), "prev_sales": len(prev), "prev_revenue": usd(_tot(prev)),
                "refunded": usd(sum(r.refunded_cents for r in cur))}

    def list_sales(days: int = 3, search: str | None = None):
        rows = sorted(_window(db, user.id, days), key=lambda r: r.ts, reverse=True)
        if search:
            s = search.lower()
            rows = [r for r in rows if s in r.counterparty.lower() or s in r.note.lower() or s in r.category.lower()]
        return [{"id": r.id, "when": r.ts.strftime("%Y-%m-%d %H:%M"), "customer": r.counterparty, "amount_cents": r.amount_cents,
                 "category": r.category, "note": r.note, "refunded_cents": r.refunded_cents} for r in rows[:15]]

    def explain_trend(days: int = 7):
        cur, prev = _window(db, user.id, days), _window(db, user.id, days, days)

        def by(rows, key):
            d = defaultdict(int)
            for r in rows:
                d[key(r)] += r.amount_cents
            return d
        c, p = by(cur, lambda r: r.category), by(prev, lambda r: r.category)
        cats = sorted(({"category": k, "now": usd(c.get(k, 0)), "before": usd(p.get(k, 0)), "delta_cents": c.get(k, 0) - p.get(k, 0)}
                       for k in set(c) | set(p)), key=lambda x: x["delta_cents"])
        cc, pc = {r.counterparty for r in cur}, {r.counterparty for r in prev}
        daily = defaultdict(int)
        for r in cur:
            daily[r.ts.strftime("%a %d")] += 1
        return {"revenue_now": usd(_tot(cur)), "revenue_before": usd(_tot(prev)), "orders_now": len(cur), "orders_before": len(prev),
                "categories_worst_first": cats, "orders_per_day_now": dict(daily), "lost_customers": sorted(pc - cc)[:5],
                "new_customers": sorted(cc - pc)[:5], "complaint_notes": [r.note for r in cur if "complaint" in r.note.lower()][:5]}

    def refund_sale(txn_id: int, amount_cents: int | None = None, reason: str = ""):
        t = db.get(Txn, txn_id)
        if not t or t.user_id != user.id:
            return {"error": "sale not found"}
        amt = amount_cents or (t.amount_cents - t.refunded_cents)
        out = policy.run_action(db, user, "refund", {"txn_id": t.id, "amount_cents": amt, "reason": reason,
                                                     "description": f"Refund {usd(amt)} to {t.counterparty}"}, amt)
        if out["status"] == "pending_approval":
            pending.append(out["approval_id"])
            out["customer"], out["amount"] = t.counterparty, usd(amt)
        return out

    return {"get_sales_summary": get_sales_summary, "list_sales": list_sales, "explain_trend": explain_trend, "refund_sale": refund_sale}


class AskIn(BaseModel):
    text: str
    session_id: str | None = None


@router.post("/ask")
def ask(body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sid = body.session_id or uuid.uuid4().hex[:8]
    last_ap = db.scalar(select(Approval).where(Approval.user_id == user.id, Approval.status == "pending").order_by(Approval.id.desc()))
    # Deterministic confirm/reject path: only the owner's own short reply can release a pending approval - never the LLM.
    if last_ap and (_YES.fullmatch(body.text) or _NO.fullmatch(body.text)):
        ok = bool(_YES.fullmatch(body.text))
        out = policy.decide_approval(db, user, last_ap.id, ok)
        db.commit()
        reply = ("Done. " + (f"Refunded {out['result']['amount']} to {out['result']['customer']}." if out.get("status") == "done" else "")
                 if ok else "Okay, cancelled.")
        if ok and out.get("status") != "done":
            reply = f"That didn't go through: {out.get('reason', 'blocked')}."
        return {"session_id": sid, "reply": reply, "steps": [], "pending_approvals": []}

    hist = _HISTORY[(user.id, sid)][-6:]
    msg = "\n".join(f"{r}: {t}" for r, t in hist) + f"\nowner: {body.text}"
    pending: list[int] = []
    tools = _tools(db, user, pending)
    s = tools["get_sales_summary"](7)
    fb = (f"Last 7 days: {s['sales']} sales, {s['revenue']} versus {s['prev_revenue']} the week before. "
          "Set GEMINI_API_KEY to enable the full voice agent.")
    reply, steps = run_tool_loop(SYSTEM, msg, tools, TOOL_DOCS, fb,
                                 on_call=lambda n, a, r: policy.audit(db, f"user:{user.id}", f"cfo.tool.{n}", {"args": a}))
    db.commit()
    _HISTORY[(user.id, sid)] += [("owner", body.text), ("cfo", reply)]
    return {"session_id": sid, "reply": reply, "steps": [{"tool": x.get("tool"), "args": x.get("args")} for x in steps if "tool" in x],
            "pending_approvals": pending}
