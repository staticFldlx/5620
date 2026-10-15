"""Layer rules (spec 8.3, Fig 24), checked with ast instead of an extra import-linter dependency.

access_control -> orchestration -> agents -> domain, imports only point downwards;
agents never import each other; agents.runtime imports no Django or domain code;
only infrastructure touches external SDKs and HTTP clients.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERNAL = ("access_control", "orchestration", "agents", "domain", "infrastructure", "config", "tests")
AGENT_PACKAGES = ("assessment", "planning", "teaching_support", "tech_operations")
NETWORK_MODULES = ("urllib.request", "http.client", "requests", "httpx", "openai", "anthropic")


def module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = module_name(path) if path.name == "__init__.py" else module_name(path).rpartition(".")[0]
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                module = ".".join(base[: len(base) - (node.level - 1)] + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            # record full names so "from domain.learning import selectors" is judged as domain.learning.selectors
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def allowed(source: str, target: str) -> bool:
    top = target.split(".")[0]
    if source.startswith("agents.runtime"):
        if top in ("django", "domain", "orchestration", "access_control"):
            return False
        return top not in INTERNAL or target.startswith(("agents.runtime", "infrastructure.llm"))
    if source.startswith("agents."):
        own = source.split(".")[1]
        if top not in INTERNAL:
            return True
        if target.startswith("agents."):
            return target.startswith(("agents.runtime", f"agents.{own}"))
        parts = target.split(".")
        return target.startswith(("domain.common", "infrastructure.retrieval")) or (
            top == "domain" and len(parts) >= 3 and parts[2] in ("selectors", "services", "views", "models")
        )
    if source.startswith("orchestration"):
        return top not in ("access_control",) and not any(target.startswith(f"agents.{a}") for a in AGENT_PACKAGES)
    if source.startswith("domain"):
        return top not in ("access_control", "orchestration", "agents")
    if source.startswith("infrastructure"):
        return top not in ("access_control", "orchestration", "agents", "domain")
    return True


def python_files(package: str):
    return [p for p in (ROOT / package).rglob("*.py") if "migrations" not in p.parts]


def test_imports_only_point_down_the_layers():
    violations = []
    for package in ("access_control", "orchestration", "agents", "domain", "infrastructure"):
        for path in python_files(package):
            source = module_name(path)
            for target in imports(path):
                if not allowed(source, target):
                    violations.append(f"{source} -> {target}")
    assert violations == []


def test_only_infrastructure_talks_to_the_network():
    offenders = []
    for package in ("access_control", "orchestration", "agents", "domain"):
        for path in python_files(package):
            if any(target.startswith(NETWORK_MODULES) for target in imports(path)):
                offenders.append(module_name(path))
    assert offenders == []


def test_rule_checker_catches_violations():
    assert not allowed("agents.planning.agent", "agents.assessment.agent")
    assert not allowed("agents.runtime.runtime", "django.conf")
    assert not allowed("domain.learning.services", "orchestration.task_queue.dispatcher")
    assert allowed("agents.planning.agent", "domain.learning.selectors")
    assert allowed("agents.planning.agent", "domain.learning.views.plan_view")
    assert not allowed("agents.planning.agent", "domain.learning.apps.LearningConfig")
    assert not allowed("agents.planning.agent", "orchestration.task_queue.dispatcher")
