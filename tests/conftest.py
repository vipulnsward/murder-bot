import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "neo_app"))
os.environ.setdefault(
    "COUNTER_AI_SIM_JS",
    "/private/tmp/claude-501/-Users-sward-work-scratch/"
    "c2e71639-9f51-4ec5-b5ef-685684771afc/scratchpad/evony-battle-simulator/js",
)


def _db_up():
    try:
        import psycopg2
        psycopg2.connect(dbname="murderbot").close()
        return True
    except Exception:
        return False


DB_UP = _db_up()
