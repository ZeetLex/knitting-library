"""Import and wire split backend service modules.

The legacy backend relied on one module-level global namespace. The refactor keeps
behavior stable by sharing service symbols after the domain modules are imported,
so moved functions can still resolve cross-domain helpers at call time.
"""
from importlib import import_module

SERVICE_MODULES = [
    "app.core.foundation",
    "app.core.service",
    "app.core.static",
    "app.auth.service",
    "app.admin.service",
    "app.recipes.repository",
    "app.recipes.files",
    "app.recipes.service",
    "app.ai.prompts",
    "app.ai.ocr",
    "app.ai.jobs",
    "app.ai.service",
    "app.review.service",
    "app.yarns.service",
    "app.inventory.service",
    "app.stats.service",
    "app.releases.service",
]

_wired = False


def wire_services() -> dict:
    global _wired
    modules = [import_module(name) for name in SERVICE_MODULES]
    symbols = {}
    for module in modules:
        for name, value in vars(module).items():
            if not name.startswith("__"):
                symbols[name] = value
    for module in modules:
        module.__dict__.update(symbols)
        module.__all__ = [name for name in module.__dict__ if not name.startswith("__")]
    _wired = True
    return symbols
