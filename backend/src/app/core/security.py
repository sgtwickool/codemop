import hmac
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from app.config import settings

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    """Extract and validate API key from Authorization header"""
    if not api_key_header:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing"
        )
    
    # Handle "Bearer " prefix
    if api_key_header.startswith("Bearer "):
        api_key = api_key_header[7:].strip()
    else:
        api_key = api_key_header.strip()
    
    # An unset API_KEY never matches (not even an empty bearer token). The comparison is
    # constant-time, so response timing doesn't reveal how much of a guess was right
    if not settings.API_KEY or not hmac.compare_digest(api_key.encode(), settings.API_KEY.encode()):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return api_key