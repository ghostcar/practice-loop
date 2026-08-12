"""LockTimer application services — C3 draft/start, C4 materializer, C5 execution.

REFACTORING.md step 1 (Session 82): the single execution.py module was split into
siblings — drafts, materializer, session, jobs, tags — plus execution.py which
keeps the C5 core and re-exports everything (imports stay backwards-compatible).
"""
