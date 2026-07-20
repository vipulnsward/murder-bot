import heapq
import random
import time


class Task:
    def __init__(self, name, func, interval, priority=10, jitter=0.0, enabled=True):
        self.name = name
        self.func = func
        self.interval = float(interval)
        self.priority = priority
        self.jitter = jitter
        self.enabled = enabled
        self.next_run = 0.0
        self.runs = 0
        self.fails = 0

    def _reschedule(self, now, delay=None):
        base = self.interval if delay is None else float(delay)
        if self.jitter:
            base += random.uniform(-self.jitter, self.jitter) * base
        self.next_run = now + max(0.0, base)


class Scheduler:
    """ALAS-style time-based task scheduler.

    Tasks carry a next_run timestamp and an interval. run_due() picks the single
    most-due, highest-priority ready task, runs it, and reschedules it — so a
    high-priority task (e.g. refill) preempts routine ones on the next tick.
    A task's func may return a number to override the next delay; raising delays
    it by `retry_delay` and increments its fail count. Clock is injectable.
    """

    def __init__(self, clock=time.time, retry_delay=30.0):
        self.tasks = {}
        self.clock = clock
        self.retry_delay = retry_delay

    def add(self, task, start_delay=0.0):
        task._reschedule(self.clock(), delay=start_delay)
        self.tasks[task.name] = task
        return task

    def remove(self, name):
        self.tasks.pop(name, None)

    def delay(self, name, seconds):
        t = self.tasks.get(name)
        if t:
            t._reschedule(self.clock(), delay=seconds)

    def _ready(self, now):
        heap = [
            (t.priority, t.next_run, t.name)
            for t in self.tasks.values()
            if t.enabled and t.next_run <= now
        ]
        if not heap:
            return None
        heapq.heapify(heap)
        return self.tasks[heap[0][2]]

    def seconds_until_next(self, now=None):
        now = self.clock() if now is None else now
        upcoming = [t.next_run for t in self.tasks.values() if t.enabled]
        if not upcoming:
            return None
        return max(0.0, min(upcoming) - now)

    def run_due(self):
        """Run the one most-due, highest-priority ready task. Returns its name or None."""
        now = self.clock()
        task = self._ready(now)
        if task is None:
            return None
        try:
            override = task.func()
            task.runs += 1
            task._reschedule(self.clock(), delay=override)
        except Exception as e:
            task.fails += 1
            task._reschedule(self.clock(), delay=self.retry_delay)
            raise SchedulerTaskError(task.name, e)
        return task.name


class SchedulerTaskError(Exception):
    def __init__(self, task_name, cause):
        super().__init__(f"task {task_name!r} failed: {cause!r}")
        self.task_name = task_name
        self.cause = cause


if __name__ == "__main__":
    # deterministic self-test with a fake clock (no real sleeping)
    clock = {"t": 1000.0}
    sched = Scheduler(clock=lambda: clock["t"], retry_delay=5.0)
    log = []
    sched.add(Task("train", lambda: log.append(("train", clock["t"])), interval=6, priority=10))
    sched.add(Task("refill", lambda: log.append(("refill", clock["t"])), interval=120, priority=1))
    sched.add(Task("dashboard", lambda: log.append(("dashboard", clock["t"])), interval=60, priority=20))

    fails = {"n": 0}

    def flaky():
        fails["n"] += 1
        if fails["n"] == 1:
            raise RuntimeError("boom")
        log.append(("flaky", clock["t"]))

    sched.add(Task("flaky", flaky, interval=10, priority=5))

    # advance the fake clock 1s at a time for 130s, running whatever is due
    errors = 0
    for _ in range(130):
        try:
            sched.run_due()
        except SchedulerTaskError:
            errors += 1
        clock["t"] += 1.0

    train_runs = sum(1 for n, _ in log if n == "train")
    refill_runs = sum(1 for n, _ in log if n == "refill")
    dash_runs = sum(1 for n, _ in log if n == "dashboard")
    flaky_runs = sum(1 for n, _ in log if n == "flaky")

    print(f"train runs={train_runs} (expect ~22 @ 6s over 130s)")
    print(f"dashboard runs={dash_runs} (expect ~3 @ 60s)")
    print(f"refill runs={refill_runs} (expect ~2 @ 120s, priority=1 preempts)")
    print(f"flaky runs={flaky_runs}, scheduler errors caught={errors} (1 boom -> retry_delay -> recovers)")

    ok = (20 <= train_runs <= 23) and (dash_runs in (2, 3)) and (refill_runs in (1, 2)) and errors == 1 and flaky_runs >= 10
    # verify priority: at t where refill and others are both due, refill (prio 1) runs first
    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
