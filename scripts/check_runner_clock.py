"""Run a check while observing wall-clock steps; never adjusts host time or token policy."""

import argparse
import json
import subprocess
import threading
import time


def clock_summary(steps):
    return {
        "clock_samples": len(steps),
        "minimum_wall_step_seconds": round(min(steps, default=0), 6),
        "maximum_wall_step_seconds": round(max(steps, default=0), 6),
        "clock_stable": bool(steps) and all(abs(step) < 0.05 for step in steps),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Supply a check command after --")
    stopped = threading.Event()
    steps = []

    def observe():
        previous = None
        while not stopped.is_set():
            before = time.monotonic()
            wall = time.time()
            after = time.monotonic()
            # Exclude ambiguous samples if this tiny clock read was descheduled.
            if after - before <= 0.02:
                sample = ((before + after) / 2, wall)
                if previous:
                    steps.append((sample[1] - previous[1]) - (sample[0] - previous[0]))
                previous = sample
            stopped.wait(0.1)

    monitor = threading.Thread(target=observe, daemon=True)
    monitor.start()
    try:
        result = subprocess.run(command, check=False)
    finally:
        stopped.set()
        monitor.join()
    summary = clock_summary(steps)
    print(json.dumps(summary), flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
    if not summary["clock_stable"]:
        raise SystemExit(
            "Runner clock instability detected; repeat checks on a stable host"
        )


if __name__ == "__main__":
    main()
