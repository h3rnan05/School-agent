from app.blackboard.dedupe import IdentitySource, compute_fingerprint, resolve_identity


def test_prefers_blackboard_id_when_available():
    identity, source = resolve_identity(
        course_id="_12345_1",
        title="Chapter 4 Homework",
        blackboard_id="_content_9001",
        url="https://university.blackboard.com/content/9001",
        due_date_raw="August 12, 2026 11:59 PM",
        points=50.0,
    )
    assert identity == "_content_9001"
    assert source == IdentitySource.BLACKBOARD_ID


def test_falls_back_to_url_when_no_blackboard_id():
    identity, source = resolve_identity(
        course_id="_12345_1",
        title="Chapter 4 Homework",
        blackboard_id=None,
        url="https://university.blackboard.com/content/9001",
        due_date_raw="August 12, 2026 11:59 PM",
        points=50.0,
    )
    assert identity == "https://university.blackboard.com/content/9001"
    assert source == IdentitySource.URL


def test_falls_back_to_fingerprint_as_last_resort():
    identity, source = resolve_identity(
        course_id="_12345_1",
        title="Chapter 4 Homework",
        blackboard_id=None,
        url=None,
        due_date_raw="August 12, 2026 11:59 PM",
        points=50.0,
    )
    assert source == IdentitySource.FINGERPRINT
    assert identity == compute_fingerprint("_12345_1", "Chapter 4 Homework", "August 12, 2026 11:59 PM", 50.0)


def test_fingerprint_is_stable_for_equivalent_input():
    a = compute_fingerprint("_12345_1", "Chapter 4 Homework", "August 12, 2026 11:59 PM", 50.0)
    b = compute_fingerprint("_12345_1", "  chapter 4   homework  ", "August 12, 2026 11:59 PM", 50.0)
    assert a == b  # whitespace/case differences in title should not create a "new" assignment


def test_fingerprint_differs_for_different_assignments():
    a = compute_fingerprint("_12345_1", "Chapter 4 Homework", "August 12, 2026 11:59 PM", 50.0)
    b = compute_fingerprint("_12345_1", "Chapter 5 Homework", "August 19, 2026 11:59 PM", 50.0)
    assert a != b
