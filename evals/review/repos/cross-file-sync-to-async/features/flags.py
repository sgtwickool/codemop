import httpx

FLAGS_URL = "https://flags.internal/api/flags"


async def load_flags():
    """The feature flags for this deployment"""
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(FLAGS_URL)
    response.raise_for_status()
    return response.json()
