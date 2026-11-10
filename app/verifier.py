"""Bounded fresh-CONNECT proof with private ephemeral Mosquitto options."""

import os
import re
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

from .passwd import AccountError, validate_password, validate_username


class FreshConnectVerifier:
    available = True

    def __init__(self, host, port=1883, executable="/usr/bin/mosquitto_sub", deadline=8.0):
        if not host or host.startswith("-") or not 1 <= int(port) <= 65535:
            raise ValueError("Provide a valid explicit broker endpoint")
        self.host, self.port, self.executable = host, int(port), executable
        self.deadline = min(8.0, max(1.0, float(deadline)))

    def _attempt(self, username, password, timeout):
        path = None
        try:
            fd, name = tempfile.mkstemp(prefix="mqtt-manager-options-")
            path = Path(name)
            # mkstemp is 0600. This exact options serialization was tested with
            # spaces, quotes, backslashes and Unicode on Mosquitto 2.1.2.
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(f"-u {username}\n-P {password}\n")
            cid = "mqtt-manager-check-" + secrets.token_hex(12)
            result = subprocess.run(
                [
                    self.executable,
                    "-o",
                    str(path),
                    "-h",
                    self.host,
                    "-p",
                    str(self.port),
                    "-i",
                    cid,
                    "-t",
                    "mqtt-manager-check",
                    "-E",
                    "-W",
                    "1",
                    "-d",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
                shell=False,
                close_fds=True,
            )
            return result.returncode == 0 and bool(
                re.search(rb"received CONNACK \(0\)(?:\r?\n|$)", result.stdout)
            )
        except subprocess.TimeoutExpired:
            return False
        except OSError:
            raise AccountError(
                "verification_failed", "The private connection check could not run."
            ) from None
        finally:
            if path:
                path.unlink(missing_ok=True)

    def __call__(self, username, password):
        validate_username(username)
        validate_password(password)
        until = time.monotonic() + self.deadline
        # Fail closed if this listener accepts an intentionally incorrect credential.
        # An accepted CONNACK alone cannot distinguish anonymous/fallback policy.
        if self._attempt(username, secrets.token_urlsafe(32), min(1.5, self.deadline)):
            raise AccountError(
                "authentication_unenforced",
                "The broker accepted an incorrect password. Verification is unsafe.",
            )
        while time.monotonic() < until:
            if self._attempt(username, password, min(1.5, max(0.05, until - time.monotonic()))):
                return True
            time.sleep(min(0.1, max(0, until - time.monotonic())))
        return False
