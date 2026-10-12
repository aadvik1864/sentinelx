"""Detect local wall-clock steps without adjusting time or relaxing JWT/TOTP validation."""

import threading
import time


class ClockGuard:
    def __init__(self):
        self.previous = None
        self.stable = True
        self.samples = 0
        self.last_monotonic = None
        self.stop_event = threading.Event()
        self.thread = None

    def observe(self, monotonic, wall):
        if self.previous:
            step = (wall - self.previous[1]) - (monotonic - self.previous[0])
            if abs(step) >= 0.05:
                self.stable = (
                    False  # Latched until a deliberate process restart after investigation.
                )
        self.previous = (monotonic, wall)
        self.last_monotonic = monotonic
        self.samples += 1

    def healthy(self):
        return (
            self.stable
            and self.samples >= 2
            and self.last_monotonic is not None
            and time.monotonic() - self.last_monotonic < 2
        )

    def start(self):
        self.stop_event.clear()
        self.previous, self.stable, self.samples = None, True, 0

        def monitor():
            while not self.stop_event.is_set():
                before, wall, after = time.monotonic(), time.time(), time.monotonic()
                if after - before <= 0.02:
                    self.observe((before + after) / 2, wall)
                self.stop_event.wait(0.1)

        self.thread = threading.Thread(target=monitor, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)


clock_guard = ClockGuard()
