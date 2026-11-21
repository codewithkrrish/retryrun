"""Command-line entry point for retryrun.

Thin by design: parse flags, validate them, hand a RetryConfig to the
runner, and translate the result into an exit code. No retry logic
lives here — that is `runner.py`'s job, and it is tested on its own.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .errors import InvalidOptionError, RetryRunError
from .runner import RetryConfig, run_with_retries
from .schedule import plan

DEFAULT_TRIES = 3
DEFAULT_DELAY = 1.0
DEFAULT_BACKOFF = 2.0


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, kept separate so tests can drive it directly."""
    parser = argparse.ArgumentParser(
        prog="retryrun",
        description=(
            "Run a command, retrying it with exponential backoff until it "
            "succeeds or runs out of tries."
        ),
        epilog=(
            "Examples:\n"
            "  retryrun --tries 5 --delay 2 curl https://example.com\n"
            "  retryrun --only-on 1,2 --timeout 30 ./deploy.sh\n"
            "  retryrun --dry-run --tries 4 --delay 1 --backoff 3 ./flaky.sh"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--tries",
        type=int,
        default=DEFAULT_TRIES,
        help=f"total attempts, including the first (default: {DEFAULT_TRIES})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"seconds before the first retry (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=DEFAULT_BACKOFF,
        help=f"multiplier applied to each wait (default: {DEFAULT_BACKOFF})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="kill each attempt after this many seconds (exit 124 on timeout)",
    )
    parser.add_argument(
        "--only-on",
        default=None,
        metavar="CODES",
        help="comma-separated exit codes worth retrying, e.g. '1,2,124'; "
        "any other failure returns immediately",
    )
    parser.add_argument(
        "--jitter",
        action="store_true",
        help="add up to 25%% random extra wait so retries don't stampede",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print the command's own output, no retry progress",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show the retry schedule and exit without running anything",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="the command to run, e.g. curl https://example.com",
    )
    return parser


def parse_only_on(raw: str | None) -> frozenset[int] | None:
    """Parse '--only-on 1,2' into a set of exit codes, or None."""
    if raw is None:
        return None
    try:
        codes = frozenset(int(part.strip()) for part in raw.split(",") if part.strip())
    except ValueError:
        raise InvalidOptionError(
            f"retryrun: --only-on expects comma-separated numbers, got {raw!r}"
        ) from None
    if not codes:
        raise InvalidOptionError("retryrun: --only-on needs at least one exit code")
    return codes


def build_config(args: argparse.Namespace) -> RetryConfig:
    """Validate parsed flags and build the runner config."""
    if args.tries < 1:
        raise InvalidOptionError(
            f"retryrun: --tries must be at least 1, got {args.tries}"
        )
    if args.delay < 0:
        raise InvalidOptionError(
            f"retryrun: --delay cannot be negative, got {args.delay}"
        )
    if args.backoff < 1:
        raise InvalidOptionError(
            f"retryrun: --backoff must be 1 or more, got {args.backoff}"
        )
    if args.timeout is not None and args.timeout <= 0:
        raise InvalidOptionError(
            f"retryrun: --timeout must be positive, got {args.timeout}"
        )
    if not args.command:
        raise InvalidOptionError(
            "retryrun: no command given — put the command after the flags, "
            "e.g. retryrun --tries 3 curl https://example.com"
        )
    # argparse.REMAINDER keeps a leading '--' if the user typed one to
    # separate flags from the command; drop it.
    command = args.command[1:] if args.command[0] == "--" else args.command
    if not command:
        raise InvalidOptionError("retryrun: no command given after '--'")

    return RetryConfig(
        command=command,
        tries=args.tries,
        delay=args.delay,
        backoff=args.backoff,
        timeout=args.timeout,
        only_on=parse_only_on(args.only_on),
        jitter=args.jitter,
        quiet=args.quiet,
    )


def _print_dry_run(config: RetryConfig) -> None:
    waits = plan(config.tries, config.delay, config.backoff)
    print(f"command: {' '.join(config.command)}")
    print(f"attempts: {config.tries}")
    if config.timeout is not None:
        print(f"per-attempt timeout: {config.timeout:g}s")
    if config.only_on is not None:
        print(f"retry only on exit codes: {', '.join(str(c) for c in sorted(config.only_on))}")
    if not waits:
        print("no retries planned — runs once.")
        return
    for i, wait in enumerate(waits, start=2):
        print(f"attempt {i}: wait {wait:.1f}s before running")
    print(f"longest possible run: about {sum(waits):.1f}s of waiting")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        config = build_config(args)
    except RetryRunError as exc:
        print(exc, file=sys.stderr)
        return exc.exit_code

    if args.dry_run:
        _print_dry_run(config)
        return 0

    def _log(message: str) -> None:
        print(f"retryrun: {message}", file=sys.stderr)

    try:
        result = run_with_retries(config, log=_log)
    except RetryRunError as exc:
        print(exc, file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("retryrun: interrupted, stopping", file=sys.stderr)
        return 130
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
