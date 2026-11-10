"""Bounded incremental log observations, not a keepalive monitor."""

from __future__ import annotations

import os
import re
import stat
import threading
from collections import Counter, OrderedDict, deque
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CONNECT = re.compile(
    r"New client connected from .+ as (\S{1,256}) \([^\n]*?u['\"]([^'\"]{1,128})['\"][^\n]*\)\.?$"
)
DISCONNECT = re.compile(
    r"Client (\S{1,256})(?: \[[^\]\s]{1,256}\])? (?:disconnected(?:.*)?|closed its connection\.?|has exceeded timeout, disconnecting\.?|has been disconnected.*|already connected, closing old connection\.?)$"
)
STAMP = re.compile(
    r"^(\d{10}(?:\.\d+)?|\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?):?\s+(.*)$"
)


class PresenceTracker:
    def __init__(
        self,
        path: Path,
        *,
        max_scan=1024 * 1024,
        max_sessions=10000,
        max_accounts=10000,
        zone="Australia/Melbourne",
        reconnect_count=0,
        reconnect_window=300,
        clock=lambda: datetime.now(timezone.utc).timestamp(),
    ):
        self.path = Path(path)
        self.max_scan, self.max_sessions, self.max_accounts = max_scan, max_sessions, max_accounts
        self.zone = ZoneInfo(zone)
        self.reconnect_count, self.reconnect_window, self.clock = (
            reconnect_count,
            reconnect_window,
            clock,
        )
        self.lock = threading.Lock()
        self.identity, self.offset, self.anchor = None, 0, b""
        self.sessions = {}
        self.observed = OrderedDict()
        self.reconnections = {}
        self.available = False
        self.incomplete = True

    def _time(self, value):
        try:
            if re.fullmatch(r"\d{10}(?:\.\d+)?", value):
                return float(value)
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if date.tzinfo is None:
                date = date.replace(tzinfo=self.zone)
            return date.timestamp()
        except (ValueError, OverflowError):
            return None

    def _remember(self, username, stamp, connected):
        previous = self.observed.get(username)
        if previous and stamp < previous[0]:
            return
        self.observed[username] = (stamp, connected)
        self.observed.move_to_end(username)
        while len(self.observed) > self.max_accounts:
            name, _ = self.observed.popitem(last=False)
            self.reconnections.pop(name, None)
            self.sessions = {
                cid: details for cid, details in self.sessions.items() if details[0] != name
            }
            self.incomplete = True

    def _line(self, line):
        matched = STAMP.match(line)
        if not matched:
            return
        stamp = self._time(matched[1])
        message = matched[2]
        if stamp is None or stamp > self.clock() + 300:
            return
        if re.search(r"mosquitto version \S+ (?:starting|terminating)", message):
            for name in {details[0] for details in self.sessions.values()}:
                self._remember(name, stamp, False)
            self.sessions.clear()
            self.reconnections.clear()
            self.incomplete = False
            return
        match = CONNECT.search(message)
        if match:
            cid, username = match.groups()
            if cid.startswith("mqtt-manager-check-"):
                return  # Internal verification is not evidence of device activity.
            old = self.sessions.pop(cid, None)
            if old and old[0] != username:
                self._remember(
                    old[0], stamp, any(name == old[0] for name, _ in self.sessions.values())
                )
            previous = self.observed.get(username)
            if self.reconnect_count and previous and previous[1] is False:
                events = self.reconnections.setdefault(
                    username, deque(maxlen=max(1, self.reconnect_count))
                )
                events.append(stamp)
            self.sessions[cid] = (username, stamp)
            self._remember(username, stamp, True)
            if len(self.sessions) > self.max_sessions:
                self.sessions.clear()
                self.reconnections.clear()
                self.incomplete = True
                self.observed = OrderedDict(
                    (name, (value[0], None)) for name, value in self.observed.items()
                )
            return
        match = DISCONNECT.search(message)
        if match:
            old = self.sessions.pop(match[1], None)
            if old:
                self._remember(
                    old[0], stamp, any(name == old[0] for name, _ in self.sessions.values())
                )

    def scan(self):
        with self.lock:
            try:
                fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode):
                        raise OSError
                    identity = (info.st_dev, info.st_ino)
                    # Anchor also catches copytruncate+regrowth between scans.
                    anchor_changed = False
                    if identity == self.identity and self.anchor:
                        stream.seek(max(0, self.offset - len(self.anchor)))
                        anchor_changed = stream.read(len(self.anchor)) != self.anchor
                    changed = (
                        identity != self.identity or info.st_size < self.offset or anchor_changed
                    )
                    if changed:
                        self.sessions.clear()
                        self.reconnections.clear()
                        self.observed = OrderedDict(
                            (name, (value[0], None)) for name, value in self.observed.items()
                        )
                        self.offset, self.identity, self.incomplete = 0, identity, True
                    skipped = info.st_size - self.offset > self.max_scan
                    if skipped:
                        self.offset = info.st_size - self.max_scan
                        self.sessions.clear()
                        self.reconnections.clear()
                        self.observed = OrderedDict(
                            (name, (value[0], None)) for name, value in self.observed.items()
                        )
                        self.incomplete = True
                    stream.seek(self.offset)
                    data = stream.read(self.max_scan)
                    start = self.offset
                    if skipped:
                        newline = data.find(b"\n")
                        data = data[newline + 1 :] if newline >= 0 else b""
                        start = stream.tell() - len(data)
                    last = data.rfind(b"\n")
                    complete = data[: last + 1] if last >= 0 else b""
                    for line in complete.splitlines():
                        if len(line) <= 4096:
                            self._line(line.decode("utf-8", errors="replace"))
                        else:
                            # A skipped line may contain a disconnect. Do not let
                            # pre-gap sessions suppress the per-row warning.
                            self.sessions.clear()
                            self.reconnections.clear()
                            self.observed = OrderedDict(
                                (name, (value[0], None)) for name, value in self.observed.items()
                            )
                            self.incomplete = True
                    self.offset = start + len(complete)
                    stream.seek(max(0, self.offset - 64))
                    self.anchor = stream.read(min(64, self.offset))
                    self.available = True
            except OSError:
                self.available = False
                self.sessions.clear()
                self.reconnections.clear()
                self.incomplete = True
                self.observed = OrderedDict(
                    (name, (value[0], None)) for name, value in self.observed.items()
                )

    def rows(self, usernames):
        self.scan()
        with self.lock:
            result = {}
            counts = Counter(name for name, _ in self.sessions.values())
            for username in usernames:
                observation = self.observed.get(username)
                stamp = observation[0] if observation else None
                count = counts[username]
                if not self.available or not observation or observation[1] is None:
                    status, label = "unknown", "○ Unknown"
                elif count:
                    status, label = "connected", "● Connected"
                elif observation[1] is False:
                    events = self.reconnections.get(username, ())
                    if (
                        self.reconnect_count
                        and len(events) >= self.reconnect_count
                        and events[0] >= self.clock() - self.reconnect_window
                    ):
                        status, label = "reconnecting", "◐ Reconnecting"
                    else:
                        status, label = "disconnected", "○ Disconnected"
                else:
                    status, label = "unknown", "○ Unknown"
                result[username] = {
                    "status": status,
                    "status_label": label,
                    "connections": count,
                    "last_seen": datetime.fromtimestamp(stamp, timezone.utc).isoformat()
                    if stamp
                    else None,
                    "last_seen_local": datetime.fromtimestamp(stamp, self.zone).strftime(
                        "%d %b %Y %H:%M:%S %Z"
                    )
                    if stamp
                    else None,
                    "log_incomplete": self.incomplete,
                    # Positive observed presence can resolve this row without
                    # claiming complete history or an exact/live session count.
                    # A retained timestamp alone cannot restore certainty after
                    # a gap or rule out unseen parallel sessions on disconnect.
                    "presence_uncertain": self.incomplete and (not self.available or not count),
                    "source": "log observation",
                }
            return result
