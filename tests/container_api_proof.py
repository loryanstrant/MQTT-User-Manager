"""Run INSIDE disposable manager only, proving real HTTP and broker behavior."""

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from app.passwd import parse_password_file
from app.verifier import FreshConnectVerifier

ORIGIN = os.environ["PUBLIC_ORIGIN"]
HOST = urlsplit(ORIGIN).netloc
cookie = ""
csrf = ""


def request(path, method="GET", body=None, authenticated=True):
    global cookie
    headers = {"Host": HOST, "Origin": ORIGIN, "X-CSRF-Token": csrf}
    if authenticated and cookie:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        "http://127.0.0.1:8080" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as e:
        response = e
    if response.headers.get("Set-Cookie"):
        cookie = response.headers["Set-Cookie"].split(";")[0]
    data = response.read()
    return response.status, json.loads(data) if response.headers.get("Content-Type", "").startswith(
        "application/json"
    ) else data.decode()


v = json.loads(sys.stdin.read())
original = Path("/mosquitto/config/passwords").read_bytes()
assert request("/api/accounts", authenticated=False)[0] == 401
status, result = request("/auth/csrf")
csrf = result["csrf_token"]
status, result = request("/auth/login", "POST", {"username": "admin", "password": v["admin"]})
assert status == 200
csrf = result["csrf_token"]
assert request("/")[0] == 200
assert request("/api/accounts")[1]["total"] >= 1
first, second = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
verify = FreshConnectVerifier("mosquitto")
for action, password in [("add", first), ("change", second), ("delete", None)]:
    status, result = request(
        "/api/operations",
        "POST",
        {
            "action": action,
            "username": "api-proof",
            **({"password": password, "note": "Disposable API test"} if password else {}),
        },
    )
    assert status == 202, result
    url = result["poll_url"]
    for _ in range(60):
        status, result = request(url)
        if result["status"] != "running":
            break
        time.sleep(0.5)
    assert result["status"] == "succeeded", result
    assert not (Path("/mosquitto/config/.mqtt-manager-backups/TRANSACTION_PENDING")).exists()
    now = parse_password_file(Path("/mosquitto/config/passwords").read_bytes())
    before = parse_password_file(original)
    assert all(now.get(name) == line for name, line in before.items())
    if action == "add":
        assert verify("api-proof", first)
    elif action == "change":
        assert verify("api-proof", second) and not verify("api-proof", first)
    else:
        assert not verify("api-proof", second)
assert Path("/mosquitto/config/passwords").read_bytes() == original
assert verify("existing", v["existing"])
print(
    json.dumps(
        {
            "real_http_add_change_delete": True,
            "old_password_refused": True,
            "deleted_known_valid_credential_refused": True,
            "unrelated_lines_unchanged": True,
            "existing_fresh_login": True,
            "private_backups": len(
                list(Path("/mosquitto/config/.mqtt-manager-backups").glob("backup-*"))
            ),
            "password_file_mode": oct(Path("/mosquitto/config/passwords").stat().st_mode & 0o777),
            "ui_template_served": True,
        }
    )
)
