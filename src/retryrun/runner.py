"""Runs a command, retrying it on failure.

The runner is deliberately boring: it shells out, checks the exit code,
waits, and tries again. All the interesting decisions — which exit codes
count as retryable, how long to wait — live in `RetryConfig` and in
`schedule.py`, so this module stays easy to test without ever spawning
a real process (pass a fake `execute` in tests).
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable

from .errors import CommandNotFoundError
from .schedule import delay_before_attempt

# Matches GNU timeout's convention, so scripts can tell a timeout apart
# from an ordinary failure.
TIMEOUT_EXIT_CODE = 124


@dataclass
class RetryConfig:
    """Everything a retry run needs to know."""

    command: list[str]
    tries: int = 3
    delay: float = 1.0
    backoff: float = 2.0
    timeout: float | None = None
    # If set, only these exit codes trigger a retry. Any other non-zero
    # code returns immediately — no point retrying a usage error.
    only_on: frozenset[int] | None = None
    jitter: bool = False
    quiet: bool = False


@dataclass
class AttemptResult:
    """Outcome of a single attempt."""

    exit_code: int
    timed_out: bool = False


@dataclass
class RunResult:
    """Outcome of the whole retry run."""

    exit_code: int
    attempts: int
    succeeded: bool


def _execute(command: list[str], timeout: float | None) -> AttemptResult:
    """Run the command once, returning its exit code.

    Raises CommandNotFoundError when the program does not exist, and
    translates a timeout into exit code 124 instead of crashing.
    """
    try:
        proc = subprocess.run(command, timeout=timeout)
    except FileNotFoundError:
        raise CommandNotFoundError(
            f"retryrun: command not found: {command[0]!r}\n"
            "Check the spelling, or install the program first."
        ) from None
    except subprocess.TimeoutExpired:
        return AttemptResult(exit_code=TIMEOUT_EXIT_CODE, timed_out=True)
    return AttemptResult(exit_code=proc.returncode)


def run_with_retries(
    config: RetryConfig,
    execute: Callable[[list[str], float | None], AttemptResult] = _execute,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] | None = None,
) -> RunResult:
    """Run `config.command`, retrying on failure up to `config.tries`.

    Returns the exit code of the last attempt (0 on success). Progress
    goes to `log` when provided and the run is not quiet; nothing is
    printed by default, so library users stay in control.
    """
    notify = (lambda msg: None) if (log is None or config.quiet) else log

    last_code = 0
    for attempt in range(1, config.tries + 1):
        result = execute(config.command, config.timeout)
        last_code = result.exit_code

        if result.exit_code == 0:
            notify(f"attempt {attempt}/{config.tries} succeeded")
            return RunResult(exit_code=0, attempts=attempt, succeeded=True)

        retryable = config.only_on is None or result.exit_code in config.only_on
        if attempt == config.tries or not retryable:
            why = "timed out" if result.timed_out else f"exited with {result.exit_code}"
            notify(f"attempt {attempt}/{config.tries} {why}; giving up")
            return RunResult(
                exit_code=result.exit_code, attempts=attempt, succeeded=False
            )

        wait = delay_before_attempt(attempt + 1, config.delay, config.backoff, config.jitter)
        why = "timed out" if result.timed_out else f"exited with {result.exit_code}"
        notify(
            f"attempt {attempt}/{config.tries} {why}; "
            f"retrying in {wait:.1f}s"
        )
        sleep(wait)

    # Unreachable in practice (the loop always returns), but mypy and
    # future-me both prefer an explicit answer to a fall-through.
    return RunResult(exit_code=last_code, attempts=config.tries, succeeded=False)
