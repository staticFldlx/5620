"""Disposable backend for browser regression tests; never uses the developer's DB/key."""
from pathlib import Path
import os
import signal
import subprocess
import sys
import tempfile
import time

backend = Path(__file__).resolve().parents[2] / 'backend'

def interrupt(*_):
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, interrupt)
with tempfile.TemporaryDirectory(prefix='lingopath-browser-') as directory:
    env = {**os.environ, 'DATABASE_PATH': str(Path(directory) / 'test.sqlite3'), 'DATABASE_URL': '',
           'LLM_PROVIDER': 'fake', 'LLM_API_KEY': '', 'DJANGO_DEBUG': 'true', 'DJANGO_SECRET_KEY': 'isolated-browser-test',
           'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1', 'CORS_ALLOWED_ORIGINS': 'http://127.0.0.1:5274',
           'AGENT_TASK_EXECUTION': os.environ.get('AGENT_TASK_EXECUTION', 'inline'), 'LOG_LEVEL': 'WARNING'}
    children = []
    try:
        for command in (['migrate','--noinput'], ['load_demo_data']):
            subprocess.run([sys.executable, 'manage.py', *command], cwd=backend, env=env, check=True)
        if env.get('E2E_PROGRESS_SCENARIOS') == 'true':
            subprocess.run([sys.executable, str(Path(__file__).with_name('progress_seed.py'))], cwd=backend, env=env, check=True)
        children.append(subprocess.Popen([sys.executable, 'manage.py','runserver','127.0.0.1:8101','--noreload'], cwd=backend, env=env))
        if env['AGENT_TASK_EXECUTION'] == 'worker':
            children.append(subprocess.Popen([sys.executable,'manage.py','run_agent_worker'], cwd=backend, env=env))
        while all(child.poll() is None for child in children): time.sleep(.2)
        raise SystemExit(next((child.returncode for child in children if child.returncode), 1))
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None: child.terminate()
        for child in children:
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
