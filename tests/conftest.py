import base64
import os

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.passwd import PasswordStore


def hash_line(name, fill=1):
    salt = base64.b64encode(bytes([fill]) * 12).decode()
    digest = base64.b64encode(bytes([fill]) * 64).decode()
    return f"{name}:$7$101${salt}${digest}\n".encode()


class FakeCommand:
    algorithm = "sha512-pbkdf2"

    def __init__(self):
        self.calls = []
        self.hook = None
        self.sequence = 10

    def __call__(self, path, action, username, password):
        self.calls.append((action, username))
        lines = path.read_bytes().splitlines(keepends=True)
        lines = [line for line in lines if not line.startswith(username.encode() + b":")]
        if action != "delete":
            lines.append(hash_line(username, self.sequence))
            self.sequence += 1
        path.write_bytes(b"".join(lines))
        if self.hook:
            self.hook(path, action, username)


@pytest.fixture
def rig(tmp_path):
    password_file = tmp_path / "passwd"
    password_file.write_bytes(hash_line("homeassistant") + hash_line("device", 2))
    password_file.chmod(0o600)
    command = FakeCommand()
    signals = []
    verifications = []

    def reload():
        signals.append(True)

    def verify(name, password):
        verifications.append(name)
        return True

    store = PasswordStore(
        password_file, command, reload, verify, broker_uid=os.geteuid(), broker_gid=os.getegid()
    )
    return {
        "path": password_file,
        "command": command,
        "signals": signals,
        "verifications": verifications,
        "store": store,
        "original": password_file.read_bytes(),
    }


@pytest.fixture
def web(rig, tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "PUBLIC_ORIGIN": "https://manager.test",
            "ADMIN_PASSWORD_HASH": generate_password_hash(
                "synthetic-admin-password", method="pbkdf2:sha256:1000"
            ),
            "SECRET_KEY": "synthetic-test-session-key-not-production",
            "MQTT_NOTES_FILE": str(tmp_path / "notes.json"),
            "MQTT_LOG_FILE": str(tmp_path / "broker.log"),
        },
        {"accounts": rig["store"]},
    )
    return app


@pytest.fixture
def client(web):
    return web.test_client()


def login(client):
    csrf = client.get("/auth/csrf", base_url="https://manager.test").json["csrf_token"]
    response = client.post(
        "/auth/login",
        base_url="https://manager.test",
        json={"username": "admin", "password": "synthetic-admin-password"},
        headers={"Origin": "https://manager.test", "X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    return {"Origin": "https://manager.test", "X-CSRF-Token": response.json["csrf_token"]}
