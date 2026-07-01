"""Temporary compatibility facade for older imports.

New code should import from the feature package that owns the behavior. This file
exists only to keep any remaining legacy imports working during the split.
"""
from app.service_registry import wire_services

globals().update(wire_services())
