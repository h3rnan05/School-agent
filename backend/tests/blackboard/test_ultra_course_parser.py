"""UltraCourseParser is an intentional stub (Phase 2.1: no real Ultra
Course View content page was available). These tests document that it
fails safe — no crash, no invented assignments — rather than claiming it
works.
"""
from app.blackboard.parsers import UltraCourseParser


def test_ultra_course_parser_returns_empty_list_not_error():
    result = UltraCourseParser().parse(
        html="<html><body>whatever an Ultra course page looks like</body></html>",
        course_id="_98766_1",
        base_url="https://university.blackboard.com",
        timezone="UTC",
    )
    assert result == []
