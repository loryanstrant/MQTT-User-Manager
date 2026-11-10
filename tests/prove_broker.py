"""Isolated, synthetic MQTT mechanics proof; never connects to production."""

import json
import secrets
import subprocess
import time
from pathlib import Path

IMAGE = "eclipse-mosquitto:latest"
PREFIX = "rufus-scratch-mqtt-proof"
DATA, BROKER = PREFIX + "-data", PREFIX + "-broker"
results = {}


def docker(*args, stdin=None, check=True, timeout=30):
    p = subprocess.run(
        ["docker", *args], input=stdin, capture_output=True, text=True, timeout=timeout
    )
    if check and p.returncode:
        raise RuntimeError(
            f"Docker command {args[0]} failed (exit {p.returncode}); output withheld"
        )
    return p


def tool(*args, stdin=None, check=True):
    return docker(
        "run",
        "--rm",
        "-i",
        "--name",
        PREFIX + "-tool",
        "--user",
        "1883:1883",
        "--volumes-from",
        DATA,
        "--pid",
        "container:" + BROKER,
        "--network",
        "container:" + BROKER,
        "--entrypoint",
        args[0],
        IMAGE,
        *args[1:],
        stdin=stdin,
        check=check,
    )


def passwd(user, password, create=False, algo="sha512-pbkdf2"):
    args = ["mosquitto_passwd"] + (["-c"] if create else [])
    tool(*args, "-H", algo, "/scratch/passwords", user, stdin=password + "\n" + password + "\n")


def connect(user, password):
    cid = "mqtt-manager-proof-" + secrets.token_hex(8)
    # No secret in argv/environment; private options-file removed within the same invocation.
    options = f"-u {user}\n-P {password}\n"
    p = tool(
        "sh",
        "-c",
        'umask 077; f=$(mktemp /scratch/client.XXXXXX); trap \'rm -f "$f"\' EXIT; cat > "$f"; mosquitto_sub -o "$f" -h 127.0.0.1 -p 1883 -i "$1" -t mqtt-manager-proof -E -W 3 -d',
        "sh",
        cid,
        stdin=options,
        check=False,
    )
    return p.returncode == 0 and "received CONNACK (0)" in p.stdout


def reload_accounts():
    tool("mosquitto_signal", "-p", "1", "config-reload")
    time.sleep(0.25)


def publish(password, message):
    opts = f"-u existing\n-P {password}\n"
    tool(
        "sh",
        "-c",
        'umask 077; f=$(mktemp /scratch/client.XXXXXX); trap \'rm -f "$f"\' EXIT; cat > "$f"; mosquitto_pub -o "$f" -h 127.0.0.1 -p 1883 -t mqtt-manager-proof -q 1 -m "$1"',
        "sh",
        message,
        stdin=opts,
    )


try:
    docker(
        "run",
        "-d",
        "--name",
        DATA,
        "-v",
        "/scratch",
        "--entrypoint",
        "sh",
        IMAGE,
        "-c",
        "sleep 600",
    )
    docker(
        "exec",
        "-i",
        DATA,
        "sh",
        "-c",
        "cat > /scratch/mosquitto.conf; chown -R 1883:1883 /scratch; chmod 750 /scratch",
        stdin="listener 1883\nallow_anonymous false\npassword_file /scratch/passwords\nlog_dest stdout\nlog_type all\n",
    )
    existing, first, second = (secrets.token_urlsafe(24) for _ in range(3))
    docker(
        "exec",
        "-i",
        "--user",
        "1883:1883",
        DATA,
        "mosquitto_passwd",
        "-c",
        "-H",
        "sha512-pbkdf2",
        "/scratch/passwords",
        "existing",
        stdin=existing + "\n" + existing + "\n",
    )
    docker("exec", DATA, "chmod", "640", "/scratch/passwords")
    docker(
        "run",
        "-d",
        "--name",
        BROKER,
        "--user",
        "1883:1883",
        "--volumes-from",
        DATA,
        "--entrypoint",
        "mosquitto",
        IMAGE,
        "-c",
        "/scratch/mosquitto.conf",
    )
    for _ in range(20):
        if connect("existing", existing):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Initial authenticated connection failed")
    results["version"] = tool("mosquitto", "-h").stdout.splitlines()[0]
    identity = docker(
        "inspect", BROKER, "--format", "{{.Id}} {{.State.StartedAt}} {{.Image}}"
    ).stdout
    original = tool("sh", "-c", "cat /scratch/passwords").stdout
    opts = f"-u existing\n-P {existing}\n"
    tool("sh", "-c", "umask 077; cat > /scratch/existing.options", stdin=opts)
    watcher = subprocess.Popen(
        [
            "docker",
            "exec",
            "--user",
            "1883:1883",
            BROKER,
            "mosquitto_sub",
            "-o",
            "/scratch/existing.options",
            "-h",
            "127.0.0.1",
            "-t",
            "mqtt-manager-proof",
            "-i",
            "mqtt-manager-proof-existing",
            "-C",
            "4",
            "-W",
            "25",
            "-d",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.3)
    publish(existing, "before")
    passwd("newaccount", first)
    tool("chmod", "640", "/scratch/passwords")
    reload_accounts()
    assert connect("newaccount", first), "Add did not authenticate"
    assert connect("existing", existing), "Existing account was damaged"
    publish(existing, "after-add")
    results["add_and_existing_fresh_login"] = True
    passwd("newaccount", second)
    tool("chmod", "640", "/scratch/passwords")
    reload_accounts()
    assert connect("newaccount", second), "New password rejected"
    assert not connect("newaccount", first), "Old password still accepted"
    publish(existing, "after-change")
    results["change_new_accepted_old_refused"] = True
    tool("mosquitto_passwd", "-D", "/scratch/passwords", "newaccount")
    tool("chmod", "640", "/scratch/passwords")
    reload_accounts()
    assert not connect("newaccount", second), "Deleted account accepted"
    publish(existing, "after-delete")
    out, err = watcher.communicate(timeout=28)
    assert watcher.returncode == 0 and all(
        s in out.splitlines() for s in ["before", "after-add", "after-change", "after-delete"]
    )
    assert out.count("received CONNACK (0)") == 1, "Existing subscriber reconnected"
    results["existing_session_survived_three_reloads"] = True
    assert original == tool("sh", "-c", "cat /scratch/passwords").stdout
    results["unrelated_hash_unchanged"] = True
    results["password_file_permissions"] = tool(
        "stat", "-c", "%u:%g %a", "/scratch/passwords"
    ).stdout.strip()
    assert results["password_file_permissions"] == "1883:1883 640"
    assert (
        identity
        == docker("inspect", BROKER, "--format", "{{.Id}} {{.State.StartedAt}} {{.Image}}").stdout
    )
    results["broker_identity_unchanged"] = True
    assert "Reloading config" in docker("logs", BROKER).stdout
    results["shared_pid_reload_observed"] = True
    # Optional diagnostic only: do not disguise a hashing failure as a required-proof failure.
    argon = secrets.token_urlsafe(24)
    try:
        passwd("argonaccount", argon, algo="argon2id")
    except RuntimeError:
        results["optional_argon2id"] = (
            "Hash generation failed in this tested image; mixed-hash support not proved"
        )
    else:
        reload_accounts()
        assert connect("argonaccount", argon) and connect("existing", existing)
        results["optional_argon2id"] = "Mixed-hash fresh login proved"
    results["private_options_fresh_connack"] = True
    Path("_IMAGES/mqtt-mechanics-proof.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
finally:
    for name in [PREFIX + "-tool", BROKER, DATA]:
        docker("rm", "-fv", name, check=False)
