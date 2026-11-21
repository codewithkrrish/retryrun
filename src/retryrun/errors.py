"""Errors raised by retryrun.

Each one carries a human-readable message and the exit code the CLI
should return, so the entry point never has to guess.
"""


class RetryRunError(Exception):
    """Base error for retryrun. Carries the exit code to return."""

    exit_code: int = 1

    def __init__(self, message: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class CommandNotFoundError(RetryRunError):
    """The command to run does not exist (or is not executable)."""

    exit_code = 127


class InvalidOptionError(RetryRunError):
    """A flag or option value does not make sense."""

    exit_code = 2
