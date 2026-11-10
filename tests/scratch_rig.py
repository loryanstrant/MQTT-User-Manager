"""Explicit disposable broker/UI rig. No production host or account material."""

import json
import secrets
import subprocess
from pathlib import Path

PREFIX = "rufus-scratch-mqtt-c204b6db"
IMAGE = "rufus-scratch-mqtt-manager:c204b6db"


def run(*args, data=None, check=True):
    result = subprocess.run(
        ["docker", *args], input=data, capture_output=True, text=True, timeout=90
    )
    if check and result.returncode:
        raise RuntimeError(f"Scratch {args[0]} failed; output withheld")
    return result.stdout


def setup():
    root = Path(".scratch")
    root.mkdir(mode=0o700, exist_ok=True)
    values = {"existing": secrets.token_urlsafe(24), "session": secrets.token_urlsafe(48)}
    # Admin password supplied by parent from vault via stdin; never echo.
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
        "PUBLIC_ORIGIN=https://perceptor.strant.casa:8708\nADMIN_USERNAME=admin\nADMIN_PASSWORD_HASH="
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
    # Rufus already publishes preview ports. Give only our disposable manager a
    # second interface reachable from that namespace; the broker stays isolated.
    preview_networks = json.loads(
        run("inspect", "Rufus", "--format", "{{json .NetworkSettings.Networks}}")
    )
    if len(preview_networks) != 1:
        raise RuntimeError("Choose the verified Rufus preview network before starting the proxy")
    run("network", "connect", next(iter(preview_networks)), PREFIX + "-manager")
    run(
        "run",
        "-d",
        "--name",
        PREFIX + "-https",
        "--network",
        "container:Rufus",
        "--entrypoint",
        "caddy",
        "caddy:latest",
        "reverse-proxy",
        "--from",
        "https://perceptor.strant.casa:8708",
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
