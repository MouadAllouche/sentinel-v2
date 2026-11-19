"""Static, indicative MITRE ATT&CK mapping. No network lookups."""

from __future__ import annotations

from typing import Any

__all__ = ["mitre_for_rules", "mitre_table"]

_TECHNIQUES: dict[str, tuple[str, str]] = {
    "T1110": ("Brute Force", "Credential Access"),
    "T1110.001": ("Password Guessing", "Credential Access"),
    "T1110.003": ("Password Spraying", "Credential Access"),
    "T1078": ("Valid Accounts", "Defense Evasion"),
    "T1548.003": ("Sudo and Sudo Caching", "Privilege Escalation"),
    "T1098": ("Account Manipulation", "Persistence"),
    "T1098.004": ("SSH Authorized Keys", "Persistence"),
    "T1136.001": ("Create Local Account", "Persistence"),
    "T1053.003": ("Cron", "Persistence"),
    "T1543.002": ("Systemd Service", "Persistence"),
    "T1222.002": ("Linux File and Directory Permissions Modification", "Defense Evasion"),
    "T1021.004": ("SSH", "Lateral Movement"),
    "T1046": ("Network Service Discovery", "Discovery"),
    "T1571": ("Non-Standard Port", "Command and Control"),
    "T1059": ("Command and Scripting Interpreter", "Execution"),
    "T1595": ("Active Scanning", "Reconnaissance"),
}

_TACTIC_ORDER = [
    "Reconnaissance",
    "Discovery",
    "Credential Access",
    "Execution",
    "Privilege Escalation",
    "Defense Evasion",
    "Persistence",
    "Lateral Movement",
    "Command and Control",
]


def mitre_table() -> dict[str, dict[str, str]]:
    return {
        identifier: {
            "name": name,
            "tactic": tactic,
            "url": f"https://attack.mitre.org/techniques/{identifier.replace('.', '/')}/",
        }
        for identifier, (name, tactic) in _TECHNIQUES.items()
    }


def mitre_for_rules(rule_ids: list[str]) -> list[dict[str, Any]]:
    """Return a tactic-ordered union of techniques for the given rule ids."""
    table = mitre_table()
    from core.rules.defaults import DEFAULT_RULES

    wanted: set[str] = set()
    for definition in DEFAULT_RULES:
        if definition["id"] in rule_ids:
            wanted.update(definition.get("mitre") or [])
    wanted.update(rule_ids)  # accept raw technique ids as well as rule ids
    sorted_ids = sorted(
        (identifier for identifier in wanted if identifier in table),
        key=lambda identifier: (_TACTIC_ORDER.index(table[identifier]["tactic"]), identifier),
    )
    return [
        {
            "id": identifier,
            "name": table[identifier]["name"],
            "tactic": table[identifier]["tactic"],
            "url": table[identifier]["url"],
            "label": f"{identifier} {table[identifier]['name']} "
            "(indicative mapping; verify at attack.mitre.org)",
        }
        for identifier in sorted_ids
    ]
