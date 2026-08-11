"""Platform Foundation — contracts and composition shared across all product variants.

This package MUST NOT import from app.locktimer, app.api.tasks, app.models.entity,
or any other Tracker/Timer domain internals.  Domain modules depend on platform;
platform never depends on a domain module.
"""
