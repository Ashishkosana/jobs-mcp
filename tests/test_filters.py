"""Deterministic tests for the filters — no network."""
from jobs_mcp.server import _blocked, _in_us, _matches


def test_in_us():
    assert _in_us("San Francisco, CA")
    assert _in_us("Remote - United States")
    assert _in_us("")  # unknown location is allowed through
    assert not _in_us("London, UK")
    assert not _in_us("Toronto, ON, CA")
    assert not _in_us("Bengaluru, India")


def test_clearance_blocked():
    assert _blocked("Lockheed Martin", "Software Engineer", "")           # defense company
    assert _blocked("Acme", "Software Engineer, TS/SCI required", "")     # clearance in title
    assert _blocked("Acme", "Backend Engineer", "Annapolis Junction, MD")  # clearance location
    assert not _blocked("Stripe", "Software Engineer", "Remote US")       # clean role


def test_title_match():
    assert _matches("Senior Backend Software Engineer", ["backend", "engineer"])
    assert _matches("Software Engineer, New Grad", ["software", "engineer"])
    assert not _matches("Data Scientist", ["software", "engineer"])
    assert not _matches("Product Manager", ["engineer"])
