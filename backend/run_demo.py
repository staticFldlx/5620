"""One-command demo start (spec 8.10). Python only, no Docker; works on Windows and macOS.

    python run_demo.py [--host 127.0.0.1] [--port 8000]

Runs migrate -> load_demo_data -> ingest_materials (when RETRIEVAL_BACKEND is not none),
then starts runserver, plus run_agent_worker when AGENT_TASK_EXECUTION=worker.
Ctrl+C stops everything.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def manage(*args: str) -> list[str]:
    return [sys.executable, str(BASE_DIR / "manage.py"), *args]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8000")
    options = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(BASE_DIR))
    import django
    from django.conf import settings

    django.setup()

    subprocess.run(manage("migrate", "--noinput"), check=True)
    subprocess.run(manage("load_demo_data"), check=True)
    if settings.RETRIEVAL_BACKEND != "none":
        subprocess.run(manage("ingest_materials"), check=True)

    processes = [subprocess.Popen(manage("runserver", f"{options.host}:{options.port}"))]
    if settings.AGENT_TASK_EXECUTION == "worker":
        processes.append(subprocess.Popen(manage("run_agent_worker")))
    print(f"LingoPath API on http://{options.host}:{options.port}/api/v1/docs  (mode: {settings.AGENT_TASK_EXECUTION}, LLM: {settings.LLM_PROVIDER})")
    try:
        for process in processes:
            process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
