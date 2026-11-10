"""Explicit disposable image smoke check; no live broker, ports or credentials."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path


class SmokeFailure(RuntimeError):
    """Sanitized failure; command output may contain private test material."""


def docker(*args, data=None, timeout=90):
    try:
        result = subprocess.run(
            ["docker", *args], input=data, text=True, capture_output=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SmokeFailure(f"Disposable image {args[0]} failed; output withheld") from None
    if result.returncode:
        if args[:2] == ("rm", "-f") and "No such container:" in result.stderr:
            return ""
        raise SmokeFailure(f"Disposable image {args[0]} refused; output withheld")
    return result.stdout


def remove_containers(*names):
    failed = False
    for name in names:
        try:
            docker("rm", "-f", name)
        except SmokeFailure:
            failed = True
    if failed:
        raise SmokeFailure("Disposable image cleanup failed; check test containers; output withheld")


# Runs inside the container. The generated credential arrives only through stdin.
HTTP_PROOF = r'''
import hashlib, http.cookies, json, time, urllib.error, urllib.request
v=json.loads(input())
base='http://127.0.0.1:8080'
origin='https://mqtt-users.example.invalid'
def request(path, payload=None, headers=None):
    headers={'Host':'mqtt-users.example.invalid', **(headers or {})}
    if payload is not None:
        headers['Content-Type']='application/json'
    req=urllib.request.Request(base+path, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    try:
        response=urllib.request.urlopen(req, timeout=2)
    except urllib.error.HTTPError as error:
        response=error
    return response.status, response.read(), response.headers
for attempt in range(30):
    try:
        code,body,headers=request('/healthz')
        assert code==200 and json.loads(body)=={'status':'ok'}
        break
    except (OSError, AssertionError):
        time.sleep(0.2)
else:
    raise RuntimeError('Application did not become live')
code,body,headers=request('/')
assert code==200 and b'accounts.js' in body
for name,digest in v['assets'].items():
    code,body,headers=request('/static/'+name)
    assert code==200 and hashlib.sha256(body).hexdigest()==digest
code,body,headers=request('/api/accounts')
assert code==401 and 'no-store' in headers['Cache-Control']
code,body,headers=request('/auth/csrf')
assert code==200
csrf=json.loads(body)['csrf_token']
cookie=http.cookies.SimpleCookie()
cookie.load(headers['Set-Cookie'])
assert cookie['mqtt_admin']['secure'] and cookie['mqtt_admin']['httponly']
assert cookie['mqtt_admin']['samesite']=='Strict'
session='mqtt_admin='+cookie['mqtt_admin'].value
code,body,headers=request('/auth/login', {'username':'admin','password':v['admin']},
    {'Origin':origin, 'X-CSRF-Token':csrf, 'Cookie':session})
assert code==200 and json.loads(body)['authenticated'] is True
rotated=json.loads(body)['csrf_token']
assert rotated!=csrf
cookie.load(headers['Set-Cookie'])
session='mqtt_admin='+cookie['mqtt_admin'].value
# Mutations with a mismatching Origin must be refused before any broker adapter.
code,body,headers=request('/api/operations', {'action':'add','username':'synthetic-device','password':v['admin']},
    {'Origin':'https://untrusted.example.invalid', 'X-CSRF-Token':rotated, 'Cookie':session})
assert code==403
code,body,headers=request('/auth/logout', {},
    {'Origin':origin,'X-CSRF-Token':rotated,'Cookie':session})
assert code==200
code,body,headers=request('/auth/session', headers={'Cookie':session})
assert code==401 and json.loads(body)['error']=='unauthorized'
print('Image HTTP, exact assets, login, Origin guard and logout passed')
'''


def smoke(image):
    root = Path(__file__).resolve().parents[1]
    scratch = root / ".scratch"
    scratch.mkdir(mode=0o700, exist_ok=True)
    name = "rufus-scratch-mqtt-image-" + secrets.token_hex(6)
    with tempfile.TemporaryDirectory(prefix="image-smoke-", dir=scratch) as directory:
        directory = Path(directory)
        try:
            admin = secrets.token_urlsafe(32)
            # Generate the hash using the image's own dependency set, not host packages.
            password_hash = docker(
                "run", "--rm", "-i", "--network", "none", "--name", name + "-hash",
                "--entrypoint", "python", image, "-c",
                "from werkzeug.security import generate_password_hash; "
                "print(generate_password_hash(input(), method='pbkdf2:sha256:600000'))",
                data=admin + "\n",
            ).strip()
            env = directory / "manager.env"
            env.write_text(
                "PUBLIC_ORIGIN=https://mqtt-users.example.invalid\nADMIN_USERNAME=admin\n"
                "ADMIN_PASSWORD_HASH=" + password_hash + "\nSECRET_KEY="
                + secrets.token_urlsafe(48) + "\n",
            )
            env.chmod(0o600)
            # No network, broker namespace, host bind mount or published port.
            docker(
                "run", "-d", "--name", name, "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--pids-limit", "64", "--memory", "256m",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=4m,mode=1777",
                "--tmpfs", "/data:rw,noexec,nosuid,size=4m,mode=0700,uid=1883,gid=1883",
                "--env-file", str(env), image,
            )
            inspection = json.loads(docker("inspect", name))[0]
            assert inspection["Config"]["User"] == "1883:1883"
            assert inspection["HostConfig"]["ReadonlyRootfs"]
            assert inspection["HostConfig"]["NetworkMode"] == "none"
            assert not inspection["HostConfig"]["PidMode"]
            assert not inspection["HostConfig"]["Binds"]
            assert inspection["Config"]["Entrypoint"] == ["python", "wsgi.py"]
            tools = docker(
                "exec", name, "python", "-c",
                "import shutil,os; assert os.getuid()==1883; "
                "assert all(shutil.which(x) for x in "
                "['mosquitto_passwd','mosquitto_sub','mosquitto_pub'])",
            )
            assert tools == ""
            assets = {
                name: hashlib.sha256((root / "app/static" / name).read_bytes()).hexdigest()
                for name in ("accounts.js", "style.css", "icon.png", "favicon.ico", "github-mark.png")
            }
            result = docker(
                "exec", "-i", name, "python", "-c", HTTP_PROOF,
                data=json.dumps({"admin": admin, "assets": assets}) + "\n",
            )
            assert "Image HTTP, exact assets, login, Origin guard and logout passed" in result
        finally:
            # Docker timeouts can leave either exact disposable name running.
            primary_failure = sys.exc_info()[0] is not None
            try:
                remove_containers(name, name + "-hash")
            except SmokeFailure:
                if not primary_failure:
                    raise
                print("Disposable cleanup also failed; check test containers; output withheld", file=sys.stderr)
    print("Disposable image smoke passed; container and private test files removed")


if __name__ == "__main__":
    try:
        smoke(os.environ.get("MQTT_SMOKE_IMAGE", "mqtt-user-manager:local"))
    except SmokeFailure as error:
        raise SystemExit(str(error)) from None
    except AssertionError:
        raise SystemExit("Disposable image contract assertion failed; details withheld") from None
