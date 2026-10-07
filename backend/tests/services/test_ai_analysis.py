"""
Unit tests for AI Analysis service functions.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.ai_analysis import (
    analyze_diff,
    create_ai_prompt,
    call_ai_api
)
import logging


class TestAIAnalysisService:
    """Test AI Analysis service functions."""

    @pytest.mark.asyncio
    async def test_analyze_diff_success(self):
        """The diff goes into the prompt, and the model's suggestions come back."""
        mock_suggestions = [
            {
                "line_number": 1,
                "file_path": "test.py",
                "description": "Test suggestion",
                "fix": "def test_function():\n    return 'fixed'",
                "confidence": 0.95
            }
        ]
        
        with patch('app.services.ai_analysis.create_ai_prompt') as mock_prompt, \
             patch('app.services.ai_analysis.call_ai_api', new_callable=AsyncMock) as mock_call_ai:
            mock_prompt.return_value = "test prompt"
            mock_call_ai.return_value = mock_suggestions
            
            result = await analyze_diff("def test_function():\n    return 'test'")
            
            assert result == mock_suggestions
            mock_prompt.assert_called_once_with("def test_function():\n    return 'test'")
            mock_call_ai.assert_called_once_with("test prompt")

    @pytest.mark.asyncio
    async def test_analyze_diff_failure(self):
        """Test AI analysis error handling."""
        with patch('app.services.ai_analysis.call_ai_api', new_callable=AsyncMock) as mock_call_ai, \
             patch('app.services.ai_analysis.logger') as mock_logger:
            mock_call_ai.side_effect = Exception("Network error")
            
            with pytest.raises(Exception) as exc_info:
                await analyze_diff("some diff")
            
            assert "Network error" in str(exc_info.value)
            mock_logger.error.assert_called_once_with("💥 AI analysis failed: Network error")

    def test_create_ai_prompt(self):
        """Test AI prompt generation."""
        diff_content = "def test_function():\n    return 'hello'\n    print('unreachable')"
        
        result = create_ai_prompt(diff_content)
        
        # Verify prompt structure
        assert "You are an expert code reviewer" in result
        assert "Analyze the following code diff" in result
        assert "def test_function():" in result
        assert "unreachable" in result
        assert '"suggestions": [' in result
        assert '"line_number": 42' in result
        assert '"confidence": 0.95' in result
        
        # Verify length limit
        long_diff = "x" * 15000
        result = create_ai_prompt(long_diff)
        assert len(result) < 20000  # Should be limited

    def test_create_ai_prompt_empty_diff(self):
        """Test AI prompt with empty diff."""
        result = create_ai_prompt("")
        
        assert "You are an expert code reviewer" in result
        assert "Code Diff:" in result
        assert "```" in result

    @pytest.mark.asyncio
    async def test_call_ai_api_success(self):
        """Test successful AI API call."""
        # Mock AI API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"suggestions": [{"line_number": 1, "file_path": "test.py", "description": "Test", "fix": "fix", "confidence": 0.9}]}'
                    }
                }
            ]
        }
        
        with patch('app.services.ai_analysis.fetch_with_retry', new_callable=AsyncMock) as mock_fetch, \
             patch('app.services.ai_analysis.parse_ai_response') as mock_parse:
            
            mock_fetch.return_value = mock_response
            mock_parse.return_value = [{"line_number": 1, "file_path": "test.py", "description": "Test", "fix": "fix", "confidence": 0.9}]
            
            result = await call_ai_api("test prompt")
            
            assert result == [{"line_number": 1, "file_path": "test.py", "description": "Test", "fix": "fix", "confidence": 0.9}]
            mock_parse.assert_called_once_with('{"suggestions": [{"line_number": 1, "file_path": "test.py", "description": "Test", "fix": "fix", "confidence": 0.9}]}')

    @pytest.mark.asyncio
    async def test_call_ai_api_invalid_response(self):
        """Test AI API call with invalid response format."""
        # Mock AI API response with unexpected format
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "invalid format"}
        
        with patch('app.services.ai_analysis.fetch_with_retry', new_callable=AsyncMock) as mock_fetch, \
             patch('app.services.ai_analysis.logger') as mock_logger:
            
            mock_fetch.return_value = mock_response
            
            result = await call_ai_api("test prompt")
            
            # Should return empty list and log warning
            assert result == []
            mock_logger.warning.assert_called_once_with("Unexpected AI API response format: {'error': 'invalid format'}")

    @pytest.mark.asyncio
    async def test_call_ai_api_no_choices(self):
        """Test AI API call with no choices in response."""
        # Mock AI API response with no choices
        mock_response = MagicMock()
        mock_response.json.return_value = {"other_field": "value"}
        
        with patch('app.services.ai_analysis.fetch_with_retry', new_callable=AsyncMock) as mock_fetch, \
             patch('app.services.ai_analysis.logger') as mock_logger:
            
            mock_fetch.return_value = mock_response
            
            result = await call_ai_api("test prompt")
            
            # Should return empty list and log warning
            assert result == []
            mock_logger.warning.assert_called_once_with("Unexpected AI API response format: {'other_field': 'value'}")

    @pytest.mark.asyncio
    async def test_call_ai_api_network_error(self):
        """Test AI API call with network error."""
        with patch('app.services.ai_analysis.fetch_with_retry', new_callable=AsyncMock) as mock_fetch, \
             patch('app.services.ai_analysis.logger') as mock_logger:
            
            mock_fetch.side_effect = Exception("Connection failed")
            
            with pytest.raises(Exception) as exc_info:
                await call_ai_api("test prompt")
            
            assert "Connection failed" in str(exc_info.value)
            # Note: call_ai_api doesn't log directly - logging happens in analyze_diff