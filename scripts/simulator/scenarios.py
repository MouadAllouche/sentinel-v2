"""Scenario catalogue for the sandboxed threat simulator (Phase 20)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.rules.defaults import DEFAULT_RULES
from scripts.simulator import generators as gen

DEFAULT_RULE_IDS = frozenset(str(rule["id"]) for rule in DEFAULT_RULES)


@dataclass(frozen=True)
class Expectation:
    should_detect: bool
    rules_any_of: tuple[str, ...]
    min_severity: str
    incident: str  # yes | no | either
    max_false_positive_severity: str
    note: str


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    description: str
    mitre: tuple[str, ...]
    category: str  # attack | benign | evasion | combined
    build: Callable[[Any, datetime], gen.SimulatedActivity]
    expectation: Expectation


def _attack(
    identifier: str,
    title: str,
    description: str,
    mitre: tuple[str, ...],
    build: Callable[[Any, datetime], gen.SimulatedActivity],
    rules: tuple[str, ...],
    *,
    min_severity: str = "medium",
    incident: str = "either",
    note: str = "",
) -> Scenario:
    return Scenario(
        identifier,
        title,
        description,
        mitre,
        "attack",
        build,
        Expectation(
            True, rules, min_severity, incident, "low", note or f"Expected {rules[0]} to fire."
        ),
    )


def _benign(
    identifier: str,
    title: str,
    description: str,
    build: Callable[[Any, datetime], gen.SimulatedActivity],
    *,
    note: str,
    allowlisted: bool = False,
) -> Scenario:
    return Scenario(
        identifier,
        title,
        description,
        ("T1078",),
        "benign",
        build,
        Expectation(False, (), "low", "no", "low" if not allowlisted else "medium", note),
    )


SCENARIOS: tuple[Scenario, ...] = (
    _attack(
        "ssh-bruteforce-single-ip",
        "SSH brute force from one IP",
        "60 failed logins from one IP over ten minutes, mixed valid and invalid users.",
        ("T1110", "T1110.001"),
        gen.ssh_bruteforce_single_ip,
        ("ssh-bruteforce-by-ip",),
        note="Tier 2 (≥20) should fire high.",
    ),
    _attack(
        "password-spraying",
        "Password spraying",
        "One IP tries twelve usernames twice each, slowly.",
        ("T1110.003",),
        gen.password_spraying,
        ("ssh-password-spraying",),
        note="Distinct usernames matter.",
    ),
    _attack(
        "distributed-bruteforce",
        "Distributed brute force",
        "Fifteen IPs make three attempts each against admin.",
        ("T1110",),
        gen.distributed_bruteforce,
        ("ssh-distributed-single-user",),
        note="Distinct source IPs matter.",
    ),
    _attack(
        "credential-compromise-chain",
        "Credential compromise chain",
        "Failures, success, sudo visudo then a sudoers.d change.",
        ("T1078", "T1548.003"),
        gen.credential_compromise_chain,
        ("sensitive-sudo", "persistence-change"),
        min_severity="high",
        incident="yes",
        note="One incident with several score reasons.",
    ),
    _attack(
        "scanner-preauth-flood",
        "SSH pre-auth scan",
        "Many pre-auth disconnects and invalid users from one scanner.",
        ("T1046",),
        gen.scanner_preauth_flood,
        ("ssh-preauth-scanning",),
    ),
    _attack(
        "login-from-new-ip",
        "Login from a new IP",
        "A user with prior logins from two IPs logs in from a new public IP.",
        ("T1078",),
        gen.login_from_new_ip,
        ("new-ip-login",),
        note="Needs ten historical logins.",
    ),
    _attack(
        "backdoor-account",
        "Backdoor account",
        "A new account is created and added to the sudo group.",
        ("T1136.001", "T1098"),
        gen.backdoor_account,
        ("new-user-created", "user-added-to-privileged-group"),
    ),
    _attack(
        "persistence-cron",
        "Cron persistence",
        "A new file appears in etc/cron.d.",
        ("T1053.003",),
        gen.persistence_cron,
        ("persistence-change",),
    ),
    _attack(
        "persistence-ssh-key",
        "SSH key persistence",
        "A new key is appended to authorized_keys.",
        ("T1098.004",),
        gen.persistence_ssh_key,
        ("persistence-change",),
        note="Drift must name the key fingerprint, never the key.",
    ),
    _attack(
        "config-tampering",
        "World-writable sshd_config",
        "sshd_config becomes world-writable.",
        ("T1222.002",),
        gen.config_tampering,
        ("world-writable-sensitive-file",),
        min_severity="critical",
    ),
    _attack(
        "suspicious-process",
        "Process from /tmp",
        "Fake feed: a binary runs from /tmp.",
        ("T1059",),
        gen.suspicious_process,
        ("suspicious-process",),
    ),
    _attack(
        "unexpected-listener",
        "Listener on all interfaces",
        "Fake feed: a new listener on 0.0.0.0:4444.",
        ("T1049",),
        gen.unexpected_listener,
        ("new-listening-port-all-interfaces",),
    ),
    _attack(
        "recon-tool-install",
        "Recon tool install",
        "dpkg installs nmap.",
        ("T1592",),
        gen.recon_tool_install,
        ("recon-or-attack-tool-installed",),
        min_severity="low",
    ),
    _attack(
        "failed-login-spike",
        "Baseline anomaly",
        "Seven benign days then a forty-event spike in one hour.",
        ("T1110",),
        gen.failed_login_spike,
        ("baseline-failed-logins",),
        note="Explanation must include mean, std, samples and standard deviations.",
    ),
    Scenario(
        "low-and-slow",
        "Low and slow evasion",
        "One failed login every seven minutes for 24 hours, under every threshold window.",
        ("T1110",),
        "evasion",
        gen.low_and_slow,
        Expectation(
            False,
            (),
            "low",
            "no",
            "low",
            "Known blind spot: no threshold or baseline rule fires. Deliberate, not a failure.",
        ),
    ),
    _benign(
        "benign-admin-day",
        "Benign admin day",
        "Normal logins, sudo and apt installs with two typo'd passwords.",
        gen.benign_admin_day,
        note="No incident and no finding above low.",
    ),
    _benign(
        "benign-noisy-user",
        "Benign noisy user",
        "Three failed logins across a day then success.",
        gen.benign_noisy_user,
        note="Spread too far apart to cross a threshold.",
    ),
    _benign(
        "benign-allowlisted-monitor",
        "Allowlisted monitor",
        "A trusted monitoring host produces many failed logins.",
        gen.benign_allowlisted_monitor,
        note="Events are stored and visible; suppression is reported, no incident.",
        allowlisted=True,
    ),
    Scenario(
        "mixed-realistic-week",
        "Mixed realistic week",
        "Seven days of benign noise with three attacks hidden inside.",
        ("T1110", "T1078", "T1053.003"),
        "combined",
        gen.mixed_realistic_week,
        Expectation(
            True, ("ssh-bruteforce-by-ip",), "medium", "yes", "low", "Combined dashboard database."
        ),
    ),
)

_BY_ID = {scenario.id: scenario for scenario in SCENARIOS}


def scenario_ids() -> list[str]:
    return [scenario.id for scenario in SCENARIOS]


def get_scenario(identifier: str) -> Scenario:
    try:
        return _BY_ID[identifier]
    except KeyError as exc:
        raise ValueError(f"unknown scenario: {identifier}") from exc
