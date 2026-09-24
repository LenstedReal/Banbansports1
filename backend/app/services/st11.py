"""ST11.LOL token manager for beIN 1 stream."""
import asyncio
import logging
import re
import httpx
from time import time
from ..core.config import ST11_TOKEN, ST11_TMS, ST11_VALIDATE_TIMEOUT

logger = logging.getLogger("banbansports.st11")


class ST11TokenManager:
    def __init__(self):
        self.base_url = "http://st11.lol"
        self.stream_id = "bs111"
        self.current_token = ST11_TOKEN
        self.current_tms = ST11_TMS
        self.last_refresh = time()
        self.lock = asyncio.Lock()

    async def get_stream_url(self) -> str:
        return f"{self.base_url}/static/{self.stream_id}.m3u8?tms={self.current_tms}&token={self.current_token}"

    async def is_token_valid(self) -> bool:
        if not self.current_token or not self.current_tms:
            return False
        try:
            async with httpx.AsyncClient(timeout=ST11_VALIDATE_TIMEOUT) as http:
                r = await http.get(await self.get_stream_url(),
                                   headers={"User-Agent": "SSUserAgent", "Host": "st11.lol"},
                                   follow_redirects=True)
                if r.status_code != 200:
                    return False
                return r.text.startswith("#EXTM3U") and "#EXT-X" in r.text
        except Exception:
            return False

    async def try_auto_refresh(self) -> bool:
        async with self.lock:
            candidates = [
                f"{self.base_url}/stream/{self.stream_id}",
                f"{self.base_url}/embed/{self.stream_id}",
                f"{self.base_url}/?p=stream&id={self.stream_id}",
                f"{self.base_url}/{self.stream_id}",
                f"{self.base_url}/",
            ]
            patterns = [
                re.compile(r'tms=(\d+)[^"\s]*?token=([A-Za-z0-9_-]+)'),
                re.compile(r'token=([A-Za-z0-9_-]+)[^"\s]*?tms=(\d+)'),
            ]
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
                    for url in candidates:
                        try:
                            r = await http.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*"})
                            if r.status_code != 200 or not r.text:
                                continue
                            text = r.text
                            new_tms = new_token = None
                            for pat in patterns:
                                m = pat.search(text)
                                if m:
                                    if pat.pattern.startswith(r'tms'):
                                        new_tms, new_token = m.group(1), m.group(2)
                                    else:
                                        new_token, new_tms = m.group(1), m.group(2)
                                    break
                            if new_tms and new_token and (new_tms != self.current_tms or new_token != self.current_token):
                                test_url = f"{self.base_url}/static/{self.stream_id}.m3u8?tms={new_tms}&token={new_token}"
                                tr = await http.get(test_url, headers={"User-Agent": "SSUserAgent", "Host": "st11.lol"}, follow_redirects=True)
                                if tr.status_code == 200 and tr.text.startswith("#EXTM3U"):
                                    self.current_tms = new_tms
                                    self.current_token = new_token
                                    self.last_refresh = time()
                                    logger.info("ST11 token auto-refresh OK")
                                    return True
                        except Exception as e:
                            logger.debug(f"ST11 try {url}: {e}")
            except Exception as e:
                logger.warning(f"ST11 outer error: {e}")
            return False


st11_manager = ST11TokenManager()
