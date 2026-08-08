from app.blackboard.config import load_settings


def test_courses_list_url_defaults_to_ultra_course_path(monkeypatch, tmp_path):
    monkeypatch.setenv("BLACKBOARD_BASE_URL", "https://cursos-udem.blackboard.com")
    monkeypatch.setenv("SCHOOL_AGENT_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("BLACKBOARD_COURSES_PATH", raising=False)

    settings = load_settings()

    assert settings.courses_list_url == "https://cursos-udem.blackboard.com/ultra/course"


def test_courses_path_is_overridable(monkeypatch, tmp_path):
    monkeypatch.setenv("BLACKBOARD_BASE_URL", "https://university.blackboard.com")
    monkeypatch.setenv("SCHOOL_AGENT_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("BLACKBOARD_COURSES_PATH", "")

    settings = load_settings()

    assert settings.courses_list_url == "https://university.blackboard.com"


def test_default_timezone_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("BLACKBOARD_BASE_URL", "https://cursos-udem.blackboard.com")
    monkeypatch.setenv("SCHOOL_AGENT_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("BLACKBOARD_TIMEZONE", "America/Monterrey")

    settings = load_settings()

    assert settings.timezone == "America/Monterrey"
