"""Bounded CLI transport. Raw diagnostics are discarded, never returned or logged."""

import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass

from backend.app.orchestration.contracts import ErrorCategory


class RuntimeFailure(Exception):
    def __init__(self, category: ErrorCategory):
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str


class OpenClawCLI:
    """POSIX transport with a combined stdout/stderr budget and process-group cleanup."""

    def __init__(self, timeout: int = 60, max_bytes: int = 1_048_576):
        if not 1 <= timeout <= 600 or not 1024 <= max_bytes <= 4_194_304:
            raise ValueError("Invalid CLI resource budget")
        self.timeout, self.max_bytes = timeout, max_bytes

    def execute(self, arguments: list[str], prompt: str = "") -> CommandResult:
        executable = shutil.which("openclaw")
        if not executable:
            raise RuntimeFailure(ErrorCategory.NOT_INSTALLED)
        if os.name != "posix":
            raise RuntimeFailure(ErrorCategory.UNAVAILABLE)
        encoded = prompt.encode("utf-8")
        if len(encoded) > self.max_bytes:
            raise RuntimeFailure(ErrorCategory.EXECUTION)
        try:
            with tempfile.TemporaryFile() as source:
                source.write(encoded)
                source.seek(0)
                with subprocess.Popen(
                    [executable, *arguments],
                    stdin=source,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    start_new_session=True,
                ) as process:
                    try:
                        return self._collect(process)
                    except BaseException:
                        # Kill the CLI group, including children, on timeout/overflow/interruption.
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait()
                        raise
        except RuntimeFailure:
            raise
        except OSError:
            raise RuntimeFailure(ErrorCategory.UNAVAILABLE) from None

    def _collect(self, process) -> CommandResult:
        deadline, total, output = time.monotonic() + self.timeout, 0, bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, True)
            selector.register(process.stderr, selectors.EVENT_READ, False)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeFailure(ErrorCategory.TIMEOUT)
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise RuntimeFailure(ErrorCategory.EXECUTION)
                    if key.data:
                        output.extend(chunk)
            try:
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise RuntimeFailure(ErrorCategory.TIMEOUT) from None
        try:
            return CommandResult(code, output.decode("utf-8"))
        except UnicodeDecodeError:
            raise RuntimeFailure(ErrorCategory.INVALID_OUTPUT) from None

    def json(self, arguments: list[str]):
        result = self.execute(arguments)
        if result.returncode:
            raise RuntimeFailure(ErrorCategory.UNAVAILABLE)
        return parse_json(result.stdout)

    def version(self) -> str:
        result = self.execute(["--version"])
        match = re.fullmatch(r"OpenClaw (\d{4}\.\d+\.\d+)(?: \([a-f0-9]+\))?\s*", result.stdout)
        if result.returncode or not match:
            raise RuntimeFailure(ErrorCategory.UNAVAILABLE)
        return match[1]


def parse_json(text: str):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, RecursionError):
        raise RuntimeFailure(ErrorCategory.INVALID_OUTPUT) from None


def configured_agents(cli: OpenClawCLI) -> list[dict]:
    data = cli.json(["agents", "list", "--json"])
    if (
        not isinstance(data, list)
        or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in data)
        or len({item["id"] for item in data}) != len(data)
    ):
        raise RuntimeFailure(ErrorCategory.UNAVAILABLE)
    return data


def health_check(cli: OpenClawCLI | None = None) -> dict:
    """Read-only, no probes/auth flow. Return only version, counts, and readiness flags."""
    cli = cli or OpenClawCLI()
    report = {
        "available": False,
        "version": None,
        "agent_count": 0,
        "model_configured": False,
        "error": None,
    }
    try:
        report["version"] = cli.version()
        report["available"] = True
        report["agent_count"] = len(configured_agents(cli))
        status = cli.json(["models", "status", "--json"])
        if not isinstance(status, dict):
            raise RuntimeFailure(ErrorCategory.UNAVAILABLE)
        report["model_configured"] = isinstance(status.get("resolvedDefault"), str)
    except RuntimeFailure as exc:
        report["error"] = exc.category.value
    return report
