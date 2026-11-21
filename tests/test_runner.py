"""Tests for the runner, using a fake executor so no real process spawns."""

from retryrun.runner import AttemptResult, RetryConfig, run_with_retries


def _scripted(codes):
    """Fake executor: returns the given exit codes in order, then 0."""
    calls = {"n": 0}

    def execute(command, timeout):
        index = calls["n"]
        calls["n"] += 1
        code = codes[index] if index < len(codes) else 0
        return AttemptResult(exit_code=code)

    return execute, calls


def _no_sleep():
    slept = []

    def sleep(seconds):
        slept.append(seconds)

    return sleep, slept


def test_success_on_first_try_never_sleeps():
    execute, calls = _scripted([0])
    sleep, slept = _no_sleep()
    result = run_with_retries(RetryConfig(command=["true"]), execute, sleep)
    assert result.succeeded and result.attempts == 1 and result.exit_code == 0
    assert slept == [] and calls["n"] == 1


def test_success_after_failures_retries_with_backoff():
    execute, calls = _scripted([1, 1, 0])
    sleep, slept = _no_sleep()
    result = run_with_retries(
        RetryConfig(command=["flaky"], tries=5, delay=1.0, backoff=2.0),
        execute,
        sleep,
    )
    assert result.succeeded and result.attempts == 3
    assert slept == [1.0, 2.0]
    assert calls["n"] == 3


def test_exhausted_retries_returns_last_exit_code():
    execute, _ = _scripted([3, 3, 3, 3])
    sleep, slept = _no_sleep()
    result = run_with_retries(
        RetryConfig(command=["nope"], tries=3, delay=1.0, backoff=2.0),
        execute,
        sleep,
    )
    assert not result.succeeded
    assert result.attempts == 3 and result.exit_code == 3
    assert slept == [1.0, 2.0]


def test_only_on_stops_on_unlisted_code():
    execute, calls = _scripted([2, 1, 0])
    sleep, slept = _no_sleep()
    result = run_with_retries(
        RetryConfig(command=["x"], tries=5, only_on=frozenset({1})),
        execute,
        sleep,
    )
    # Exit 2 is not in --only-on, so it returns immediately.
    assert result.exit_code == 2 and result.attempts == 1
    assert slept == [] and calls["n"] == 1


def test_only_on_retries_listed_code():
    execute, _ = _scripted([1, 1, 0])
    sleep, slept = _no_sleep()
    result = run_with_retries(
        RetryConfig(command=["x"], tries=3, only_on=frozenset({1})),
        execute,
        sleep,
    )
    assert result.succeeded and result.attempts == 3


def test_timeout_counts_as_failure_and_is_retried():
    def execute(command, timeout):
        return AttemptResult(exit_code=124, timed_out=True)

    sleep, slept = _no_sleep()
    result = run_with_retries(
        RetryConfig(command=["slow"], tries=2, delay=0.5), execute, sleep
    )
    assert not result.succeeded and result.exit_code == 124
    assert result.attempts == 2 and slept == [0.5]


def test_progress_messages_go_to_log():
    execute, _ = _scripted([1, 0])
    messages = []
    result = run_with_retries(
        RetryConfig(command=["x"], tries=2), execute, lambda s: None, messages.append
    )
    assert result.succeeded
    assert len(messages) == 2
    assert "attempt 1/2" in messages[0] and "retrying" in messages[0]
    assert "succeeded" in messages[1]


def test_quiet_suppresses_progress_messages():
    execute, _ = _scripted([1, 0])
    messages = []
    result = run_with_retries(
        RetryConfig(command=["x"], tries=2, quiet=True),
        execute,
        lambda s: None,
        messages.append,
    )
    assert result.succeeded and messages == []
