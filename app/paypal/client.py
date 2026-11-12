"""PayPal REST wrapper (Orders v2, Refunds, Payouts, Transaction Search, Webhook verify).
MOCK mode (no credentials) returns realistic fake ids so the whole product demos offline."""
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from ..config import settings


class PayPalError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"PayPal {status}: {body[:300]}")
        self.status, self.body = status, body


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def to_cents(value: str) -> int:
    return int((Decimal(value) * 100).to_integral_value())


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


class PayPalClient:
    def __init__(self):
        self._token, self._exp = None, 0.0
        self.boot = uuid.uuid4().hex[:8]  # request-id namespace so dev DB resets don't replay old idempotency keys

    @property
    def mock(self) -> bool:
        return settings.paypal_mock

    # ---- transport ----
    def _auth(self) -> str:
        if self._token and time.time() < self._exp - 30:
            return self._token
        r = httpx.post(
            f"{settings.paypal_base_url}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(settings.paypal_client_id, settings.paypal_client_secret),
            timeout=20,
        )
        if r.status_code >= 400:
            raise PayPalError(r.status_code, r.text)
        j = r.json()
        self._token, self._exp = j["access_token"], time.time() + int(j.get("expires_in", 300))
        return self._token

    def _req(self, method, path, json=None, params=None, request_id=None):
        headers = {"Authorization": f"Bearer {self._auth()}", "Content-Type": "application/json"}
        if request_id:
            headers["PayPal-Request-Id"] = f"{self.boot}-{request_id}"
        r = httpx.request(method, settings.paypal_base_url + path, headers=headers, json=json, params=params, timeout=30)
        if r.status_code >= 400:
            raise PayPalError(r.status_code, r.text)
        return r.json() if r.content else {}

    # ---- orders ----
    def create_order(self, amount_cents: int, reference_id: str, description: str, request_id: str) -> dict:
        if self.mock:
            oid = _id("MOCK-ORDER")
            return {"id": oid, "status": "PAYER_ACTION_REQUIRED", "approve_url": f"{settings.public_base_url}/mock/paypal/approve/{oid}"}
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": reference_id[:127],
                "description": description[:127],
                "amount": {"currency_code": settings.currency, "value": money(amount_cents)},
            }],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": f"{settings.public_base_url}/paypal/return",
                "cancel_url": f"{settings.public_base_url}/paypal/cancel",
                "user_action": "PAY_NOW",
                "shipping_preference": "NO_SHIPPING",
            }}},
        }
        d = self._req("POST", "/v2/checkout/orders", json=body, request_id=request_id)
        link = next((l["href"] for l in d.get("links", []) if l["rel"] in ("payer-action", "approve")), None)
        return {"id": d["id"], "status": d["status"], "approve_url": link}

    def capture_order(self, order_id: str) -> dict:
        if self.mock:
            return {"id": order_id, "status": "COMPLETED", "capture_id": _id("MOCK-CAP"), "amount_cents": None}
        d = self._req("POST", f"/v2/checkout/orders/{order_id}/capture", json={}, request_id=f"cap-{order_id}")
        cap = d["purchase_units"][0]["payments"]["captures"][0]
        return {"id": d["id"], "status": d["status"], "capture_id": cap["id"], "amount_cents": to_cents(cap["amount"]["value"])}

    # ---- refunds ----
    def refund_capture(self, capture_id: str, amount_cents: int | None, note: str, request_id: str) -> dict:
        if self.mock or capture_id.startswith("MOCK-"):
            return {"id": _id("MOCK-REFUND"), "status": "COMPLETED"}
        body: dict = {"note_to_payer": note[:255]}
        if amount_cents:
            body["amount"] = {"currency_code": settings.currency, "value": money(amount_cents)}
        d = self._req("POST", f"/v2/payments/captures/{capture_id}/refund", json=body, request_id=request_id)
        return {"id": d["id"], "status": d["status"]}

    # ---- payouts ----
    def create_payout(self, email: str, amount_cents: int, note: str, batch_id: str) -> dict:
        if self.mock:
            return {"batch_id": _id("MOCK-PAYOUT"), "status": "SUCCESS"}
        body = {
            "sender_batch_header": {"sender_batch_id": batch_id, "email_subject": "You've been paid", "email_message": note[:200]},
            "items": [{
                "recipient_type": "EMAIL", "receiver": email, "note": note[:200], "sender_item_id": batch_id,
                "amount": {"value": money(amount_cents), "currency": settings.currency},
            }],
        }
        d = self._req("POST", "/v1/payments/payouts", json=body, request_id=batch_id)
        h = d["batch_header"]
        return {"batch_id": h["payout_batch_id"], "status": h["batch_status"]}

    # ---- reporting (31-day max window per call) ----
    def transaction_search(self, days: int = 30) -> list[dict]:
        if self.mock:
            return []
        end = datetime.now(timezone.utc)
        cur, out = end - timedelta(days=days), []
        fmt = "%Y-%m-%dT%H:%M:%S-0000"
        while cur < end:
            nxt = min(cur + timedelta(days=30), end)
            page = 1
            while True:
                d = self._req("GET", "/v1/reporting/transactions", params={
                    "start_date": cur.strftime(fmt), "end_date": nxt.strftime(fmt),
                    "fields": "all", "page_size": 500, "page": page,
                })
                out += d.get("transaction_details", [])
                if page >= d.get("total_pages", 1):
                    break
                page += 1
            cur = nxt
        return out

    # ---- webhooks ----
    def verify_webhook(self, headers: dict, event: dict) -> bool:
        if self.mock:
            return True
        if not settings.paypal_webhook_id:
            return False
        body = {
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": settings.paypal_webhook_id,
            "webhook_event": event,
        }
        try:
            return self._req("POST", "/v1/notifications/verify-webhook-signature", json=body).get("verification_status") == "SUCCESS"
        except PayPalError:
            return False


paypal = PayPalClient()
