"""Tests for the retry schedule maths."""

from retryrun.schedule import MAX_DELAY_SECONDS, delay_before_attempt, plan


def test_first_attempt_runs_immediately():
    assert delay_before_attempt(1, 1.0, 2.0) == 0.0


def test_second_attempt_waits_exactly_delay():
    assert delay_before_attempt(2, 1.5, 2.0) == 1.5


def test_backoff_multiplies_each_wait():
    assert delay_before_attempt(3, 1.0, 2.0) == 2.0
    assert delay_before_attempt(4, 1.0, 2.0) == 4.0
    assert delay_before_attempt(5, 1.0, 3.0) == 27.0


def test_backoff_of_one_is_flat():
    assert delay_before_attempt(4, 2.0, 1.0) == 2.0


def test_plan_lists_one_wait_per_retry():
    assert plan(1, 1.0, 2.0) == []
    assert plan(3, 1.0, 2.0) == [1.0, 2.0]
    assert plan(4, 0.5, 3.0) == [0.5, 1.5, 4.5]


def test_wait_is_capped():
    assert delay_before_attempt(40, 60.0, 2.0) == MAX_DELAY_SECONDS


def test_jitter_only_adds_wait():
    base = delay_before_attempt(3, 1.0, 2.0)
    for _ in range(20):
        waited = delay_before_attempt(3, 1.0, 2.0, jitter=True)
        assert base <= waited <= base * 1.25
