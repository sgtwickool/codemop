import httpx
import asyncio
from typing import Optional, Dict, Any
from app.config import settings

async def fetch_with_retry(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[dict] = None,
    json: Optional[dict] = None,
    timeout: float = 120.0
) -> httpx.Response:
    """Fetch URL with retry logic"""
    for attempt in range(settings.MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=json, data=data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                return response
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < settings.MAX_RETRIES - 1:
                # Rate limited, wait and retry
                wait_time = settings.RETRY_DELAY * (attempt + 1)
                print(f"Rate limited, retrying in {wait_time}s (attempt {attempt + 1}/{settings.MAX_RETRIES})")
                await asyncio.sleep(wait_time)
            else:
                raise
        except Exception as e:
            if attempt < settings.MAX_RETRIES - 1:
                wait_time = settings.RETRY_DELAY * (attempt + 1)
                print(f"Request error, retrying in {wait_time}s (attempt {attempt + 1}/{settings.MAX_RETRIES}): {str(e)}")
                await asyncio.sleep(wait_time)
            else:
                raise