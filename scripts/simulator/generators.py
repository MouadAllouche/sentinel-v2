"""Synthetic activity builders producing parser-identical log lines and fake feeds.

All timestamps are simulated. No network, subprocess or machine state is read.
Documentation-reserved IPs and invented usernames are used throughout.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

ATTACKER = "203.0.113.45"
ATTACKER2 = "203.0.113.60"
TRUSTED = "192.0.2.10"
BENIGN = "198.51.100.7"
DAY = timedelta(days=1)


@dataclass
class FileMutation:
    at: datetime
    path: str
    action: str  # append_key | create | chmod_world_writable
    content: str = ""


@dataclass
class FeedRecord:
    at: datetime
    kind: str  # connection | listener | process
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulatedActivity:
    """Everything a scenario produces, with simulated timestamps."""

    auth_lines: list[tuple[datetime, str]] = field(default_factory=list)
    dpkg_lines: list[tuple[datetime, str]] = field(default_factory=list)
    history_lines: list[tuple[datetime, str]] = field(default_factory=list)
    mutations: list[FileMutation] = field(default_factory=list)
    feeds: list[FeedRecord] = field(default_factory=list)
    allowlist_ips: list[str] = field(default_factory=list)
    malicious_from: datetime | None = None


def _iso(stamp: datetime) -> str:
    return stamp.isoformat()


def failed(stamp: datetime, user: str, ip: str, *, invalid: bool = False) -> str:
    who = f"invalid user {user}" if invalid else user
    return f"{_iso(stamp)} sshd[1]: Failed password for {who} from {ip} port 2200"


def success(stamp: datetime, user: str, ip: str) -> str:
    return f"{_iso(stamp)} sshd[1]: Accepted password for {user} from {ip} port 2200"


def sudo(stamp: datetime, user: str, command: str) -> str:
    return f"{_iso(stamp)} sudo:   {user} : USER=root ; COMMAND={command}"


def preauth(stamp: datetime, ip: str) -> str:
    return (
        f"{_iso(stamp)} sshd[1]: Connection closed by invalid user scanner {ip} port 2200 [preauth]"
    )


def user_created(stamp: datetime, name: str) -> str:
    return f"{_iso(stamp)} useradd[1]: new user: name={name}, UID=1001"


def group_add(stamp: datetime, name: str, group: str) -> str:
    return f"{_iso(stamp)} usermod[1]: add '{name}' to group '{group}'"


def dpkg_install(stamp: datetime, package: str) -> str:
    return f"{stamp.strftime('%Y-%m-%d %H:%M:%S')} install {package} 1.0"


def benign_history(
    rng: random.Random, start: datetime, *, days: int = 7, with_failures: bool = False
) -> list[tuple[datetime, str]]:
    lines: list[tuple[datetime, str]] = []
    for day in range(days):
        for index in range(3):
            stamp = start - timedelta(days=days - day, hours=index * 2)
            user = rng.choice(["alice", "bob", "carol"])
            lines.append((stamp, success(stamp, user, BENIGN)))
            lines.append(
                (
                    stamp + timedelta(minutes=1),
                    sudo(stamp + timedelta(minutes=1), user, "/usr/bin/id"),
                )
            )
            if with_failures:
                bad = stamp + timedelta(minutes=2)
                lines.append((bad, failed(bad, user, BENIGN)))
    return sorted(lines)


def ssh_bruteforce_single_ip(rng: random.Random, clock: datetime) -> SimulatedActivity:
    start = clock
    users = ["admin", "root", "guest", "support"]
    lines = [
        (
            start + timedelta(seconds=i * 10),
            failed(
                start + timedelta(seconds=i * 10), rng.choice(users), ATTACKER, invalid=i % 3 == 0
            ),
        )
        for i in range(60)
    ]
    lines.append(
        (start + timedelta(minutes=10), success(start + timedelta(minutes=10), "admin", ATTACKER))
    )
    return SimulatedActivity(auth_lines=sorted(lines), malicious_from=start)


def password_spraying(rng: random.Random, clock: datetime) -> SimulatedActivity:
    names = [f"user{index:02d}" for index in range(12)]
    lines: list[tuple[datetime, str]] = []
    for index, name in enumerate(names):
        for attempt in range(2):
            stamp = clock + timedelta(minutes=index * 2 + attempt)
            lines.append((stamp, failed(stamp, name, ATTACKER)))
    return SimulatedActivity(auth_lines=sorted(lines), malicious_from=clock)


def distributed_bruteforce(rng: random.Random, clock: datetime) -> SimulatedActivity:
    lines: list[tuple[datetime, str]] = []
    for index in range(15):
        ip = f"203.0.113.{10 + index}"
        for attempt in range(3):
            stamp = clock + timedelta(seconds=index * 20 + attempt * 5)
            lines.append((stamp, failed(stamp, "admin", ip)))
    return SimulatedActivity(auth_lines=sorted(lines), malicious_from=clock)


def credential_compromise_chain(rng: random.Random, clock: datetime) -> SimulatedActivity:
    lines: list[tuple[datetime, str]] = []
    for index in range(12):
        stamp = clock + timedelta(seconds=index * 30)
        lines.append((stamp, failed(stamp, "admin", ATTACKER)))
    ok = clock + timedelta(minutes=7)
    lines.append((ok, success(ok, "admin", ATTACKER)))
    visudo = ok + timedelta(minutes=1)
    lines.append((visudo, sudo(visudo, "admin", "/usr/sbin/visudo")))
    lines.append(
        (
            visudo + timedelta(minutes=1),
            sudo(visudo + timedelta(minutes=1), "admin", "/usr/bin/systemctl enable backdoor"),
        )
    )
    mutations = [
        FileMutation(
            visudo + timedelta(minutes=2),
            "etc/sudoers.d/backdoor",
            "create",
            "admin ALL=(ALL) NOPASSWD: ALL\n",
        )
    ]
    return SimulatedActivity(auth_lines=sorted(lines), mutations=mutations, malicious_from=clock)


def scanner_preauth_flood(rng: random.Random, clock: datetime) -> SimulatedActivity:
    lines = [
        (clock + timedelta(seconds=i * 5), preauth(clock + timedelta(seconds=i * 5), ATTACKER))
        for i in range(45)
    ]
    lines += [
        (
            clock + timedelta(seconds=i * 7 + 1),
            failed(clock + timedelta(seconds=i * 7 + 1), f"user{i}", ATTACKER, invalid=True),
        )
        for i in range(10)
    ]
    return SimulatedActivity(auth_lines=sorted(lines), malicious_from=clock)


def login_from_new_ip(rng: random.Random, clock: datetime) -> SimulatedActivity:
    history: list[tuple[datetime, str]] = []
    for index in range(10):
        stamp = clock - timedelta(days=8 - index // 2, hours=index)
        ip = BENIGN if index % 2 else "198.51.100.8"
        history.append((stamp, success(stamp, "alice", ip)))
    stamp = clock
    return SimulatedActivity(
        history_lines=sorted(history),
        auth_lines=[(stamp, success(stamp, "alice", ATTACKER))],
        malicious_from=stamp,
    )


def backdoor_account(rng: random.Random, clock: datetime) -> SimulatedActivity:
    a = clock
    b = clock + timedelta(minutes=2)
    return SimulatedActivity(
        auth_lines=[
            (a, user_created(a, "svc_backdoor")),
            (b, group_add(b, "svc_backdoor", "sudo")),
        ],
        malicious_from=a,
    )


def persistence_cron(rng: random.Random, clock: datetime) -> SimulatedActivity:
    return SimulatedActivity(
        mutations=[
            FileMutation(clock, "etc/cron.d/payload", "create", "*/5 * * * * root /usr/bin/id\n")
        ],
        malicious_from=clock,
    )


def persistence_ssh_key(rng: random.Random, clock: datetime) -> SimulatedActivity:
    return SimulatedActivity(
        mutations=[
            FileMutation(
                clock,
                "etc/authorized_keys",
                "append_key",
                "ssh-ed25519 c3NoLXN0b3JhZ2Utc2ltdWxhdGlvbg== simulator-added\n",
            )
        ],
        malicious_from=clock,
    )


def config_tampering(rng: random.Random, clock: datetime) -> SimulatedActivity:
    return SimulatedActivity(
        mutations=[FileMutation(clock, "etc/sshd_config", "chmod_world_writable")],
        malicious_from=clock,
    )


def suspicious_process(rng: random.Random, clock: datetime) -> SimulatedActivity:
    return SimulatedActivity(
        feeds=[
            FeedRecord(
                clock,
                "process",
                {"pid": 4100, "name": "payload", "exe": "/tmp/payload", "username": "nobody"},  # noqa: S108 - simulated path
            )
        ],
        malicious_from=clock,
    )


def unexpected_listener(rng: random.Random, clock: datetime) -> SimulatedActivity:
    # One minute later so the first cycle seeds the listener baseline first.
    return SimulatedActivity(
        feeds=[
            FeedRecord(
                clock + timedelta(minutes=2),
                "listener",
                {"port": 4444, "address": "0.0.0.0", "pid": 4200, "name": "payload"},  # noqa: S104 - simulated bind
            )
        ],
        malicious_from=clock,
    )


def recon_tool_install(rng: random.Random, clock: datetime) -> SimulatedActivity:
    return SimulatedActivity(
        dpkg_lines=[(clock, dpkg_install(clock, "nmap"))], malicious_from=clock
    )


def failed_login_spike(rng: random.Random, clock: datetime) -> SimulatedActivity:
    # Seven days of benign history, kept just inside the 7-day baseline query
    # window so the metric can reach maturity.
    history = benign_history(rng, clock + timedelta(hours=12), days=7, with_failures=True)
    spike = clock.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=30)
    lines = [
        (spike + timedelta(seconds=i), failed(spike + timedelta(seconds=i), "admin", ATTACKER))
        for i in range(40)
    ]
    return SimulatedActivity(
        history_lines=sorted(history), auth_lines=sorted(lines), malicious_from=spike
    )


def low_and_slow(rng: random.Random, clock: datetime) -> SimulatedActivity:
    end = clock + timedelta(hours=24)
    lines: list[tuple[datetime, str]] = []
    stamp = clock
    while stamp < end:
        lines.append((stamp, failed(stamp, "admin", ATTACKER)))
        stamp += timedelta(minutes=7)
    return SimulatedActivity(auth_lines=lines, malicious_from=clock)


def benign_admin_day(rng: random.Random, clock: datetime) -> SimulatedActivity:
    lines: list[tuple[datetime, str]] = []
    for index in range(8):
        stamp = clock + timedelta(hours=index)
        lines.append((stamp, success(stamp, "alice", TRUSTED)))
        lines.append(
            (
                stamp + timedelta(minutes=2),
                sudo(stamp + timedelta(minutes=2), "alice", "/usr/bin/id"),
            )
        )
    lines.append(
        (clock + timedelta(minutes=1), failed(clock + timedelta(minutes=1), "alice", TRUSTED))
    )
    lines.append(
        (
            clock + timedelta(hours=4, minutes=1),
            failed(clock + timedelta(hours=4, minutes=1), "alice", TRUSTED),
        )
    )
    return SimulatedActivity(auth_lines=sorted(lines))


def benign_noisy_user(rng: random.Random, clock: datetime) -> SimulatedActivity:
    lines = [
        (
            clock + timedelta(hours=index * 6),
            failed(clock + timedelta(hours=index * 6), "bob", BENIGN),
        )
        for index in range(3)
    ]
    lines.append((clock + timedelta(hours=18), success(clock + timedelta(hours=18), "bob", BENIGN)))
    return SimulatedActivity(auth_lines=sorted(lines))


def benign_allowlisted_monitor(rng: random.Random, clock: datetime) -> SimulatedActivity:
    lines = [
        (
            clock + timedelta(seconds=i * 10),
            failed(clock + timedelta(seconds=i * 10), "monitor", TRUSTED),
        )
        for i in range(25)
    ]
    return SimulatedActivity(auth_lines=lines, allowlist_ips=[TRUSTED])


def mixed_realistic_week(rng: random.Random, clock: datetime) -> SimulatedActivity:
    activity = SimulatedActivity(
        history_lines=benign_history(rng, clock, days=7), malicious_from=clock + DAY
    )
    # Attack 1: brute force on day 2.
    start = clock + DAY
    activity.auth_lines += [
        (
            start + timedelta(seconds=i * 10),
            failed(start + timedelta(seconds=i * 10), "admin", ATTACKER),
        )
        for i in range(25)
    ]
    # Attack 2: sudo + sudoers change on day 4.
    chain = clock + 3 * DAY
    activity.auth_lines += [
        (chain, success(chain, "admin", ATTACKER)),
        (
            chain + timedelta(minutes=1),
            sudo(chain + timedelta(minutes=1), "admin", "/usr/sbin/visudo"),
        ),
    ]
    activity.mutations.append(
        FileMutation(chain + timedelta(minutes=2), "etc/sudoers.d/backdoor", "create", "backdoor\n")
    )
    # Attack 3: cron persistence on day 6.
    cron = clock + 5 * DAY
    activity.mutations.append(
        FileMutation(cron, "etc/cron.d/payload", "create", "*/5 * * * * root /usr/bin/id\n")
    )
    activity.auth_lines.sort(key=lambda item: item[0])
    return activity
