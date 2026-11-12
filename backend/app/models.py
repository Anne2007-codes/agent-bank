from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> datetime:
    """Naive UTC (SQLite-friendly)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=now)


# ---------------- ledger ----------------
class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # user | agent | escrow | system
    owner_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(String(120))


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(default=now)
    debit_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    credit_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount_cents: Mapped[int]
    memo: Mapped[str] = mapped_column(String(200), default="")
    ref: Mapped[str] = mapped_column(String(60), default="", index=True)


# ---------------- payments / policy ----------------
class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # topup | order | refund | payout
    paypal_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    capture_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    amount_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(20), default="CREATED")
    ref: Mapped[str] = mapped_column(String(60), default="", index=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    amount_cents: Mapped[int]
    summary: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|approved|rejected|failed
    created_at: Mapped[datetime] = mapped_column(default=now)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(default=now)
    actor: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


# ---------------- agent bank ----------------
class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(10))  # manager | worker
    skills: Mapped[list] = mapped_column(JSON, default=list)
    persona: Mapped[str] = mapped_column(Text, default="")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    reputation: Mapped[float] = mapped_column(default=3.0)
    jobs_done: Mapped[int] = mapped_column(default=0)
    earned_cents: Mapped[int] = mapped_column(default=0)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    manager_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    budget_cents: Mapped[int]
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|awarded|paid|refunded
    escrow_account_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    winning_bid_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now)


class Bid(Base):
    __tablename__ = "bids"
    __table_args__ = (UniqueConstraint("job_id", "agent_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    price_cents: Mapped[int]
    pitch: Mapped[str] = mapped_column(Text, default="")


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    content: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(default=False)
    score: Mapped[float] = mapped_column(default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")


# ---------------- negotiator ----------------
class Negotiation(Base):
    __tablename__ = "negotiations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product: Mapped[str] = mapped_column(String(200))
    list_price_cents: Mapped[int]
    budget_cents: Mapped[int]
    seller_floor_cents: Mapped[int]
    max_rounds: Mapped[int] = mapped_column(default=6)
    status: Mapped[str] = mapped_column(String(20), default="created")
    agreed_cents: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now)


class NegMessage(Base):
    __tablename__ = "neg_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    negotiation_id: Mapped[int] = mapped_column(ForeignKey("negotiations.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    offer_cents: Mapped[Optional[int]] = mapped_column(nullable=True)
    accept: Mapped[bool] = mapped_column(default=False)


# ---------------- transactions / time machine / CFO ----------------
class Txn(Base):
    __tablename__ = "txns"
    __table_args__ = (UniqueConstraint("user_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    ts: Mapped[datetime] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(8))  # spend | sale
    counterparty: Mapped[str] = mapped_column(String(120))
    amount_cents: Mapped[int]  # always positive
    category: Mapped[str] = mapped_column(String(60), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    capture_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    refunded_cents: Mapped[int] = mapped_column(default=0)


class Simulation(Base):
    __tablename__ = "simulations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    merchant: Mapped[str] = mapped_column(String(120))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)


class SavingsPlan(Base):
    __tablename__ = "savings_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"))
    merchant: Mapped[str] = mapped_column(String(120))
    monthly_cents: Mapped[int]
    status: Mapped[str] = mapped_column(String(24), default="created")
    created_at: Mapped[datetime] = mapped_column(default=now)


# ---------------- scam shield ----------------
class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[int]
    verdict: Mapped[str] = mapped_column(String(8))
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=now)
