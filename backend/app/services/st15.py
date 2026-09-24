"""ST15.LOL token manager for S Sport stream (ST11 paterninin SSport adaptasyonu).

Upstream master: https://live.st15.lol/ss11/index.m3u8?token=...&tms=...

KEŞFEDİLEN DAVRANIŞ: ST15 sunucusu TMS değerini DOĞRULAMIYOR.
  - TMS=0, TMS=gelecek tarih, TMS hiç yok → hepsi 200 OK döner
  - Sadece TOKEN doğrulanıyor
  - Bu yüzden TMS'i her request'te anlık Unix timestamp olarak üretmek
    en sağlam stratejidir (sabit TMS yıllar sonra CDN cache anomalisi
    yaratabilir, dinamik TMS her zaman taze).

ENV:
  * SSPORT_TOKEN  (zorunlu)  - tek başına yetiyor, asıl auth bu
  * STREAM_TOKEN  (alias, backward compat)
  * SSPORT_TMS    (opsiyonel) - manuel sabit TMS istenirse override eder
  * STREAM_TMS    (alias, backward compat)
  * SSPORT_DYNAMIC_TMS=true (varsayılan) → her request'te anlık timestamp
"""
import asyncio
import logging
import os
import re
import httpx
from time import time

logger = logging.getLogger("banbansports.st15")

# ENV'den oku — iki isim de desteklenir
INIT_TOKEN = (os.environ.get('SSPORT_TOKEN') or os.environ.get('STREAM_TOKEN') or '').strip()
INIT_TMS = (os.environ.get('SSPORT_TMS') or os.environ.get('STREAM_TMS') or '').strip()
# Dynamic TMS opsiyonu — varsayılan: True (anlık timestamp her request'te)
DYNAMIC_TMS = os.environ.get('SSPORT_DYNAMIC_TMS', 'true').lower() in ('1', 'true', 'yes', 'on')
ST15_VALIDATE_TIMEOUT = 8.0


class ST15TokenManager:
    def __init__(self):
        self.live_host = "live.st15.lol"
        self.embed_host = "st15.lol"
        self.stream_id = "ss11"
        self.current_token = INIT_TOKEN
        self.current_tms = INIT_TMS  # Sabit override (manuel). Boşsa dynamic kullanılır.
        self.dynamic_tms = DYNAMIC_TMS
        self.last_refresh = time()
        self.lock = asyncio.Lock()

    def _effective_tms(self) -> str:
        """ENV'de sabit TMS varsa onu döndür, yoksa anlık Unix timestamp."""
        if self.current_tms and not self.dynamic_tms:
            return self.current_tms
        return str(int(time()))

    def get_stream_url(self) -> str:
        tms = self._effective_tms()
        return (f"https://{self.live_host}/{self.stream_id}/index.m3u8"
                f"?token={self.current_token}&tms={tms}")

    async def is_token_valid(self) -> bool:
        if not self.current_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=ST15_VALIDATE_TIMEOUT) as http:
                r = await http.get(self.get_stream_url(),
                                   headers={"User-Agent": "SSUserAgent",
                                            "Host": self.live_host,
                                            "Accept": "*/*"},
                                   follow_redirects=True)
                if r.status_code != 200:
                    return False
                return r.text.startswith("#EXTM3U") and "#EXT-X" in r.text
        except Exception:
            return False

    async def try_auto_refresh(self) -> bool:
        """Embed sayfalarından yeni TOKEN parse et, master ile validate et, geçerse güncelle.

        TMS dynamic olduğu için sadece TOKEN refresh ediyoruz (ST15 server TMS doğrulamıyor).
        ST15 stream servisi ST11'den biraz farklı olduğu için bu best-effort'tur.
        Başarısız olursa current_token korunur
        admin panelinden manuel rotate gerekli.
        Toplam max süre ~12 saniye (per-request 3s × 5 candidate + 2 validate).
        """
        async with self.lock:
            candidates = [
                f"https://{self.embed_host}/stream/{self.stream_id}",
                f"https://{self.embed_host}/embed/{self.stream_id}",
                f"https://{self.embed_host}/{self.stream_id}",
                f"https://{self.embed_host}/?p=stream&id={self.stream_id}",
                f"https://{self.embed_host}/",
            ]
            # Token-only pattern (TMS yok say, sadece token parse et)
            token_only_pat = re.compile(r'token=([A-Za-z0-9_-]{10,})')
            # Birlikte de yakalayabilen pattern'ler
            combo_patterns = [
                re.compile(r'token=([A-Za-z0-9_-]+)[^"\s\'<>]*?tms=(\d+)'),
                re.compile(r'tms=(\d+)[^"\s\'<>]*?token=([A-Za-z0-9_-]+)'),
            ]
            try:
                async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as http:
                    for url in candidates:
                        try:
                            r = await http.get(url, headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                "Accept": "text/html,application/xhtml+xml,*/*",
                                "Referer": f"https://{self.embed_host}/",
                            })
                            if r.status_code != 200 or not r.text:
                                continue
                            text = r.text
                            new_token = None
                            # Önce combo dene
                            for pat in combo_patterns:
                                m = pat.search(text)
                                if not m:
                                    continue
                                if pat.pattern.startswith(r'token'):
                                    new_token = m.group(1)
                                else:
                                    new_token = m.group(2)
                                break
                            # Combo yoksa sadece token ara
                            if not new_token:
                                m = token_only_pat.search(text)
                                if m:
                                    new_token = m.group(1)
                            if not new_token:
                                continue
                            if new_token == self.current_token:
                                continue
                            # Validate yeni token'ı dynamic TMS ile master'da dene
                            test_url = (f"https://{self.live_host}/{self.stream_id}/index.m3u8"
                                        f"?token={new_token}&tms={int(time())}")
                            tr = await http.get(test_url, headers={
                                "User-Agent": "SSUserAgent",
                                "Host": self.live_host,
                                "Accept": "*/*",
                            }, follow_redirects=True, timeout=4.0)
                            if tr.status_code == 200 and tr.text.startswith("#EXTM3U"):
                                self.current_token = new_token
                                self.last_refresh = time()
                                logger.info(f"ST15/S Sport TOKEN auto-refresh OK (src={url})")
                                return True
                        except Exception as e:
                            logger.debug(f"ST15 try {url}: {e}")
            except Exception as e:
                logger.warning(f"ST15 outer error: {e}")
            return False


st15_manager = ST15TokenManager()
