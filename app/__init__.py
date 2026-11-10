"""Standalone MQTT account manager backend. Product templates are parent-owned."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException

from .auth import canonical_origin, install_auth
from .notes import NotesStore, validate_note
from .passwd import (
    AccountError,
    BrokerReloader,
    CriticalError,
    PasswordCommand,
    PasswordStore,
    file_lock,
    generate_password,
    validate_password,
    validate_username,
)
from .presence import PresenceTracker
from .tasks import OperationManager
from .verifier import FreshConnectVerifier

DEFAULTS = {
    "PUBLIC_ORIGIN": "https://mqtt-users.example.invalid",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD_HASH": "",
    "SECRET_KEY": "",
    "MQTT_PASSWORD_FILE": "/mosquitto/config/passwd",
    "MQTT_NOTES_FILE": "/data/notes.json",
    "MQTT_LOG_FILE": "/mosquitto/log/mosquitto.log",
    "MQTT_BROKER_HOST": "mosquitto",
    "MQTT_BROKER_PORT": 1883,
    "MQTT_BROKER_UID": 1883,
    "MQTT_BROKER_GID": 1883,
    "MQTT_HASH_ALGO": "sha512-pbkdf2",
    "MQTT_PASSWD_BIN": "/usr/bin/mosquitto_passwd",
    "MQTT_PASSWD_STDIN_VERIFIED": True,
    "MQTT_PROTECTED_ACCOUNTS": "homeassistant,zigbee2mqtt",
    "MQTT_RECONNECT_COUNT": 0,
    "MQTT_RECONNECT_WINDOW": 300,
    "COMMAND_TIMEOUT": 5.0,
    "LOCK_TIMEOUT": 3.0,
    "LOCAL_TIMEZONE": "Australia/Melbourne",
}


def unverified_client(username, password):
    raise AccountError(
        "verification_unavailable",
        "The private-input connection check has not passed its compatibility test.",
    )


unverified_client.available = False


def create_app(config=None, services=None):
    app = Flask(__name__)
    app.config.update(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key in os.environ:
            value = os.environ[key]
            if isinstance(default, bool):
                value = value.lower() == "true"
            elif isinstance(default, int):
                value = int(value)
            elif isinstance(default, float):
                value = float(value)
            app.config[key] = value
    app.config.update(config or {})
    canonical_origin(app.config["PUBLIC_ORIGIN"])
    if not app.config.get("TESTING") and urlsplit(app.config["PUBLIC_ORIGIN"]).scheme != "https":
        raise ValueError("PUBLIC_ORIGIN requires HTTPS outside tests")
    if not isinstance(app.config["SECRET_KEY"], str) or len(app.config["SECRET_KEY"]) < 32:
        raise ValueError("Provide a private session key of at least 32 characters")
    password_hash = app.config["ADMIN_PASSWORD_HASH"]
    if (
        not isinstance(password_hash, str)
        or not password_hash.startswith(("scrypt:", "pbkdf2:sha256:"))
        or len(password_hash.split("$")) != 3
    ):
        raise ValueError("Provide a Werkzeug scrypt or PBKDF2 admin password hash")
    if (
        not isinstance(app.config["ADMIN_USERNAME"], str)
        or not 1 <= len(app.config["ADMIN_USERNAME"]) <= 128
    ):
        raise ValueError("Provide a bounded admin username")
    if app.config["MQTT_BROKER_HOST"] in {"localhost", "127.0.0.1", "::1", ""}:
        raise ValueError("MQTT_BROKER_HOST must explicitly name the broker, not localhost")
    if not 0 < app.config["COMMAND_TIMEOUT"] <= 10 or not 0 < app.config["LOCK_TIMEOUT"] <= 10:
        raise ValueError("Timeouts must be bounded to at most ten seconds")
    if (
        not 0 <= app.config["MQTT_RECONNECT_COUNT"] <= 100
        or not 1 <= app.config["MQTT_RECONNECT_WINDOW"] <= 3600
    ):
        raise ValueError("Reconnect observation settings exceed safety bounds")
    app.config.update(
        SESSION_COOKIE_NAME="mqtt_admin",
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=16384,
        MAX_FORM_MEMORY_SIZE=16384,
        MAX_FORM_PARTS=20,
        TRUSTED_HOSTS=[urlsplit(app.config["PUBLIC_ORIGIN"]).hostname],
        ADMIN_CREDENTIAL_VERSION=hashlib.sha256(password_hash.encode()).hexdigest(),
    )
    services = services or {}
    command = services.get("command") or PasswordCommand(
        app.config["MQTT_PASSWD_BIN"],
        app.config["MQTT_HASH_ALGO"],
        app.config["COMMAND_TIMEOUT"],
        app.config["MQTT_PASSWD_STDIN_VERIFIED"],
    )
    store = services.get("accounts") or PasswordStore(
        Path(app.config["MQTT_PASSWORD_FILE"]),
        command,
        services.get("reload") or BrokerReloader(broker_uid=app.config["MQTT_BROKER_UID"]),
        services.get("verifier")
        or FreshConnectVerifier(app.config["MQTT_BROKER_HOST"], app.config["MQTT_BROKER_PORT"]),
        broker_uid=app.config["MQTT_BROKER_UID"],
        broker_gid=app.config["MQTT_BROKER_GID"],
        protected=tuple(
            filter(
                None, (name.strip() for name in app.config["MQTT_PROTECTED_ACCOUNTS"].split(","))
            )
        ),
        lock_timeout=app.config["LOCK_TIMEOUT"],
    )
    notes = services.get("notes") or NotesStore(
        Path(app.config["MQTT_NOTES_FILE"]), app.config["LOCK_TIMEOUT"]
    )
    presence = services.get("presence") or PresenceTracker(
        Path(app.config["MQTT_LOG_FILE"]),
        zone=app.config["LOCAL_TIMEZONE"],
        reconnect_count=app.config["MQTT_RECONNECT_COUNT"],
        reconnect_window=app.config["MQTT_RECONNECT_WINDOW"],
    )
    tasks = services.get("operations") or OperationManager()
    app.extensions.update(accounts=store, notes=notes, presence=presence, operations=tasks)
    if not app.config.get("TESTING"):
        # Keep the context alive for process lifetime; a second replica fails startup.
        import atexit

        process_lock = file_lock(
            Path(app.config["MQTT_NOTES_FILE"]).parent / ".manager-process.lock", timeout=0.1
        )
        process_lock.__enter__()
        app.extensions["process_lock"] = process_lock
        atexit.register(process_lock.__exit__, None, None, None)
    install_auth(app)

    def payload():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise AccountError("invalid_request", "Submit a valid JSON object.")
        return data

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/healthz")
    def health():
        # Liveness only: never expose broker topology or credentials anonymously.
        return jsonify(status="ok")

    @app.get("/api/accounts")
    def accounts():
        usernames = store.accounts()
        descriptions = notes.read()
        observations = presence.rows(usernames)
        rows = [
            {
                "username": name,
                "note": descriptions.get(name, ""),
                "protected": name in store.protected,
                **observations[name],
            }
            for name in usernames
        ]
        total = len(rows)
        query = request.args.get("q", "")
        status = request.args.get("status", "all")
        sort = request.args.get("sort", "username")
        direction = request.args.get("direction", "asc")
        if (
            len(query) > 256
            or status not in {"all", "connected", "disconnected", "reconnecting", "unknown"}
            or sort not in {"username", "note", "status", "last_seen"}
            or direction not in {"asc", "desc"}
        ):
            raise AccountError(
                "invalid_filter", "Choose a valid search, connection status and sort order."
            )
        rows = [
            row
            for row in rows
            if query.casefold() in (row["username"] + " " + row["note"]).casefold()
            and (status == "all" or row["status"] == status)
        ]
        rows.sort(key=lambda row: row["username"].casefold())
        rows.sort(key=lambda row: (row[sort] or "").casefold(), reverse=direction == "desc")
        return jsonify(
            accounts=rows,
            total=total,
            count=len(rows),
            critical=store.blocked(),
            message="Recovery required. Account changes are blocked."
            if store.blocked()
            else "Connection status is based on logs, not a live device check.",
        )

    @app.post("/api/passwords/generate")
    def password():
        return jsonify(password=generate_password())

    @app.put("/api/accounts/<username>/note")
    def note(username):
        validate_username(username)
        if username not in store.accounts():
            raise AccountError("missing", "That account no longer exists.")
        data = payload()
        note = validate_note(data.get("note"))
        notes.set(username, note)
        return jsonify(username=username, note=note, message="Note saved.")

    @app.post("/api/operations")
    def operation():
        data = payload()
        action = data.get("action")
        username = validate_username(data.get("username"))
        if action not in {"add", "change", "delete"}:
            raise AccountError("invalid_action", "Choose add, change or delete.")
        password = validate_password(data.get("password")) if action != "delete" else None
        note = validate_note(data["note"]) if "note" in data else None
        if action == "delete" and username in store.protected:
            raise AccountError("protected", "This account is protected from removal.")
        if store.blocked():
            raise CriticalError()
        if not app.extensions["limiter"].allow(("operation",), 15, 60):
            raise AccountError("rate_limit", "Too many account changes. Wait a minute.")

        def job(progress):
            result = store.mutate(action, username, password, progress)
            if note is not None or action == "delete":
                progress("Saving the separate note")
                try:
                    notes.set(username, "" if action == "delete" else note)
                except Exception:
                    result["warning"] = (
                        "The account change completed, but its separate note was not saved. Refresh the account list and repair the notes file."
                    )
            return result

        task_id = tasks.submit(session["sid"], job)
        return jsonify(
            id=task_id,
            status="running",
            label="◐ Working",
            poll_url=f"/api/operations/{task_id}",
            poll_after_ms=500,
        ), 202

    @app.get("/api/operations/<task_id>")
    def operation_status(task_id):
        if len(task_id) > 128:
            raise AccountError("missing", "That operation is unavailable.")
        return jsonify(tasks.get(task_id, session["sid"]))

    @app.errorhandler(AccountError)
    def account_error(error):
        code = (
            503
            if isinstance(error, CriticalError)
            else 409
            if error.code in {"busy", "exists", "external_change"}
            else 404
            if error.code == "missing"
            else 429
            if error.code == "rate_limit"
            else 400
        )
        return jsonify(error=error.code, message=error.message), code

    @app.errorhandler(Exception)
    def safe_error(error):
        # Do not log exception repr/tracebacks: adapters may contain password arguments.
        code = error.code if isinstance(error, HTTPException) else 500
        return jsonify(error="request_failed", message="The request could not be completed."), code

    return app
