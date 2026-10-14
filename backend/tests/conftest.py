import json
import uuid

import pytest
from django.core.management import call_command

from access_control.identity.management.commands.load_demo_data import uid
from orchestration.task_queue import registry
from tests import stub_agents

STUB_REGISTRY = {agent_id: f"tests.stub_agents.{cls.__name__}" for agent_id, cls in stub_agents.STUBS.items()}


def pytest_configure(config):
    from django.conf import settings

    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Demo data is loaded once; every test runs in a transaction that is rolled back."""
    with django_db_blocker.unblock():
        call_command("load_demo_data", verbosity=0)


@pytest.fixture(autouse=True)
def _defaults(settings):
    settings.AGENT_TASK_EXECUTION = "inline"
    settings.LLM_PROVIDER = "fake"
    registry.reset_caches()
    yield
    registry.reset_caches()


@pytest.fixture
def stubs(settings):
    """Register test-double agents. Tests set behaviour per task type: stubs["x.y"] = handler."""
    settings.AGENT_REGISTRY = dict(STUB_REGISTRY)
    registry.reset_caches()
    stub_agents.BEHAVIOUR.clear()
    yield stub_agents.BEHAVIOUR
    stub_agents.BEHAVIOUR.clear()


class Api:
    def __init__(self, client):
        self.client = client
        self.headers: dict = {}

    def login(self, email: str, password: str = "demo1238") -> "Api":
        response = self.post("/auth/login", {"email": email, "password": password})
        assert response.status_code == 200, response.content
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {response.json()['session']}"}
        return self

    def get(self, path: str, **params):
        return self.client.get(f"/api/v1{path}", params, **self.headers)

    def post(self, path: str, body: dict | None = None):
        return self.client.post(f"/api/v1{path}", json.dumps(body or {}), content_type="application/json", **self.headers)

    def patch(self, path: str, body: dict):
        return self.client.patch(f"/api/v1{path}", json.dumps(body), content_type="application/json", **self.headers)


@pytest.fixture
def api(client, db):
    return Api(client)


@pytest.fixture
def ivy(client, db):
    return Api(client).login("ivy.lin@example.com")


@pytest.fixture
def emily(db):
    from django.test import Client

    return Api(Client()).login("emily.walker@example.com")


@pytest.fixture
def alex(db):
    from django.test import Client

    return Api(Client()).login("alex.hu@example.com")


def key(name: str) -> str:
    """Deterministic id of a fixture record, e.g. key("student-ivy")."""
    return str(uid(name))


def new_uuid() -> str:
    return str(uuid.uuid4())
