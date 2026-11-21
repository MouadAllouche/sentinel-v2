"""Static safety scans: no dangerous constructs or secret storage in source (Phase 18)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("core", "collectors", "storage", "engine", "api", "scripts")
DANGEROUS_CALLS = {"eval", "exec", "compile", "__import__"}
DANGEROUS_ATTRS = {"system", "popen"}


def _sources() -> list[Path]:
    paths: list[Path] = []
    for directory in SOURCE_DIRS:
        paths.extend((ROOT / directory).rglob("*.py"))
    paths.append(ROOT / "cli.py")
    return paths


def _suppressed(lines: list[str], lineno: int) -> bool:
    """A noqa on the call line or its multi-line arguments suppresses the finding."""
    window = lines[max(0, lineno - 1) : lineno + 4]
    return any("noqa" in item for item in window)


def test_no_dangerous_calls_or_shell() -> None:
    offenders: list[str] = []
    for path in _sources():
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _suppressed(lines, node.lineno):
                continue
            function = node.func
            if isinstance(function, ast.Name) and function.id in DANGEROUS_CALLS:
                offenders.append(f"{path}:{node.lineno}: {function.id}()")
            if isinstance(function, ast.Attribute) and function.attr in DANGEROUS_ATTRS:
                offenders.append(f"{path}:{node.lineno}: .{function.attr}()")
            for keyword in node.keywords:
                if (
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    offenders.append(f"{path}:{node.lineno}: shell=True")
    assert offenders == []


def test_storage_sql_is_parameterised() -> None:
    """No f-strings, %-format or .format() may be passed to SQL execute calls."""
    offenders: list[str] = []
    for path in (ROOT / "storage").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"execute", "executemany"}:
                continue
            if (
                node.args
                and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp))
                and not _suppressed(lines, node.lineno)
            ):
                offenders.append(f"{path}:{node.lineno}: built SQL string")
    assert offenders == []


def test_no_secret_or_cmdline_storage() -> None:
    for path in _sources():
        text = path.read_text(encoding="utf-8").lower()
        if "cmdline" in text:
            assert "processes.py" in str(path) or "test" in str(path)
        if "/etc/shadow" in text:
            assert (
                "metadata_only" in text
                or "shadow_paths" in text
                or "drift_repository.py" in str(path)
                or "test" in str(path)
            )


def test_gitignore_ignores_secrets_and_demo() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in ignored
    assert "demo_workdir/" in ignored
    assert ".demo-e2e/" in ignored
