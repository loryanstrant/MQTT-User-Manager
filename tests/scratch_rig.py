"""Explicit disposable broker/UI rig. No production host or account material."""

import json
import os
import secrets
import subprocess
from pathlib import Path

PREFIX = "rufus-scratch-mqtt-preview"
IMAGE = os.environ.get("MQTT_SCRATCH_IMAGE", "mqtt-user-manager:local")
ORIGIN = os.environ.get("MQTT_SCRATCH_ORIGIN", "https://mqtt-preview.example.invalid:8708")


def run(*args, data=None, check=True):
    result = subprocess.run(
        ["docker", *args], input=data, capture_output=True, text=True, timeout=90
    )
    if check and result.returncode:
        raise RuntimeError(f"Scratch {args[0]} failed; output withheld")
    return result.stdout


def setup():
    from app.auth import canonical_origin

    canonical_origin(ORIGIN)
    preview_container = os.environ.get("MQTT_PREVIEW_CONTAINER")
    if not preview_container:
        raise RuntimeError("Configure the preview container before creating scratch resources")
    root = Path(".scratch")
    root.mkdir(mode=0o700, exist_ok=True)
    values = {"existing": secrets.token_urlsafe(24), "session": secrets.token_urlsafe(48)}
    # Scratch admin password supplied privately via stdin; never echo.
    import sys

    values["admin"] = sys.stdin.read().strip()
    if not values["admin"]:
        raise RuntimeError("Supply scratch admin credential privately")
    path = root / "credentials.json"
    path.write_text(json.dumps(values))
    path.chmod(0o600)
    run("network", "create", PREFIX)
    run("volume", "create", PREFIX + "-data")
    init = """import os, json, subprocess
from werkzeug.security import generate_password_hash
v=json.loads(input())
for p in ['/scratch/config','/scratch/log','/scratch/data']: os.makedirs(p,exist_ok=True); os.chown(p,1883,1883)
open('/scratch/config/mosquitto.conf','w').write('listener 1883\\nallow_anonymous false\\npassword_file /mosquitto/config/passwords\\nlog_dest file /mosquitto/log/mosquitto.log\\nlog_type all\\n')
p='/scratch/config/passwords'; open(p,'w').close(); os.chown(p,1883,1883); os.chmod(p,0o640)
r=subprocess.run(['mosquitto_passwd','-H','sha512-pbkdf2',p,'existing'],input=(v['existing']+'\\n'+v['existing']+'\\n').encode(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
assert r.returncode==0
os.chown(p,1883,1883); os.chmod(p,0o640)
"""
    run(
        "run",
        "--rm",
        "-i",
        "--name",
        PREFIX + "-init",
        "--user",
        "0:0",
        "-v",
        PREFIX + "-data:/scratch",
        "--entrypoint",
        "python",
        IMAGE,
        "-c",
        init,
        data=json.dumps(values),
    )
    run(
        "run",
        "-d",
        "--name",
        PREFIX + "-broker",
        "--network",
        PREFIX,
        "--network-alias",
        "mosquitto",
        "-v",
        PREFIX + "-data:/scratch",
        "--mount",
        f"type=volume,source={PREFIX}-data,destination=/mosquitto/config,volume-subpath=config",
        "--mount",
        f"type=volume,source={PREFIX}-data,destination=/mosquitto/log,volume-subpath=log",
        "eclipse-mosquitto:latest",
    )
    from werkzeug.security import generate_password_hash

    env = root / "manager.env"
    env.write_text(
        "PUBLIC_ORIGIN=" + ORIGIN + "\nADMIN_USERNAME=admin\nADMIN_PASSWORD_HASH="
        + generate_password_hash(values["admin"], method="pbkdf2:sha256:600000")
        + "\nSECRET_KEY="
        + values["session"]
        + "\nMQTT_PASSWORD_FILE=/mosquitto/config/passwords\n"
    )
    env.chmod(0o600)
    run(
        "run",
        "-d",
        "--name",
        PREFIX + "-manager",
        "--network",
        PREFIX,
        "--pid",
        "container:" + PREFIX + "-broker",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=4m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--env-file",
        str(env),
        "--mount",
        f"type=volume,source={PREFIX}-data,destination=/mosquitto/config,volume-subpath=config",
        "--mount",
        f"type=volume,source={PREFIX}-data,destination=/mosquitto/log,volume-subpath=log,readonly",
        "--mount",
        f"type=volume,source={PREFIX}-data,destination=/data,volume-subpath=data",
        IMAGE,
    )
    # The configured preview container must already publish the preview port.
    # Give only the disposable manager a second interface; keep the broker isolated.
    preview_networks = json.loads(
        run("inspect", preview_container, "--format", "{{json .NetworkSettings.Networks}}")
    )
    if len(preview_networks) != 1:
        raise RuntimeError("Choose a single verified preview network before starting the proxy")
    run("network", "connect", next(iter(preview_networks)), PREFIX + "-manager")
    run(
        "run",
        "-d",
        "--name",
        PREFIX + "-https",
        "--network",
        "container:" + preview_container,
        "--entrypoint",
        "caddy",
        "caddy:latest",
        "reverse-proxy",
        "--from",
        ORIGIN,
        "--to",
        PREFIX + "-manager:8080",
        "--internal-certs",
    )
    print("Disposable broker, manager and HTTPS proxy started. Credentials not shown.")


def cleanup():
    for name in ["https", "manager", "broker"]:
        run("rm", "-fv", PREFIX + "-" + name, check=False)
    run("volume", "rm", PREFIX + "-data", check=False)
    run("network", "rm", PREFIX, check=False)


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["up"]:
        setup()
    elif sys.argv[1:] == ["down"]:
        cleanup()
    else:
        raise SystemExit("Choose up or down")
