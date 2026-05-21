from src.dashboard.frontend.state.session_state import (
    DEFAULT_API_BASE_URL,
    _normalize_api_base_url,
)


def test_normalize_api_base_url_uses_default_for_blank_value() -> None:
    assert _normalize_api_base_url("") == DEFAULT_API_BASE_URL.rstrip("/")


def test_normalize_api_base_url_adds_http_scheme() -> None:
    assert _normalize_api_base_url("127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_normalize_api_base_url_strips_trailing_slash() -> None:
    assert _normalize_api_base_url("http://localhost:8000/") == "http://localhost:8000"


def test_normalize_api_base_url_uses_default_for_relative_path() -> None:
    assert _normalize_api_base_url("/summary/quality") == DEFAULT_API_BASE_URL.rstrip("/")
