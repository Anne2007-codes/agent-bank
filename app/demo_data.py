import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Txn, now

CUSTOMERS = ["Riya Sharma", "Aman Verma", "Sara Khan", "Kabir Singh", "Meera Iyer", "Tanvi Rao", "Dev Patel", "Isha Nair"]
ITEMS = [("Candles", 1500, 4500), ("Skincare", 2500, 8000), ("Home decor", 3000, 12000)]


def seed(db: Session, user_id: int, force: bool = False) -> dict:
    if not force and db.scalar(select(Txn.id).where(Txn.user_id == user_id, Txn.external_id.like("demo-%"))):
        return {"seeded": False, "reason": "demo data already present"}
    rnd, t, n = random.Random(7), now(), 0
    # --- sales: 60 days; last 5 days dip, Skincare vanishes, a couple of complaints ---
    for d in range(60):
        dip = d < 5
        for _ in range(rnd.randint(1, 2) if dip else rnd.randint(3, 7)):
            cat, lo, hi = rnd.choice(ITEMS[:1] + ITEMS[2:] if dip else ITEMS)
            ts = (t - timedelta(days=d)).replace(hour=rnd.randint(9, 21), minute=rnd.randint(0, 59))
            note = "Customer complaint: delivery was late" if dip and rnd.random() < 0.3 else ""
            db.add(Txn(user_id=user_id, external_id=f"demo-s-{n}", ts=ts, kind="sale", counterparty=rnd.choice(CUSTOMERS),
                       amount_cents=rnd.randint(lo, hi), category=cat, note=note, capture_id=f"MOCK-CAP-DEMO-{n}"))
            n += 1
    ts = (t - timedelta(days=1)).replace(hour=15, minute=10)
    db.add(Txn(user_id=user_id, external_id="demo-s-angry", ts=ts, kind="sale", counterparty="Neha Kapoor", amount_cents=8900,
               category="Home decor", note="Customer message: item arrived broken, very unhappy, wants a refund",
               capture_id="MOCK-CAP-DEMO-ANGRY"))
    # --- spend: subscriptions + noise ---
    for k in range(36):
        base = t - timedelta(days=30 * k + 3)
        db.add(Txn(user_id=user_id, external_id=f"demo-p-nf-{k}", ts=base, kind="spend", counterparty="Netflix",
                   amount_cents=1549 if k < 18 else 1399, category="Streaming"))
        if k < 24:
            db.add(Txn(user_id=user_id, external_id=f"demo-p-sp-{k}", ts=base + timedelta(days=2), kind="spend",
                       counterparty="Spotify", amount_cents=1199, category="Music"))
        if k < 18:
            db.add(Txn(user_id=user_id, external_id=f"demo-p-gy-{k}", ts=base + timedelta(days=1), kind="spend",
                       counterparty="CultFit Gym", amount_cents=2900, category="Fitness"))
    for i in range(40):
        db.add(Txn(user_id=user_id, external_id=f"demo-p-sw-{i}", ts=t - timedelta(days=rnd.randint(1, 900)), kind="spend",
                   counterparty="Swiggy", amount_cents=rnd.randint(800, 2500), category="Food"))
    db.flush()
    return {"seeded": True}
