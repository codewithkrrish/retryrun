"""The retry schedule: how long to wait before each attempt.

Kept separate from the runner so the maths is easy to test on its own.
The delay before attempt N (1-based) is::

    delay * backoff ** (N - 2)          # attempt 2 waits `delay`

so the first retry waits exactly `delay` seconds, then each wait grows
by the backoff multiplier. Jitter, when on, adds up to 25% extra so a
fleet of retrying processes does not stampede in lockstep.
"""

import random

MAX_DELAY_SECONDS = 3600.0  # one hour; nobody needs a longer single wait
JITTER_FRACTION = 0.25


def delay_before_attempt(
    attempt: int,
    delay: float,
    backoff: float,
    jitter: bool = False,
) -> float:
    """Seconds to wait before `attempt` (attempt 1 runs immediately).

    `attempt` is 1-based. Attempt 1 returns 0.0; attempt 2 returns
    `delay`; later attempts multiply by `backoff` each time.
    """
    if attempt <= 1:
        return 0.0
    wait = delay * (backoff ** (attempt - 2))
    if jitter:
        wait *= 1.0 + random.uniform(0.0, JITTER_FRACTION)
    return min(wait, MAX_DELAY_SECONDS)


def plan(tries: int, delay: float, backoff: float) -> list[float]:
    """The full wait list: one entry per retry, in seconds.

    E.g. plan(3, 1.0, 2.0) == [1.0, 2.0] — wait 1s, then 2s.
    """
    return [delay_before_attempt(n, delay, backoff) for n in range(2, tries + 1)]
