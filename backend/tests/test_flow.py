import os
import pathlib

os.environ.update(DATABASE_URL="sqlite:///./test_agentbank.db", DEMO_DELAY_SECONDS="0", GEMINI_API_KEY="",
                  PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET="", ENV="dev")
pathlib.Path("test_agentbank.db").unlink(missing_ok=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_everything():
    with TestClient(app) as c:
        reg = c.post("/auth/register", json={"name": "Anu"}).json()
        H = {"X-API-Key": reg["api_key"]}

        # wallet: mock PayPal top-up -> capture -> ledger credit, and idempotent
        t = c.post("/wallet/topup", json={"amount_cents": 3000}, headers=H).json()
        assert c.post(f"/wallet/topup/{t['order_id']}/capture", headers=H).json()["balance_cents"] == 3000
        assert c.post(f"/wallet/topup/{t['order_id']}/capture", headers=H).json()["balance_cents"] == 3000
        assert c.post("/wallet/faucet", json={"amount_cents": 50000}, headers=H).status_code == 200

        # ---- Agent Bank ----
        mgr = c.post("/agents", json={"name": "Boss", "role": "manager"}, headers=H).json()
        ws = [c.post("/agents", json={"name": f"W{i}", "skills": ["writing"]}, headers=H).json() for i in range(3)]
        assert c.post(f"/agents/{mgr['id']}/fund", json={"amount_cents": 10000}, headers=H).json()["balance_cents"] == 10000
        job = c.post("/jobs", json={"manager_agent_id": mgr["id"], "title": "Write blurb", "description": "Product blurb", "budget_cents": 4000}, headers=H).json()
        assert c.post(f"/jobs/{job['job_id']}/run", headers=H).json()["started"]
        j = c.get(f"/jobs/{job['job_id']}", headers=H).json()
        assert j["status"] == "paid" and len(j["bids"]) == 3, j
        d = c.get("/dashboard", headers=H).json()
        assert d["volume_paid_cents"] > 0 and d["leaderboard"][0]["earned_cents"] > 0
        winner = d["leaderboard"][0]["agent"]
        wid = next(w["id"] for w in ws if w["name"] == winner)
        po = c.post(f"/agents/{wid}/cashout", json={"email": "w@example.com", "amount_cents": 100}, headers=H).json()
        assert po["status"] == "done", po

        # ---- Negotiator ----
        n = c.post("/negotiations", json={"product": "Headphones", "list_price_cents": 4000, "budget_cents": 3200}, headers=H).json()
        g = c.get(f"/negotiations/{n['negotiation_id']}", headers=H).json()
        assert g["status"] == "order_created" and g["approve_url"] and g["agreed_cents"] <= 3200, g
        n2 = c.post("/negotiations", json={"product": "Laptop", "list_price_cents": 90000, "budget_cents": 20000}, headers=H).json()
        assert c.get(f"/negotiations/{n2['negotiation_id']}", headers=H).json()["status"] == "no_deal"

        # ---- Time Machine ----
        assert c.post("/txns/seed-demo", headers=H).json()["seeded"]
        subs = {s["merchant"]: s for s in c.get("/subscriptions", headers=H).json()}
        assert "Netflix" in subs and "Swiggy" not in subs, list(subs)
        sim = c.post("/simulate", json={"merchant": "netflix", "years": 3}, headers=H).json()
        assert sim["final_value_cents"] > sim["total_spent_cents"] > 0
        ap = c.post(f"/simulate/{sim['simulation_id']}/apply", headers=H).json()
        assert ap["plan_status"] == "awaiting_first_payment", ap

        # ---- Voice CFO ----
        r = c.post("/cfo/ask", json={"text": "how are sales?"}, headers=H).json()
        assert "sales" in r["reply"]
        angry = [x for x in c.get("/txns?kind=sale&days=3", headers=H).json() if "broken" in x["note"]][0]
        # refund > threshold goes to approval, then explicit confirm releases it
        from app.db import SessionLocal
        from app import policy
        from app.models import User
        with SessionLocal() as db:
            u = db.get(User, reg["user_id"])
            out = policy.run_action(db, u, "refund", {"txn_id": angry["id"], "amount_cents": 8900, "description": "refund"}, 8900)
            db.commit()
        assert out["status"] == "pending_approval"
        done = c.post("/cfo/ask", json={"text": "yes confirm"}, headers=H).json()
        assert done["reply"].startswith("Done"), done
        assert c.get("/approvals", headers=H).json() == []

        # ---- Scam Shield ----
        scam = "Hi, I'm in a hurry, pay me outside PayPal via WhatsApp, friends and family please, and send the OTP code you get"
        s = c.post("/scan", json={"text": scam}, headers=H).json()
        assert s["verdict"] == "hold" and s["score"] >= 70
        assert c.post("/scan", json={"text": "Thanks! Shipping tomorrow via courier."}, headers=H).json()["verdict"] == "allow"
        pp = c.post("/protected-payments", json={"text": scam, "description": "Camera", "amount_cents": 2500}, headers=H).json()
        assert pp["status"] == "HELD"
        assert c.post(f"/protected-payments/{pp['payment_id']}/release", json={}, headers=H).status_code == 400
        rel = c.post(f"/protected-payments/{pp['payment_id']}/release", json={"i_understand_the_risk": True}, headers=H).json()
        assert rel["status"] == "done" and rel["result"]["approve_url"]
        assert c.get("/audit", headers=H).status_code == 200
