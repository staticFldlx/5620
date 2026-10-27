"""Start the API and its single monitoring process; stop all children together."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

BASE_DIR = Path(__file__).resolve().parent


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    from django.conf import settings
    django.setup()
    commands = [
        [sys.executable, "-m", "gunicorn", "config.wsgi:application", "--bind", f"0.0.0.0:{os.environ.get('PORT', '8000')}", "--workers", "1", "--threads", "8", "--timeout", "120"],
        [sys.executable, "manage.py", "monitor_agents", "--interval", "60"],
    ]
    if settings.AGENT_TASK_EXECUTION == "worker":
        commands.append([sys.executable, "manage.py", "run_agent_worker"])
    processes = []
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for command in commands:
            processes.append(subprocess.Popen(command, cwd=BASE_DIR))
        while all(process.poll() is None for process in processes):
            time.sleep(.25)
        return next((process.returncode for process in processes if process.returncode), 1)
    except KeyboardInterrupt:
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
