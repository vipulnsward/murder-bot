import time

import fast_screenshot
import watchdog
from scheduler import Scheduler, Task

DEV = "127.0.0.1:5555"

# 1) confirm the default recovery path is wired (without executing a force-stop)
import auto_refill
print("default-recover wiring: auto_refill.app_refresh callable =", callable(auto_refill.app_refresh))

# 2) live integration: scheduler drives a fast screenshot + watchdog health check
wd = watchdog.Watchdog(DEV, fail_threshold=3, grab_fn=lambda: fast_screenshot.grab(DEV),
                       recover_fn=lambda: (print("   [recover would run app_refresh]") or True))
counters = {"screens": 0, "health_ok": 0, "dash": 0, "latency_sum": 0.0}


def screenshot_health():
    t = time.perf_counter()
    img = fast_screenshot.grab(DEV)
    counters["latency_sum"] += time.perf_counter() - t
    counters["screens"] += 1
    running = watchdog.is_app_running(DEV)
    state = wd.observe(img, app_running=running)
    if state == "ok":
        counters["health_ok"] += 1
    elif state == "RECOVER":
        wd.recover()
    print(f"   t+{time.time()-start:4.1f}s  screenshot+health -> {state}")


def dashboard():
    counters["dash"] += 1
    print(f"   t+{time.time()-start:4.1f}s  [dashboard refresh tick]")


sched = Scheduler()
sched.add(Task("screenshot_health", screenshot_health, interval=2.0, priority=5))
sched.add(Task("dashboard", dashboard, interval=5.0, priority=20))

start = time.time()
print("running scheduler live for ~15s (screenshot/health @2s, dashboard @5s)...")
while time.time() - start < 15:
    ran = sched.run_due()
    if ran is None:
        nxt = sched.seconds_until_next()
        time.sleep(min(nxt if nxt else 0.1, 0.5))

n = counters["screens"] or 1
print("--- results ---")
print(f"screenshots={counters['screens']}  avg_latency={counters['latency_sum']/n*1000:.0f}ms  "
      f"health_ok={counters['health_ok']}/{counters['screens']}  dashboard_ticks={counters['dash']}")
ok = counters["screens"] >= 6 and counters["health_ok"] == counters["screens"] and counters["dash"] >= 2
print("INTEGRATION TEST:", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
