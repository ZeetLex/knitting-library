"""Admin, mail, logs, and announcement helpers."""
from app import services as _services

globals().update({
    name: getattr(_services, name)
    for name in dir(_services)
    if not name.startswith("__")
})
