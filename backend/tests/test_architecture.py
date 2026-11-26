"""Architectural governance tests enforcing Route -> Service -> Repository boundaries."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from fastapi.routing import APIRoute

from app.main import app

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _collect_imports(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_routes_and_services_have_zero_sqlalchemy_imports():
    """Enforce strict layering: neither API routes nor services may touch SQLAlchemy directly."""
    checked_dirs = [APP_ROOT / "api", APP_ROOT / "services", APP_ROOT / "adapters" / "servicenow"]
    violations: list[str] = []

    for directory in checked_dirs:
        for py_file in sorted(directory.rglob("*.py")):
            imports = _collect_imports(py_file)
            for mod in imports:
                if mod == "sqlalchemy" or mod.startswith("sqlalchemy.") or mod == "app.core.database":
                    violations.append(f"{py_file.relative_to(APP_ROOT)} imports {mod}")

    assert violations == [], f"Layering violations detected: {violations}"


def test_all_api_route_handlers_are_async():
    """Ensure every registered FastAPI route endpoint is defined with ``async def``."""
    non_async_routes: list[str] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            # Ignore built-in FastAPI docs/openapi endpoints
            if route.path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
                continue
            if not inspect.iscoroutinefunction(route.endpoint):
                non_async_routes.append(f"{sorted(route.methods)} {route.path} -> {route.name}")

    assert non_async_routes == [], f"Non-async API routes detected: {non_async_routes}"
