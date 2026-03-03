import pytest
from unittest.mock import patch, MagicMock

from llm.openrouter_client import OpenRouterClient


class TestOpenRouterClientChat:
    def test_missing_endpoint_raises_value_error(self):
        client = OpenRouterClient()
        client.api_endpoint = None
        client.api_key = "some-key"

        with pytest.raises(ValueError, match="configured"):
            client.chat("hello")

    def test_missing_api_key_raises_value_error(self):
        client = OpenRouterClient()
        client.api_endpoint = "https://openrouter.ai/api/v1/chat/completions"
        client.api_key = None

        with pytest.raises(ValueError, match="configured"):
            client.chat("hello")

    def test_successful_response_returns_content(self):
        client = OpenRouterClient()
        client.api_endpoint = "https://openrouter.ai/api/v1/chat/completions"
        client.api_key = "test-key"
        mock_response = {
            "choices": [
                {"message": {"content": "Network status: all good."}}
            ]
        }

        with patch("llm.openrouter_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_response

            result = client.chat("Summarise this report")

        assert result == "Network status: all good."

    def test_missing_choices_key_raises_value_error(self):
        client = OpenRouterClient()
        client.api_endpoint = "https://example.com"
        client.api_key = "key"

        with patch("llm.openrouter_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"error": "something went wrong"}

            with pytest.raises(ValueError, match="Unexpected"):
                client.chat("prompt")

    def test_empty_choices_list_raises_value_error(self):
        client = OpenRouterClient()
        client.api_endpoint = "https://example.com"
        client.api_key = "key"

        with patch("llm.openrouter_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"choices": []}

            with pytest.raises(ValueError, match="Unexpected"):
                client.chat("prompt")

    def test_empty_content_raises_value_error(self):
        client = OpenRouterClient()
        client.api_endpoint = "https://example.com"
        client.api_key = "key"

        with patch("llm.openrouter_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": ""}}]
            }

            with pytest.raises(ValueError, match="Unexpected"):
                client.chat("prompt")

    def test_authorization_header_uses_bearer_token(self):
        client = OpenRouterClient()
        client.api_endpoint = "https://example.com"
        client.api_key = "my-secret-key"

        with patch("llm.openrouter_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "ok"}}]
            }
            client.chat("test")

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer my-secret-key"
