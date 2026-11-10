import threading
import time
from unittest.mock import patch

import pytest
from conftest import login

from app import create_app
from app.auth import RateLimiter
from app.passwd import AccountError
from app.tasks import OperationManager

BASE = "https://manager.test"


def test_auth_csrf_rotation_logout(client):
    assert client.get("/api/accounts", base_url=BASE).status_code == 401
    before = client.get("/auth/csrf", base_url=BASE).json["csrf_token"]
    assert (
        client.post(
            "/auth/login",
            base_url=BASE,
            json={"username": "admin", "password": "synthetic-admin-password"},
        ).status_code
        == 403
    )
    headers = login(client)
    assert headers["X-CSRF-Token"] != before
    assert client.get("/auth/session", base_url=BASE).json["authenticated"]
    assert client.post("/auth/logout", base_url=BASE, headers=headers).status_code == 200
    assert client.get("/api/accounts", base_url=BASE).status_code == 401


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.test",
        "null",
        "",
        "https://manager.test.evil",
        "https://manager.test:444",
        "https://manager.test/path",
    ],
)
def test_origin_refusal(client, origin):
    headers = login(client)
    headers["Origin"] = origin
    assert client.post("/api/passwords/generate", base_url=BASE, headers=headers).status_code == 403


def test_csrf_all_write_paths(client):
    login(client)
    for method, path, data in [
        ("post", "/api/operations", {}),
        ("put", "/api/accounts/device/note", {"note": "x"}),
        ("post", "/api/passwords/generate", {}),
        ("post", "/auth/logout", {}),
    ]:
        assert (
            getattr(client, method)(
                path, base_url=BASE, json=data, headers={"Origin": BASE}
            ).status_code
            == 403
        )


def test_security_headers_and_cookie(client):
    response = client.get("/auth/csrf", base_url=BASE)
    cookie = response.headers["Set-Cookie"]
    assert all(value in cookie for value in ("Secure", "HttpOnly", "SameSite=Strict"))
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" in response.headers


def test_generated_password_one_response_not_session(client):
    headers = login(client)
    one = client.post("/api/passwords/generate", base_url=BASE, headers=headers).json["password"]
    two = client.post("/api/passwords/generate", base_url=BASE, headers=headers).json["password"]
    assert len(one) >= 24 and one != two
    with client.session_transaction(base_url=BASE) as session:
        assert one not in repr(session) and "password" not in session


def test_rate_limit_login(client):
    token = client.get("/auth/csrf", base_url=BASE).json["csrf_token"]
    headers = {"Origin": BASE, "X-CSRF-Token": token}
    for _ in range(5):
        assert (
            client.post(
                "/auth/login",
                base_url=BASE,
                json={"username": "wrong", "password": "wrong"},
                headers=headers,
            ).status_code
            == 401
        )
    assert client.post("/auth/login", base_url=BASE, json={}, headers=headers).status_code == 429


def test_list_search_sort_notes(client, web):
    headers = login(client)
    assert (
        client.put(
            "/api/accounts/device/note",
            base_url=BASE,
            json={"note": "Synthetic room"},
            headers=headers,
        ).status_code
        == 200
    )
    response = client.get("/api/accounts?q=ROOM&sort=note&direction=desc", base_url=BASE)
    assert (
        response.status_code == 200 and response.json["count"] == 1 and response.json["total"] == 2
    )
    row = response.json["accounts"][0]
    assert row["username"] == "device" and row["status_label"] == "○ Unknown"
    assert client.get("/api/accounts?sort=password", base_url=BASE).status_code == 400
    assert client.get("/api/accounts?q=nomatch", base_url=BASE).json["count"] == 0


def poll(client, url):
    for _ in range(100):
        response = client.get(url, base_url=BASE)
        if response.json.get("status") != "running":
            return response
        time.sleep(0.01)
    pytest.fail("Task did not finish")


def test_operation_end_to_end_synthetic(client, rig):
    headers = login(client)
    password = "synthetic-device-password"
    response = client.post(
        "/api/operations",
        base_url=BASE,
        json={"action": "add", "username": "new", "password": password, "note": "Synthetic note"},
        headers=headers,
    )
    assert response.status_code == 202
    result = poll(client, response.json["poll_url"])
    assert result.json["status"] == "succeeded"
    assert password not in result.text
    assert "new" in rig["store"].accounts()
    row = client.get("/api/accounts?q=new", base_url=BASE).json["accounts"][0]
    assert row["note"] == "Synthetic note"


def test_delete_protected_and_no_bad_password_proof(client, rig):
    headers = login(client)
    response = client.post(
        "/api/operations",
        base_url=BASE,
        json={"action": "delete", "username": "homeassistant"},
        headers=headers,
    )
    assert response.status_code == 400 and response.json["error"] == "protected"
    response = client.post(
        "/api/operations",
        base_url=BASE,
        json={"action": "delete", "username": "device"},
        headers=headers,
    )
    result = poll(client, response.json["poll_url"])
    assert result.json["status"] == "succeeded" and "remain active" in result.json["message"]
    assert rig["verifications"] == []


def test_failed_operation_private(client, rig, caplog):
    headers = login(client)

    def fail(*args):
        raise RuntimeError("secret-raw-password-arguments")

    rig["store"].command = fail
    response = client.post(
        "/api/operations",
        base_url=BASE,
        json={"action": "change", "username": "device", "password": "synthetic-device-password"},
        headers=headers,
    )
    result = poll(client, response.json["poll_url"])
    assert result.json["status"] == "failed"
    assert "secret" not in result.text and "secret" not in caplog.text


def test_note_failure_reported_without_undoing_account(client, web, rig):
    headers = login(client)
    with patch.object(web.extensions["notes"], "set", side_effect=RuntimeError("secret")):
        response = client.post(
            "/api/operations",
            base_url=BASE,
            json={
                "action": "add",
                "username": "new",
                "password": "synthetic-device-password",
                "note": "hello",
            },
            headers=headers,
        )
        result = poll(client, response.json["poll_url"])
    assert result.json["status"] == "succeeded" and "warning" in result.json
    assert "new" in rig["store"].accounts()


def test_request_limit_and_host(client):
    headers = login(client)
    assert (
        client.post(
            "/api/operations",
            base_url=BASE,
            data=b"x" * 17000,
            content_type="application/json",
            headers=headers,
        ).status_code
        == 413
    )
    assert client.get("/healthz", base_url="https://evil.test").status_code == 400


def test_config_fail_closed():
    with pytest.raises(ValueError):
        create_app({"TESTING": True, "SECRET_KEY": "short"})


def test_tasks_no_queue_and_owner_scoped():
    gate = threading.Event()
    manager = OperationManager()
    task = manager.submit("one", lambda progress: (gate.wait(1), {"status": "succeeded"})[1])
    with pytest.raises(AccountError):
        manager.submit("two", lambda _: {})
    with pytest.raises(AccountError):
        manager.get(task, "two")
    assert manager.get(task, "one")["status"] == "running"
    gate.set()
    for _ in range(100):
        if manager.active is None:
            break
        time.sleep(0.01)
    assert manager.get(task, "one")["status"] == "succeeded"


def test_task_retention_and_expiry():
    now = [0]
    manager = OperationManager(retention=2, ttl=10, clock=lambda: now[0])
    for _ in range(5):
        manager.submit("one", lambda _: {"status": "succeeded"})
        while manager.active:
            time.sleep(0.001)
    assert len(manager.results) <= 2
    now[0] = 11
    with pytest.raises(AccountError):
        manager.get("missing", "one")
    assert not manager.results


def test_limiter_is_bounded():
    limiter = RateLimiter(maximum_keys=2)
    assert limiter.allow("one", 1, 60) and limiter.allow("two", 1, 60)
    assert not limiter.allow("three", 1, 60) and not limiter.allow("one", 1, 60)
    assert len(limiter.keys) == 2
