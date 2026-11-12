from sqlalchemy.orm import Session

from .config import settings
from .models import Negotiation, Payment, User
from .paypal import paypal
from .policy import action


def create_checkout(db: Session, user: User, amount_cents: int, description: str, kind: str = "order",
                    ref: str = "", meta: dict | None = None, payment: Payment | None = None) -> Payment:
    p = payment or Payment(user_id=user.id, kind=kind, amount_cents=amount_cents, currency=settings.currency,
                           status="CREATING", ref=ref, meta=meta or {})
    db.add(p)
    db.flush()
    o = paypal.create_order(amount_cents, reference_id=f"{p.kind}-{p.id}", description=description, request_id=f"pay-{p.id}")
    p.paypal_id, p.status = o["id"], "CREATED"
    p.meta = {**(p.meta or {}), "approve_url": o["approve_url"], "description": description}
    return p


@action("create_order")
def _create_order(db: Session, user: User, payload: dict) -> dict:
    p = create_checkout(db, user, payload["amount_cents"], payload["description"], ref=payload.get("ref", ""), meta=payload.get("meta"))
    if p.ref.startswith("neg:"):
        neg = db.get(Negotiation, int(p.ref[4:]))
        if neg:
            neg.status = "order_created"
    return {"payment_id": p.id, "order_id": p.paypal_id, "approve_url": p.meta["approve_url"]}
