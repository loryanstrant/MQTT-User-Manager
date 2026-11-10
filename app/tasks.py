"""One running transaction; no queue, secrets never stored in task results."""

import secrets
import threading
import time
from collections import OrderedDict

from .passwd import AccountError, CriticalError


class OperationManager:
    def __init__(self, *, retention=32, ttl=900, clock=time.monotonic):
        self.lock = threading.Lock()
        self.active = None
        self.results = OrderedDict()
        self.retention, self.ttl, self.clock = retention, ttl, clock

    def _prune(self):
        for task_id in list(self.results):
            if task_id != self.active and (
                self.clock() - self.results[task_id]["updated"] > self.ttl
                or len(self.results) > self.retention
            ):
                del self.results[task_id]

    def submit(self, owner, job):
        with self.lock:
            self._prune()
            if self.active is not None:
                raise AccountError(
                    "busy", "An account change is already running; wait for it to finish."
                )
            task_id = secrets.token_urlsafe(24)
            self.active = task_id
            self.results[task_id] = {
                "owner": owner,
                "updated": self.clock(),
                "public": {
                    "id": task_id,
                    "status": "running",
                    "label": "◐ Working",
                    "message": "Checking the account change",
                },
            }

        def progress(message):
            with self.lock:
                self.results[task_id]["updated"] = self.clock()
                self.results[task_id]["public"]["message"] = message

        def work():
            result = {
                "status": "failed",
                "label": "○ Failed",
                "error": "interrupted",
                "message": "The operation was interrupted; check the account list and recovery warning.",
            }
            try:
                result = job(progress)
            except CriticalError as error:
                result = {
                    "status": "critical",
                    "label": "◐ Recovery required",
                    "error": error.code,
                    "message": error.message,
                }
            except AccountError as error:
                result = {
                    "status": "failed",
                    "label": "○ Failed",
                    "error": error.code,
                    "message": error.message,
                }
            except BaseException:
                result = {
                    "status": "failed",
                    "label": "○ Failed",
                    "error": "operation_failed",
                    "message": "The operation failed; check the account list before trying again.",
                }
            finally:
                with self.lock:
                    self.results[task_id]["public"] = {"id": task_id, **result}
                    self.results[task_id]["updated"] = self.clock()
                    self.active = None
                    self._prune()

        try:
            thread = threading.Thread(target=work, name="mqtt-account-transaction", daemon=True)
            thread.start()
        except Exception:
            with self.lock:
                self.active = None
                self.results.pop(task_id, None)
            raise AccountError(
                "busy", "The account worker could not start; nothing was changed."
            ) from None
        return task_id

    def get(self, task_id, owner):
        with self.lock:
            self._prune()
            result = self.results.get(task_id)
            if result is None or result["owner"] != owner:
                raise AccountError("missing", "That operation is unavailable or has expired.")
            return dict(result["public"])
