"""Doğrudan (tokensız) HLS kanalları — kullanıcı listesinden canlı test edilip seçilen kaynaklar.

Her kanal için birincil + yedek URL. Birincil 200/#EXTM3U vermezse sıradaki yedeğe geçilir.
Mevcut /api/stream/{id}/stream.m3u8 proxy'si ve LED (status) altyapısı AYNEN kullanılır.
"""
from urllib.parse import urlparse

from .stream_registry import StreamManager, register, get

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


class DirectStreamManager(StreamManager):
    def __init__(self, channel_id: str, urls: list[str]):
        self.urls = urls
        self.idx = 0
        host = urlparse(urls[0]).netloc
        super().__init__(channel_id=channel_id, live_host=host, embed_host=host, stream_id=channel_id,
                         env_prefix=f"DIRECT_{channel_id.upper()}", dynamic_tms=False, user_agent=UA,
                         extra_allowed_hosts=[urlparse(u).netloc for u in urls])
        self.current_token = "direct"

    def get_stream_url(self) -> str:
        return self.urls[self.idx]

    def get_segment_base(self) -> str:
        return self.get_stream_url().split("?", 1)[0].rsplit("/", 1)[0] + "/"

    def is_configured(self) -> bool:
        return True

    async def hydrate(self) -> None:
        return

    async def persist(self) -> None:
        return

    async def try_auto_refresh(self) -> bool:
        """Yedek kaynağa geç (varsa)."""
        if len(self.urls) < 2:
            return False
        self.idx = (self.idx + 1) % len(self.urls)
        self.live_host = urlparse(self.get_stream_url()).netloc
        return True


# id → (isim, [birincil, yedek...])
DIRECT_CHANNELS: dict[str, tuple[str, list[str]]] = {
    "trt1":      ("TRT 1", ["https://tv-trt1.medya.trt.com.tr/master.m3u8", "https://trt.daioncdn.net/trt-1/master.m3u8?app=web"]),
    "aspor":     ("A SPOR", ["https://rnttwmjcin.turknet.ercdn.net/lcpmvefbyo/aspor/aspor.m3u8", "https://rnttwmjcin.turknet.ercdn.net/lcpmvefbyo/aspor/aspor_720p.m3u8"]),
    "htspor":    ("HT SPOR", ["https://rmtftbjlne.turknet.ercdn.net/bpeytmnqyp/ht-spor/ht-spor.m3u8", "https://ciner.daioncdn.net/ht-spor/ht-spor_720p.m3u8?ex=0&sid=7yj1ajgk7th3&app=d5539841-018b-48b4-80fe-8bac2ffc3d5e&ce=2"]),
    "ekolsport": ("EKOL SPORTS", ["https://ekoltv-live.ercdn.net/ekolsport/ekolsport_1080p.m3u8?autoplay=1", "https://ekoltv-live.ercdn.net/ekolsport/ekolsport.m3u8"]),
    "beinxtra":  ("beIN SPORTS XTRA", ["https://bein-esp-xumo.amagi.tv/playlistR1080p.m3u8", "https://bein-esp-xumo.amagi.tv/playlist.m3u8"]),
    "tracesport": ("TRACE SPORT STARS", ["https://lightning-tracesport-samsungau.amagi.tv/playlist.m3u8"]),
    "ktvsport":  ("KTV SPORT PLUS", ["https://kwtsplta.cdn.mangomolo.com/spl/smil:spl.stream.smil/chunklist.m3u8"]),
    "showtv":    ("SHOW TV", ["https://rmtftbjlne.turknet.ercdn.net/bpeytmnqyp/showtv/showtv.m3u8", "https://ciner.daioncdn.net/showtv/showtv.m3u8?ce=3&app=4bc856ef-4c68-4a94-bc87-37dfaaa66558&st=RBzhSuGauna0OGld-DJUVA&e=1664766175&tv=1"]),
    "atv":       ("ATV", ["https://rnttwmjcin.turknet.ercdn.net/lcpmvefbyo/atv/atv.m3u8"]),
    "nowtv":     ("NOW (FOX)", ["https://uycyyuuzyh.turknet.ercdn.net/nphindgytw/nowtv/nowtv.m3u8"]),
    "kanald":    ("KANAL D", ["https://ackaxsqacw.turknet.ercdn.net/ozfkfbbjba/kanald/kanald_1080p.m3u8", "https://demiroren.daioncdn.net/kanald/kanald.m3u8?app=kanald_web&ce=3"]),
    "kanal7":    ("KANAL 7", ["https://yurhnwtpys.turknet.ercdn.net/cvmbjbpmdx/kanal7/kanal7_1080p.m3u8", "https://kanal7-live.daioncdn.net/kanal7/kanal7.m3u8"]),
    "startv":    ("STAR TV", ["http://dygvideo.dygdigital.com/live/hls/startv4puhu?m3u8", "http://dygvideo.dygdigital.com/live/hls/stardai?m3u8"]),
    "tv85":      ("TV 8.5", ["https://rkhubpaomb.turknet.ercdn.net/fwjkgpasof/tv8bucuk/tv8bucuk.m3u8", "https://tv8.daioncdn.net/tv8bucuk/tv8bucuk.m3u8?app=tv8bucuk_web"]),
    "cnnturk":   ("CNN TÜRK", ["https://helga.iptv2022.com/cnn_turk/index.m3u8"]),
    "trtmuzik":  ("TRT MÜZİK", ["https://tv-trtmuzik.medya.trt.com.tr/master.m3u8"]),
    "powertv":   ("POWER TV", ["https://livetv.powerapp.com.tr/powerTV/powerhd.smil/playlist.m3u8", "https://live.artidijitalmedya.com/artidijital_powertv/powertv/playlist.m3u8"]),
    "powerturk": ("POWER TÜRK", ["https://live.artidijitalmedya.com/artidijital_powerturktv/powerturktv/playlist.m3u8", "http://livetv.powerapp.com.tr/powerturkTV/powerturkhd.smil/playlist.m3u8"]),
    "kraltv":    ("KRAL TV", ["http://dygvideo.dygdigital.com/live/hls/kralpop?m3u8"]),
    "number1":   ("NUMBER 1", ["https://b01c02nl.mediatriple.net/videoonlylive/mtkgeuihrlfwlive/broadcast_5c9e17cd59e8b.smil/playlist.m3u8"]),
    "dreamturk": ("DREAM TÜRK", ["https://live.duhnet.tv//S2/HLS_LIVE/dreamturknp/track_4_1250/playlist.m3u8"]),
}


def bootstrap_direct() -> None:
    for cid, (_name, urls) in DIRECT_CHANNELS.items():
        register(DirectStreamManager(cid, urls))  # trt1 placeholder'ı da bununla ezilir


# ---- otomatik test edilmiş ek kaynaklar (build_channels.py) ----
try:
    from .direct_channels_extra import DIRECT_EXTRA  # type: ignore
    for _cid, _v in DIRECT_EXTRA.items():
        DIRECT_CHANNELS.setdefault(_cid, _v)
except Exception:  # dosya yoksa sorun degil
    pass
