"""Double-entry internal ledger. Agent wallets = ledger accounts; PayPal only at the edges
(top-up in, payout out). Balances are derived from entries, never stored."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Account, LedgerEntry


class InsufficientFunds(Exception):
    pass


def create_account(db: Session, kind: str, owner_id, name: str) -> Account:
    acc = Account(kind=kind, owner_id=owner_id, name=name)
    db.add(acc)
    db.flush()
    return acc


def get_system_account(db: Session) -> Account:
    acc = db.scalar(select(Account).where(Account.kind == "system", Account.name == "paypal_float"))
    return acc or create_account(db, "system", None, "paypal_float")


def balance(db: Session, account_id: int) -> int:
    credits = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(LedgerEntry.credit_account_id == account_id)
    )
    debits = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(LedgerEntry.debit_account_id == account_id)
    )
    return int(credits - debits)


def transfer(db: Session, src_id: int, dst_id: int, amount_cents: int, memo: str = "", ref: str = "") -> LedgerEntry:
    if amount_cents <= 0:
        raise ValueError("amount must be positive")
    # row lock on Postgres (no-op on SQLite) so concurrent transfers can't overdraw
    src = db.scalar(select(Account).where(Account.id == src_id).with_for_update())
    if src is None:
        raise ValueError("unknown source account")
    if src.kind != "system" and balance(db, src_id) < amount_cents:
        raise InsufficientFunds(f"{src.name} has insufficient funds")
    e = LedgerEntry(debit_account_id=src_id, credit_account_id=dst_id, amount_cents=amount_cents, memo=memo[:200], ref=ref)
    db.add(e)
    db.flush()
    return e
