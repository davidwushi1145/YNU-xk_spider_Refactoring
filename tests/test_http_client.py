"""Tests for HTTP client."""

from unittest.mock import Mock, patch, MagicMock
import pytest
import requests

from ynu_xk_spider.http.client import HttpClient
from ynu_xk_spider.exceptions import NetworkError, SessionExpiredError


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = Mock()
    settings.base_url = "https://example.com/"
    settings.http_timeout = 10.0
    settings.max_retries = 3
    settings.retry_backoff = 0.1
    settings.retry_factor = 2.0
    return settings


@pytest.fixture
def http_client(mock_settings):
    """Create HTTP client instance."""
    return HttpClient(mock_settings)


class TestHttpClient:
    """Test cases for HttpClient."""

    def test_initialization(self, http_client, mock_settings):
        """Test client initializes with correct settings."""
        assert http_client._timeout == mock_settings.http_timeout
        assert http_client._token is None

    def test_set_auth(self, http_client):
        """Test authentication setup."""
        token = "test_token_12345"
        cookies = {"session": "abc123"}

        http_client.set_auth(token, cookies)

        assert http_client.token == token
        assert "Authorization" in http_client._session.headers
        assert http_client._session.headers["Token"] == token

    def test_token_property(self, http_client):
        """Test token property returns current token."""
        assert http_client.token is None

        http_client._token = "my_token"
        assert http_client.token == "my_token"

    @patch.object(requests.Session, "get")
    def test_get_success(self, mock_get, http_client):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "success"
        mock_get.return_value = mock_response

        response = http_client.get("https://example.com/test")

        assert response.status_code == 200
        mock_get.assert_called_once()

    @patch.object(requests.Session, "post")
    def test_post_success(self, mock_post, http_client):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "success"
        mock_post.return_value = mock_response

        response = http_client.post("https://example.com/test", data={"key": "value"})

        assert response.status_code == 200
        mock_post.assert_called_once()

    def test_check_session_expired_401(self, http_client):
        """Test session expiration detection on 401."""
        mock_response = Mock()
        mock_response.status_code = 401

        with pytest.raises(SessionExpiredError):
            http_client._check_session_expired(mock_response)

    def test_check_session_expired_text(self, http_client):
        """Test session expiration detection via response text."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "未查询到登录信息"

        with pytest.raises(SessionExpiredError):
            http_client._check_session_expired(mock_response)

    def test_close(self, http_client):
        """Test client close."""
        http_client.close()
        # Should not raise any exceptions
