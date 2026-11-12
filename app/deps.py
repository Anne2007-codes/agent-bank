from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Account, User


def current_user(x_api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)) -> User:
    u = db.scalar(select(User).where(User.api_key == x_api_key))
    if not u:
        raise HTTPException(401, "invalid API key")
    return u


def user_account(db: Session, user: User) -> Account:
    return db.scalar(select(Account).where(Account.kind == "user", Account.owner_id == user.id))
