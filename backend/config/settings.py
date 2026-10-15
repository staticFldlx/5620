"""Django settings. Every value comes from the environment (see .env.example).

A minimal .env loader is included so the project needs no python-dotenv.
Variables already present in the process environment take precedence.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = env("DJANGO_SECRET_KEY") or ("dev-only-insecure-key" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "access_control.identity",
    "domain.learning",
    "domain.governance",
    "orchestration.task_queue",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "access_control.gateway.middleware.RequestIdMiddleware",
    "access_control.gateway.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
# Bearer-token API without cookies, so no CSRF middleware (deviation A2).
SILENCED_SYSTEM_CHECKS = ["security.W003"]
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # TLS ends at the cloud load balancer
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "3600"))

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES: list = []


def _database() -> dict:
    url = env("DATABASE_URL")
    if url.startswith(("postgres://", "postgresql://")):
        parsed = urlparse(url)
        return {
            "ENGINE": "django.db.backends.postgresql",  # requires psycopg, not installed by default
            "NAME": parsed.path.lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
        }
    path = Path(env("DATABASE_PATH", "db.sqlite3"))
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": path if path.is_absolute() else BASE_DIR / path,
    }


DATABASES = {"default": _database()}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "identity.User"

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

MEDIA_ROOT = BASE_DIR / env("MEDIA_ROOT", "media")
MEDIA_URL = "/media/"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "infrastructure.monitoring.JsonFormatter"}},
    "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "json"}},
    "loggers": {"lingopath": {"handlers": ["stdout"], "level": env("LOG_LEVEL", "INFO"), "propagate": False}},
}

# --- Access control -------------------------------------------------------
AUTH_TOKEN_MAX_AGE = int(env("AUTH_TOKEN_MAX_AGE", str(7 * 24 * 3600)))
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
WORKSPACE_LIST_LIMIT = int(env("WORKSPACE_LIST_LIMIT", "50"))
# Learning reviews for a student without a teacher go to this teacher (deviation from spec 5.4, see docs).
INTAKE_TEACHER_EMAIL = env("INTAKE_TEACHER_EMAIL", "emily.walker@example.com")

# --- LLM ------------------------------------------------------------------
LLM_PROVIDER = env("LLM_PROVIDER", "fake")  # openai | school (alias) | fake
LLM_BASE_URL = env("LLM_BASE_URL")
LLM_API_KEY = env("LLM_API_KEY")
LLM_MODEL_FAST = env("LLM_MODEL_FAST")
LLM_MODEL_DEFAULT = env("LLM_MODEL_DEFAULT")
LLM_TIMEOUT_SECONDS = float(env("LLM_TIMEOUT_SECONDS", "30"))
LLM_CAPABILITIES = env_list("LLM_CAPABILITIES", "tools,json_schema")

# --- Retrieval ------------------------------------------------------------
RETRIEVAL_BACKEND = env("RETRIEVAL_BACKEND", "none")  # none | keyword | vector
EMBEDDING_BACKEND = env("EMBEDDING_BACKEND")

# --- Orchestration --------------------------------------------------------
AGENT_TASK_EXECUTION = env("AGENT_TASK_EXECUTION", "inline")  # inline | worker
TASK_TIMEOUT_SECONDS = int(env("TASK_TIMEOUT_SECONDS", "120"))
TASK_MAX_ATTEMPTS = int(env("TASK_MAX_ATTEMPTS", "2"))
MAX_HOPS_PER_REQUEST = 6
AGENT_CONFIDENCE_THRESHOLD = float(env("AGENT_CONFIDENCE_THRESHOLD", "0.70"))  # the only threshold

# --- Agent options ----------------------------------------------------------
# Teaching Assistant: "single" = one structured call per question (default, fits the 10 s frontend timeout);
# "loop" = tool loop that falls back to a single call when it runs out of steps or time.
TEACHING_SUPPORT_EXPLAIN_MODE = env("TEACHING_SUPPORT_EXPLAIN_MODE", "single")
if TEACHING_SUPPORT_EXPLAIN_MODE not in ("single", "loop"):
    raise RuntimeError("TEACHING_SUPPORT_EXPLAIN_MODE must be single or loop")
TEACHING_SUPPORT_LOOP_BUDGET_SECONDS = float(env("TEACHING_SUPPORT_LOOP_BUDGET_SECONDS", "6"))

AGENT_REGISTRY = {
    "coordinator": "orchestration.coordinator.agent.CoordinatorAgent",
    "assessment": "agents.assessment.agent.AssessmentAgent",
    "planning": "agents.planning.agent.PlanningAgent",
    "teaching_support": "agents.teaching_support.agent.TeachingSupportAgent",
    "tech_operations": "agents.tech_operations.agent.TechOperationsAgent",
}
