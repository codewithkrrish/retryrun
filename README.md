# retryrun

Retry a flaky command until it works — with exponential backoff, per-attempt timeouts, and a dry-run so you can see the plan before anything runs.

I kept writing the same `for i in 1 2 3; do ... sleep ...; done` loop in shell scripts, and every copy drifted: one forgot to stop retrying usage errors, another slept a fixed 5 seconds forever, a third swallowed the real exit code. So I pulled the loop out into one small tool and stopped re-solving it.

## What it does

```
$ retryrun --tries 5 --delay 2 curl https://example.com
retryrun: attempt 1/5 exited with 7; retrying in 2.0s
retryrun: attempt 2/5 exited with 7; retrying in 4.0s
retryrun: attempt 3/5 succeeded
```

- Waits grow by the backoff multiplier: `--delay 1 --backoff 2` waits 1s, 2s, 4s, 8s…
- `--only-on 1,2` retries just those exit codes. Anything else fails fast — no point retrying a bad flag five times.
- `--timeout 30` kills each attempt after 30 seconds (reports exit code 124, like GNU timeout).
- `--jitter` adds a little random spread so a fleet of retrying jobs doesn't hammer the same service in lockstep.
- `--dry-run` prints the schedule and exits without running anything.
- Exit code is the command's own exit code, so it drops into scripts and CI unchanged.

## Install

Needs Python 3.9 or newer. No third-party dependencies.

```bash
pip install git+https://github.com/codewithkrrish/retryrun.git
```

Or clone it and run it from the source tree:

```bash
git clone https://github.com/codewithkrrish/retryrun.git
cd retryrun
pip install -e .
```

## Usage

```bash
# the basics — try up to 5 times, first wait 2s, doubling after that
retryrun --tries 5 --delay 2 ./deploy.sh

# only retry on connection errors (curl 7) and timeouts (28)
retryrun --only-on 7,28 --timeout 30 curl https://api.example.com/health

# preview the schedule before committing to it
retryrun --dry-run --tries 4 --delay 1 --backoff 3 ./flaky.sh
# command: ./flaky.sh
# attempts: 4
# attempt 2: wait 1.0s before running
# attempt 3: wait 3.0s before running
# attempt 4: wait 9.0s before running
# longest possible run: about 13.0s of waiting

# quiet mode — only the command's own output, no retry chatter
retryrun --quiet --tries 3 ./backup.sh
```

Full list of flags: `retryrun --help`.

## Why not just a shell loop?

A shell loop works fine until it doesn't. The things I kept getting wrong:

- Retrying exit codes that will never succeed (bad arguments, missing files).
- Fixed sleeps that either wait too long on quick blips or too little on real outages.
- Losing the real exit code — `set -e` scripts need the command's code, not the loop's.
- No timeout, so one hung attempt stalls the whole job.

retryrun is that loop, done once, with tests. If your retry needs are fancier — per-attempt hooks, circuit breakers, backoff strategies beyond exponential — this is the wrong tool. It's deliberately small.

## Project structure

```
retryrun/
├── src/retryrun/
│   ├── cli.py       # flag parsing and exit codes, nothing else
│   ├── runner.py    # the retry loop (testable without spawning processes)
│   ├── schedule.py  # backoff maths: delay_before_attempt, plan
│   └── errors.py    # typed errors carrying their exit code
├── tests/
│   ├── test_schedule.py
│   ├── test_runner.py
│   └── test_cli.py
└── pyproject.toml
```

Run the tests with `python -m pytest` (28 tests, no network, no real commands except `true`/`false`/`sleep` in the end-to-end ones).

## Limitations

- Retries are for transient failures. If a command fails deterministically, retryrun just fails slower — check `--only-on` first.
- A single wait is capped at one hour; beyond that, a retry loop is the wrong answer and a scheduler is the right one.
- It doesn't stream or capture the command's output — output goes straight to your terminal, exactly as if you ran the command yourself.

## License

MIT — see [LICENSE](LICENSE).

## Author

[Krrish](https://github.com/codewithkrrish) — I build small tools I actually use, mostly Python CLIs and Discord stuff.
