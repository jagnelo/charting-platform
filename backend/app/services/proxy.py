"""
Proxy rotation service.

Currently STUBBED — all requests go direct.
To enable: set PROXY_ENABLED=true (via root .env for Docker, or backend/.env.dev for local dev) and populate proxies.txt.

Each line in proxies.txt can be:
  host:port
  user:pass@host:port
  http://host:port
  http://user:pass@host:port
"""

import logging
import random
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_proxy_pool: list[str] = []
_loaded = False


def _load_proxies() -> None:
    global _proxy_pool, _loaded
    if _loaded:
        return
    proxy_file = Path(settings.PROXY_FILE)
    if not proxy_file.exists():
        logger.info("proxies.txt not found — running without proxies")
        _loaded = True
        return
    lines = proxy_file.read_text().splitlines()
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            if not line.startswith("http"):
                line = f"http://{line}"
            _proxy_pool.append(line)
    logger.info(f"Loaded {len(_proxy_pool)} proxies from {proxy_file}")
    _loaded = True


def get_proxy() -> dict | None:
    """
    Returns a randomly selected proxy dict suitable for httpx/requests,
    or None if proxy usage is disabled or no proxies are configured.
    """
    if not settings.PROXY_ENABLED:
        return None
    _load_proxies()
    if not _proxy_pool:
        return None
    proxy_url = random.choice(_proxy_pool)
    return {"http://": proxy_url, "https://": proxy_url}


def get_proxy_url() -> str | None:
    """Returns a single proxy URL string, or None."""
    proxy = get_proxy()
    if proxy is None:
        return None
    return proxy.get("https://")
