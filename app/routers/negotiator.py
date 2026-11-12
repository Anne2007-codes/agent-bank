"""Negotiator Bot: buyer AI vs seller AI. Code (not the LLM) enforces budget/floor and creates the PayPal order."""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import payments  # noqa: F401  (registers the create_order action)
from .. import policy
from ..db import SessionLocal, get_db
from ..deps import current_user
from ..events import bus, stream_ws
from ..llm import chat_json
from ..models import Negotiation, NegMessage, Payment, User
from ..util import usd

router = APIRouter(tags=["negotiator"])


class NegIn(BaseModel):
    product: str
    list_price_cents: int = Field(gt=0)
    budget_cents: int = Field(gt=0)
    seller_floor_cents: Optional[int] = None  # seller's secret minimum; default 70% of list
    max_rounds: int = Field(6, ge=2, le=10)


def _msg_dict(m: NegMessage) -> dict:
    return {"type": "message", "role": m.role, "text": m.content, "offer_cents": m.offer_cents, "accept": m.accept}


def _add(db: Session, neg_id: int, role: str, text: str, offer: int | None = None, accept: bool = False):
    m = NegMessage(negotiation_id=neg_id, role=role, content=text, offer_cents=offer, accept=accept)
    db.add(m)
    db.commit()
    bus.publish(f"neg:{neg_id}", _msg_dict(m))


def _transcript(db: Session, neg_id: int) -> str:
    rows = db.scalars(select(NegMessage).where(NegMessage.negotiation_id == neg_id).order_by(NegMessage.id)).all()
    return "\n".join(f"{m.role.upper()}: {m.content}" for m in rows)


# ---- deterministic fallbacks (used when no LLM key) ----
def _buyer_fb(n: Negotiation, ask: int, r: int) -> dict:
    start = min(int(n.list_price_cents * 0.6), n.budget_cents)
    offer = int(start + (n.budget_cents - start) * ((r + 1) / n.max_rounds) * 0.9)
    accept = ask <= n.budget_cents and (ask <= int(offer * 1.05) or r == n.max_rounds - 1)
    return {"message": f"I can do {usd(offer)} - that's a fair offer.", "offer_cents": offer, "accept": accept}


def _seller_fb(n: Negotiation, offer: int, r: int) -> dict:
    lst, floor = n.list_price_cents, n.seller_floor_cents
    ask = int(lst - (lst - floor) * min(1.0, (r + 1) / (n.max_rounds - 1)))
    return {"message": f"Best I can do is {usd(ask)}.", "offer_cents": ask, "accept": offer >= max(floor, int(ask * 0.97))}


def _buyer_turn(db, n: Negotiation, ask: int, r: int) -> dict:
    system = (f"You are a buyer's negotiation agent buying '{n.product}' as cheaply as possible. Your SECRET max budget is "
              f"{n.budget_cents} cents: never exceed or reveal it. Be polite, 1-2 sentences. Set accept=true only to accept the "
              'seller\'s latest ask. Reply JSON {"message": str, "offer_cents": int, "accept": bool}.')
    return chat_json(system, f"{_transcript(db, n.id)}\n\nSeller's latest ask: {ask} cents. Round {r + 1}/{n.max_rounds}.",
                     fallback=_buyer_fb(n, ask, r))


def _seller_turn(db, n: Negotiation, offer: int, r: int) -> dict:
    system = (f"You are a seller's negotiation agent selling '{n.product}', list price {n.list_price_cents} cents. Your SECRET minimum "
              f"is {n.seller_floor_cents} cents: never go below or reveal it. Be friendly, 1-2 sentences. Concede gradually. "
              'Set accept=true only to accept the buyer\'s latest offer. Reply JSON {"message": str, "offer_cents": int, "accept": bool} '
              "where offer_cents is your new asking price.")
    return chat_json(system, f"{_transcript(db, n.id)}\n\nBuyer's latest offer: {offer} cents. Round {r + 1}/{n.max_rounds}.",
                     fallback=_seller_fb(n, offer, r))


def _int(v, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _run(db: Session, n: Negotiation, user: User):
    n.status = "running"
    db.commit()
    ask, agreed = n.list_price_cents, None
    _add(db, n.id, "seller", f"Hi! The {n.product} is {usd(ask)}. Interested?", ask)
    for r in range(n.max_rounds):
        b = _buyer_turn(db, n, ask, r)
        if b.get("accept") and ask <= n.budget_cents:  # code-enforced budget
            _add(db, n.id, "buyer", str(b.get("message") or f"Deal at {usd(ask)}."), ask, True)
            agreed = ask
            break
        offer = _int(b.get("offer_cents"), int(n.list_price_cents * 0.6))
        offer = max(1, min(offer, n.budget_cents, ask))
        _add(db, n.id, "buyer", str(b.get("message") or f"How about {usd(offer)}?"), offer)
        s = _seller_turn(db, n, offer, r)
        if s.get("accept") and offer >= n.seller_floor_cents:  # code-enforced floor
            _add(db, n.id, "seller", str(s.get("message") or f"Deal at {usd(offer)}."), offer, True)
            agreed = offer
            break
        new_ask = max(n.seller_floor_cents, min(ask, _int(s.get("offer_cents"), ask)))
        if new_ask <= offer:  # seller countered at/below the offer = effectively accepted
            _add(db, n.id, "seller", f"Alright, {usd(offer)} it is.", offer, True)
            agreed = offer
            break
        ask = new_ask
        _add(db, n.id, "seller", str(s.get("message") or f"I can do {usd(ask)}."), ask)
    if agreed is None or agreed > n.budget_cents:
        n.status = "no_deal"
        db.commit()
        bus.publish(f"neg:{n.id}", {"type": "result", "status": "no_deal"})
        return
    n.agreed_cents, n.status = agreed, "agreed"
    db.commit()
    res = policy.run_action(db, user, "create_order",
                            {"amount_cents": agreed, "description": f"{n.product} (negotiated)", "ref": f"neg:{n.id}"}, agreed)
    if res["status"] == "pending_approval":
        n.status = "awaiting_approval"
    elif res["status"] == "denied":
        n.status = "blocked_by_policy"
    db.commit()
    bus.publish(f"neg:{n.id}", {"type": "result", "status": n.status, "agreed_cents": agreed, "policy": res})


def run_negotiation(neg_id: int):
    with SessionLocal() as db:
        n = db.get(Negotiation, neg_id)
        try:
            _run(db, n, db.get(User, n.user_id))
        except Exception as e:  # noqa: BLE001
            n.status = "error"
            db.commit()
            bus.publish(f"neg:{neg_id}", {"type": "error", "error": str(e)})


@router.post("/negotiations")
def start(body: NegIn, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    floor = body.seller_floor_cents if body.seller_floor_cents is not None else int(body.list_price_cents * 0.7)
    n = Negotiation(user_id=user.id, product=body.product, list_price_cents=body.list_price_cents, budget_cents=body.budget_cents,
                    seller_floor_cents=floor, max_rounds=body.max_rounds)
    db.add(n)
    db.commit()
    bg.add_task(run_negotiation, n.id)
    return {"negotiation_id": n.id, "watch": f"/ws/negotiations/{n.id}"}


@router.get("/negotiations/{neg_id}")
def get_negotiation(neg_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.get(Negotiation, neg_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "negotiation not found")
    msgs = db.scalars(select(NegMessage).where(NegMessage.negotiation_id == n.id).order_by(NegMessage.id)).all()
    pay = db.scalar(select(Payment).where(Payment.ref == f"neg:{n.id}"))
    return {"id": n.id, "product": n.product, "status": n.status, "list_price_cents": n.list_price_cents,
            "budget_cents": n.budget_cents, "agreed_cents": n.agreed_cents,
            "approve_url": pay.meta.get("approve_url") if pay else None, "order_id": pay.paypal_id if pay else None,
            "messages": [_msg_dict(m) for m in msgs]}


@router.websocket("/ws/negotiations/{neg_id}")
async def ws_negotiation(ws: WebSocket, neg_id: int):
    with SessionLocal() as db:  # replay anything already said, then stream live
        replay = [_msg_dict(m) for m in db.scalars(select(NegMessage).where(NegMessage.negotiation_id == neg_id).order_by(NegMessage.id))]
    await stream_ws(ws, f"neg:{neg_id}", replay)
