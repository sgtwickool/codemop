import httpx

from config.settings import REQUEST_TIMEOUT


def fetch(url):
    return httpx.get(url, timeout=REQUEST_TIMEOUT)
