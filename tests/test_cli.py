"""Tests for CLI parsing, validation, dry-run, and real end-to-end runs."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from retryrun.cli import build_config, build_parser, main, parse_only_on
from retryrun.errors import InvalidOptionError

SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")


def _args(**overrides):
    """A parsed namespace with sensible defaults, overridable per test."""
    namespace = build_parser().parse_args(["true"])
    for key, value in overrides.items():
        setattr(namespace, key, value)
    return namespace


def test_parse_only_on_splits_codes():
    assert parse_only_on("1,2,124") == frozenset({1, 2, 124})
    assert parse_only_on(None) is None


def test_parse_only_on_rejects_words():
    with pytest.raises(InvalidOptionError):
        parse_only_on("one,two")


def test_parse_only_on_rejects_empty():
    with pytest.raises(InvalidOptionError):
        parse_only_on(",,,")


def test_tries_below_one_rejected():
    with pytest.raises(InvalidOptionError):
        build_config(_args(tries=0))


def test_negative_delay_rejected():
    with pytest.raises(InvalidOptionError):
        build_config(_args(delay=-1.0))


def test_backoff_below_one_rejected():
    with pytest.raises(InvalidOptionError):
        build_config(_args(backoff=0.5))


def test_non_positive_timeout_rejected():
    with pytest.raises(InvalidOptionError):
        build_config(_args(timeout=0.0))


def test_missing_command_rejected():
    with pytest.raises(InvalidOptionError):
        build_config(_args(command=[]))


def test_double_dash_separator_is_stripped():
    config = build_config(_args(command=["--", "echo", "hi"]))
    assert config.command == ["echo", "hi"]


def test_dry_run_prints_schedule_without_running(capsys):
    assert main(["--dry-run", "--tries", "3", "--delay", "1", "--backoff", "2", "false"]) == 0
    out = capsys.readouterr().out
    assert "attempt 2: wait 1.0s" in out
    assert "attempt 3: wait 2.0s" in out


def test_dry_run_with_one_try_plans_no_retries(capsys):
    assert main(["--dry-run", "--tries", "1", "false"]) == 0
    assert "no retries planned" in capsys.readouterr().out


def test_bad_flag_returns_exit_two(capsys):
    assert main(["--tries", "0", "true"]) == 2
    assert "tries" in capsys.readouterr().err


def test_missing_command_returns_exit_two(capsys):
    assert main([]) == 2


def test_unknown_command_returns_127(capsys):
    assert main(["definitely-not-a-real-program-xyz"]) == 127
    assert "not found" in capsys.readouterr().err


def _run_real_cli(args):
    """Run the real `retryrun` module in a subprocess (end-to-end check)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC_DIR + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "retryrun.cli", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def test_end_to_end_success_returns_zero():
    proc = _run_real_cli(["--tries", "3", "true"])
    assert proc.returncode == 0


def test_end_to_end_failure_returns_last_code():
    proc = _run_real_cli(["--tries", "2", "--delay", "0.1", "false"])
    assert proc.returncode == 1
    assert "attempt 1/2" in proc.stderr
    assert "giving up" in proc.stderr


def test_end_to_end_flaky_script_eventually_passes(tmp_path):
    script = tmp_path / "flaky.sh"
    counter = tmp_path / "count"
    script.write_text(
        "#!/bin/sh\n"
        f"n=$(cat {counter} 2>/dev/null || echo 0)\n"
        f"echo $((n + 1)) > {counter}\n"
        "test $n -ge 2\n"
    )
    script.chmod(0o755)
    proc = _run_real_cli(["--tries", "4", "--delay", "0.1", str(script)])
    assert proc.returncode == 0
    assert counter.read_text().strip() == "3"


def test_end_to_end_timeout_kills_slow_command():
    proc = _run_real_cli(["--tries", "1", "--timeout", "0.5", "sleep", "10"])
    assert proc.returncode == 124
