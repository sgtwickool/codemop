"""
Unit tests for middleware components.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from starlette.requests import Request
from app.core.middleware.security_middleware import limit_request_size, add_security_headers
from app.core.middleware.monitoring_middleware import error_tracking_middleware, request_monitoring_middleware
from app.core.security_config import MAX_REQUEST_SIZE, SECURITY_HEADERS
import logging


def make_request(method="GET", headers=None, client=("127.0.0.1", 50000)) -> Request:
    """A real request for /test, so the middleware sees what it would in the app."""
    return Request({
        "type": "http",
        "method": method,
        "path": "/test",
        "query_string": b"",
        "headers": [(name.lower().encode(), value.encode()) for name, value in (headers or {}).items()],
        "client": client,
        "app": FastAPI(),
    })


class TestSecurityMiddleware:
    """Test security middleware functions."""

    @pytest.mark.asyncio
    async def test_limit_request_size_within_limit(self):
        """Test request size limiting with valid size."""
        # Create mock request with valid size
        mock_request = make_request(headers={"content-length": str(MAX_REQUEST_SIZE - 1000)}, method="POST")
        
        # Create mock call_next
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        async def mock_call_next(request):
            return mock_response
        
        # Call middleware
        response = await limit_request_size(mock_request, mock_call_next)
        
        # Should return the response from call_next
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_limit_request_size_exceeds_limit(self):
        """Test request size limiting with too large request."""
        # Create mock request with too large size
        mock_request = make_request(headers={"content-length": str(MAX_REQUEST_SIZE + 1000)}, method="POST")
        
        # Create mock call_next
        async def mock_call_next(request):
            return MagicMock()
        
        # Call middleware
        response = await limit_request_size(mock_request, mock_call_next)
        
        # Should return 413 response
        assert response.status_code == 413
        assert "Request too large" in response.body.decode()

    @pytest.mark.asyncio
    async def test_limit_request_size_invalid_header(self):
        """Test request size limiting with invalid content-length header."""
        # Create mock request with invalid header
        mock_request = make_request(headers={"content-length": "invalid"}, method="POST")
        
        # Create mock call_next
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        async def mock_call_next(request):
            return mock_response
        
        # Call middleware with logging capture
        with pytest.warns(UserWarning):  # Should log warning
            response = await limit_request_size(mock_request, mock_call_next)
        
        # Should return the response from call_next
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_limit_request_size_no_header(self):
        """Test request size limiting with no content-length header."""
        # Create mock request without content-length header
        mock_request = make_request()
        
        # Create mock call_next
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        async def mock_call_next(request):
            return mock_response
        
        # Call middleware
        response = await limit_request_size(mock_request, mock_call_next)
        
        # Should return the response from call_next
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_add_security_headers(self):
        """Test security headers middleware."""
        # Create mock request
        mock_request = make_request()
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.status_code = 200
        
        async def mock_call_next(request):
            return mock_response
        
        # Call middleware
        response = await add_security_headers(mock_request, mock_call_next)
        
        # Should return the response from call_next
        assert response == mock_response
        
        # Should add all security headers
        for header, value in SECURITY_HEADERS.items():
            assert response.headers[header] == value


class TestMonitoringMiddleware:
    """Test monitoring middleware functions."""

    @pytest.mark.asyncio
    async def test_error_tracking_middleware_success(self):
        """Test error tracking middleware with successful request."""
        # Create mock request
        mock_request = make_request(headers={"user-agent": "test-agent"})
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        async def mock_call_next(request):
            return mock_response
        
        # Call middleware
        response = await error_tracking_middleware(mock_request, mock_call_next)
        
        # Should return the response from call_next
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_error_tracking_middleware_exception(self):
        """Test error tracking middleware with exception."""
        # Create mock request
        mock_request = make_request(headers={"user-agent": "test-agent"})
        
        # Create mock call_next that raises exception
        async def mock_call_next(request):
            raise ValueError("Test error")
        
        # Call middleware and expect exception to be re-raised
        with pytest.raises(ValueError) as exc_info:
            await error_tracking_middleware(mock_request, mock_call_next)
        
        assert "Test error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_request_monitoring_middleware_success(self):
        """Test request monitoring middleware with successful request."""
        # Create mock request
        mock_request = make_request(headers={"user-agent": "test-agent"})
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        async def mock_call_next(request):
            return mock_response
        
        # Call middleware
        response = await request_monitoring_middleware(mock_request, mock_call_next)
        
        # Should return the response from call_next
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_request_monitoring_middleware_exception(self):
        """Test request monitoring middleware with exception."""
        # Create mock request
        mock_request = make_request(headers={"user-agent": "test-agent"})
        
        # Create mock call_next that raises exception
        async def mock_call_next(request):
            raise ValueError("Test error")
        
        # Call middleware and expect exception to be re-raised
        with pytest.raises(ValueError) as exc_info:
            await request_monitoring_middleware(mock_request, mock_call_next)
        
        assert "Test error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_request_monitoring_middleware_no_client(self):
        """Test request monitoring middleware with no client info."""
        # Create mock request without client
        mock_request = make_request(headers={"user-agent": "test-agent"}, client=None)
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        async def mock_call_next(request):
            return mock_response
        
        # Call middleware
        response = await request_monitoring_middleware(mock_request, mock_call_next)
        
        # Should return the response from call_next
        assert response == mock_response


class TestMiddlewareIntegration:
    """Test middleware integration scenarios."""

    @pytest.mark.asyncio
    async def test_middleware_chain_success(self):
        """Test that middleware chain works correctly for successful requests."""
        # Create mock request
        mock_request = make_request(headers={"content-length": "1000", "user-agent": "test-agent"})
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        
        async def mock_call_next(request):
            return mock_response
        
        # Apply middleware chain
        response = await limit_request_size(mock_request, mock_call_next)
        
        # Create async functions for middleware chain
        async def next_with_response(request):
            return response
        
        async def next_with_response2(request):
            return response
        
        async def next_with_response3(request):
            return response
        
        response = await add_security_headers(mock_request, next_with_response)
        response = await error_tracking_middleware(mock_request, next_with_response2)
        response = await request_monitoring_middleware(mock_request, next_with_response3)
        
        # Should return the final response
        assert response.status_code == 200
        
        # Should have security headers
        for header, value in SECURITY_HEADERS.items():
            assert response.headers[header] == value

    @pytest.mark.asyncio
    async def test_middleware_chain_exception(self):
        """Test that middleware chain handles exceptions correctly."""
        # Create mock request
        mock_request = make_request(headers={"content-length": "1000", "user-agent": "test-agent"})
        
        # Create mock call_next that raises exception
        async def mock_call_next(request):
            raise ValueError("Test error")
        
        # Apply middleware chain
        with pytest.raises(ValueError) as exc_info:
            response = await limit_request_size(mock_request, mock_call_next)
            response = await add_security_headers(mock_request, lambda r: response)
            response = await error_tracking_middleware(mock_request, lambda r: response)
            response = await request_monitoring_middleware(mock_request, lambda r: response)
        
        assert "Test error" in str(exc_info.value)