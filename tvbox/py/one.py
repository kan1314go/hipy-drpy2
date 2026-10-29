# -*- coding: utf-8 -*-
import ast
import base64
import datetime
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import zlib
import ssl

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def __init__(self, *args, **kwargs):
            pass

        def getProxyUrl(self, *args, **kwargs):
            return ""

FILM_FILTERS = {"6_1": "欧美", "6_2": "日本", "6_3": "国产", "6_4": "直播", "6_5": "新作", "3_3": "4K独播", "manga": "漫画", "album": "写真"}
FILM_ORDER = ("6_3", "6_2", "6_1", "6_5", "3_3", "6_4", "manga", "album")
ONE_API = "https://api.em1oifd0.com/"
ONE_MIRRORS = ("https://api.3459381.com/", "https://api.61c76a0.com/", "https://api.87735d5.com/", "https://api.c6dd5cc.com/", "https://api.j7y675.com/", "https://api.em1oifd0.com/")
BOOTSTRAP_LINES = ("http://198.44.248.101:9672/", "http://198.44.248.102:9672/", "http://122.10.20.249:9672/")
BOX_KEY = b"dnf45as45fs1ace1"
BOX_IV = b"dn5as4fs1ac5f4e1"
ONE_KEY = b"l*bv%Ziq000Biaog"
ONE_IV = b"8597506002939249"
ONE_SIGN_SUFFIX = "m4n2hjPeYWkD6tFpqKF^3HO^h24P@idT"
ONE_IMAGE_KEY = b"saIZXc4yMvq0Iz56"
ONE_IMAGE_IV = b"kbJYtBJUECT0oyjo"
DEFAULT_TIMEOUT = 8
DEFAULT_UA = "Dart/3.4 (dart:io)"
SIZE = 20
FORMAT = "json"
PREVIEW_HINTS = ("preview", "trailer", "sample", "_pv.", "pv_")
PROXY_SALT = "one.tvp.pic.v2026"
LOCAL_PORT_START = 18700

_AES_SBOX = (
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
)

def _aes_build_inv():
    inv = [0] * 256
    for i, v in enumerate(_AES_SBOX):
        inv[v] = i
    return inv

_AES_INV_SBOX = _aes_build_inv()
_AES_RCON = (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36)

def _gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p & 0xFF

def _aes_expand(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_AES_SBOX[b] for b in t]
            t[0] ^= _AES_RCON[i // nk]
        elif nk > 6 and i % nk == 4:
            t = [_AES_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(nr + 1)], nr

def _aes_decrypt_block(blk, rk, nr):
    s = [blk[i] ^ rk[0][i] for i in range(16)]
    for rnd in range(1, nr):
        t = list(s)
        for r in range(1, 4):
            for c in range(4):
                s[4 * c + r] = t[4 * ((c - r) % 4) + r]
        s = [_AES_INV_SBOX[b] for b in s]
        s = [s[i] ^ rk[rnd][i] for i in range(16)]
        t = list(s)
        for c in range(4):
            a0, a1, a2, a3 = t[4 * c], t[4 * c + 1], t[4 * c + 2], t[4 * c + 3]
            s[4 * c] = _gmul(a0, 14) ^ _gmul(a1, 11) ^ _gmul(a2, 13) ^ _gmul(a3, 9)
            s[4 * c + 1] = _gmul(a0, 9) ^ _gmul(a1, 14) ^ _gmul(a2, 11) ^ _gmul(a3, 13)
            s[4 * c + 2] = _gmul(a0, 13) ^ _gmul(a1, 9) ^ _gmul(a2, 14) ^ _gmul(a3, 11)
            s[4 * c + 3] = _gmul(a0, 11) ^ _gmul(a1, 13) ^ _gmul(a2, 9) ^ _gmul(a3, 14)
    t = list(s)
    for r in range(1, 4):
        for c in range(4):
            s[4 * c + r] = t[4 * ((c - r) % 4) + r]
    s = [_AES_INV_SBOX[b] for b in s]
    s = [s[i] ^ rk[nr][i] for i in range(16)]
    return bytes(s)

def _aes_encrypt_block(blk, rk, nr):
    s = [blk[i] ^ rk[0][i] for i in range(16)]
    for rnd in range(1, nr):
        for r in range(4):
            for c in range(4):
                s[4 * c + r] = _AES_SBOX[s[4 * c + r]]
        t = list(s)
        for r in range(1, 4):
            for c in range(4):
                s[4 * c + r] = t[4 * ((c + r) % 4) + r]
        t = list(s)
        for c in range(4):
            a0, a1, a2, a3 = t[4 * c], t[4 * c + 1], t[4 * c + 2], t[4 * c + 3]
            s[4 * c] = _gmul(a0, 2) ^ _gmul(a1, 3) ^ a2 ^ a3
            s[4 * c + 1] = a0 ^ _gmul(a1, 2) ^ _gmul(a2, 3) ^ a3
            s[4 * c + 2] = a0 ^ a1 ^ _gmul(a2, 2) ^ _gmul(a3, 3)
            s[4 * c + 3] = _gmul(a0, 3) ^ a1 ^ a2 ^ _gmul(a3, 2)
        s = [s[i] ^ rk[rnd][i] for i in range(16)]
    for r in range(4):
        for c in range(4):
            s[4 * c + r] = _AES_SBOX[s[4 * c + r]]
    t = list(s)
    for r in range(1, 4):
        for c in range(4):
            s[4 * c + r] = t[4 * ((c + r) % 4) + r]
    s = [s[i] ^ rk[nr][i] for i in range(16)]
    return bytes(s)

def _pad(data):
    length = 16 - (len(data) % 16)
    return data + bytes([length]) * length

def _unpad(data):
    if not data:
        return data
    length = data[-1]
    if length < 1 or length > 16 or data[-length:] != bytes([length]) * length:
        raise ValueError("invalid cipher padding")
    return data[:-length]

def _aes(data, key, iv, decrypt=False):
    try:
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return cipher.decrypt(data) if decrypt else cipher.encrypt(_pad(data))
    except Exception:
        pass
    try:
        from Cryptodome.Cipher import AES
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return cipher.decrypt(data) if decrypt else cipher.encrypt(_pad(data))
    except Exception:
        pass
    try:
        import subprocess
        command = ["openssl", "enc", "-aes-128-cbc"]
        if decrypt:
            command.append("-d")
        command.extend(["-nopad", "-K", key.hex(), "-iv", iv.hex()])
        source = data if decrypt else _pad(data)
        process = subprocess.run(command, input=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return process.stdout
    except Exception:
        pass
    rk, nr = _aes_expand(key)
    out = bytearray()
    prev = iv
    if decrypt:
        n = len(data) - (len(data) % 16)
        for i in range(0, n, 16):
            blk = data[i:i + 16]
            dec = _aes_decrypt_block(blk, rk, nr)
            out += bytes(a ^ b for a, b in zip(dec, prev))
            prev = blk
        return bytes(out)
    else:
        padded = _pad(data)
        for i in range(0, len(padded), 16):
            blk = bytes(a ^ b for a, b in zip(padded[i:i + 16], prev))
            enc = _aes_encrypt_block(blk, rk, nr)
            out += enc
            prev = enc
        return bytes(out)

def _decrypt_one_image(data):
    return _unpad(_aes(data, ONE_IMAGE_KEY, ONE_IMAGE_IV, decrypt=True))

def _image_kind(data, loose=False):
    if data.startswith(b"\xff\xd8\xff") and (loose or data.endswith(b"\xff\xd9")):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n") and (loose or data.endswith(b"IEND\xaeB`\x82")):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")) and (loose or data.endswith(b";")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None

def _is_audio_path(path):
    return isinstance(path, str) and path.lower().split("?", 1)[0].endswith((".mp3", ".m4a", ".aac", ".wav", ".flac"))

def _looks_preview(value):
    text = str(value).lower()
    return any(hint in text for hint in PREVIEW_HINTS)

def _clean(text, limit=0):
    safe = str(text or "").replace("$", " ").replace("#", " ").replace("\r", " ").replace("\n", " ").strip()
    return safe[:limit] if limit else safe

def _choose_media(item, strict=False):
    if not isinstance(item, dict):
        return None
    for field in ("video_hls", "video_hls_h265", "video_file", "video"):
        value = item.get(field)
        if not isinstance(value, str) or not value:
            continue
        if _is_audio_path(value):
            continue
        if strict and _looks_preview(value):
            continue
        return field, value
    return None

def _diag_row(title, detail, hint):
    return {
        "vod_id": "diag",
        "vod_name": "【诊断】" + _clean(title, 40),
        "vod_pic": "",
        "vod_remarks": "ZakaTV",
        "vod_director": "📺ZakaTV",
        "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
        "vod_year": "",
        "vod_content": "【官方TG群: https://t.me/+3t5XRPPo9mlkZDRl ZakaTV交流圈】\n▸ %s\n\n原因：%s\n\n%s" % (_clean(title, 120), _clean(detail, 200), hint),
        "vod_play_from": "",
        "vod_play_url": "",
        "style": {"type": "rect", "ratio": 1.78}
    }

def _diag_page(page, title, detail):
    hint = ("排查顺序：\n"
            "1) 连不上站点 → ext 填 net=proxy,proxy=http://ip:端口\n"
            "2) 提示签名/授权失败 → 引导配置没取到，ext 加 line=http://198.44.248.101:9672/ 换线再试\n"
            "3) 提示 image/图片 400/403 → 是本地代理没起来，ext 填 img=direct\n"
            "4) 都不行 → 把这条【诊断】截图发群反馈")
    return {"page": page, "pagecount": page, "limit": SIZE, "total": 1, "list": [_diag_row(title, detail, hint)]}

def _parse_ext(text):
    conf = {}
    for chunk in re.split(r"[&\n;]+", str(text or "")):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            conf[key.strip().lower()] = value.strip()
        else:
            conf[chunk.lower()] = "1"
    return conf

def _month_str(back):
    now = datetime.datetime.now()
    year, month = now.year, now.month - back
    while month <= 0:
        month += 12
        year -= 1
    return "%04d-%02d" % (year, month)

class _Http(object):
    def __init__(self, conf):
        self.timeout = float(conf.get("timeout") or DEFAULT_TIMEOUT)
        self.ua = conf.get("ua") or DEFAULT_UA
        self.proxy = conf.get("proxy") or ""
        self.mode = (conf.get("net") or "auto").lower()

    def _targets(self):
        if self.mode == "direct" or not self.proxy:
            return [(False, "")]
        if self.mode == "proxy":
            return [(True, self.proxy)]
        return [(False, ""), (True, self.proxy)]

    def _headers(self, headers):
        merged = {"User-Agent": self.ua}
        if headers:
            merged.update(headers)
        return merged

    def post(self, url, data, headers=None):
        last = None
        for use_proxy, proxy in self._targets():
            try:
                payload = data.encode("utf-8") if isinstance(data, str) else (data or b"")
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                if use_proxy:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                        urllib.request.HTTPSHandler(context=ctx)
                    )
                else:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({}),
                        urllib.request.HTTPSHandler(context=ctx)
                    )
                request = urllib.request.Request(url, data=payload, headers=self._headers(headers), method="POST")
                with opener.open(request, timeout=self.timeout) as handle:
                    return getattr(handle, "status", 200) or 200, handle.read()
            except Exception as error:
                last = error
        raise last if last else RuntimeError("request failed")

    def post_quiet(self, url, data, headers=None):
        try:
            return self.post(url, data, headers)
        except Exception:
            return 0, b""

    def get(self, url, headers=None):
        last = None
        for use_proxy, proxy in self._targets():
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                if use_proxy:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                        urllib.request.HTTPSHandler(context=ctx)
                    )
                else:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({}),
                        urllib.request.HTTPSHandler(context=ctx)
                    )
                request = urllib.request.Request(url, headers=self._headers(headers), method="GET")
                with opener.open(request, timeout=self.timeout) as handle:
                    return getattr(handle, "status", 200) or 200, handle.read()
            except Exception as error:
                last = error
        raise last if last else RuntimeError("request failed")

class _LocalImageServer(object):
    def __init__(self, spider):
        self._spider = spider
        self._server = None
        self._port = 0
        self._base = ""
        self._lock = None
        try:
            import threading
            self._lock = threading.RLock()
        except Exception:
            self._lock = None

    def base(self):
        if self._base:
            return self._base
        if self._lock is not None:
            with self._lock:
                if self._base:
                    return self._base
                return self._start()
        return self._start()

    def _start(self):
        try:
            import http.server
            import socketserver
            import threading
        except Exception:
            return ""
        spider = self._spider

        class _Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _reply(self, status, kind, payload):
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", kind)
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "max-age=600")
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception:
                    pass

            def do_GET(self):
                try:
                    query = urllib.parse.urlparse(self.path).query
                    params = urllib.parse.parse_qs(query)
                    url = (params.get("url") or [""])[0]
                    sign = (params.get("k") or [""])[0]
                except Exception:
                    self._reply(400, "text/plain", b"bad request")
                    return
                if not url.startswith(("http://", "https://")) or not sign or sign != spider._sign(url):
                    self._reply(403, "text/plain", b"not allowed")
                    return
                try:
                    status, raw = spider._img_get(url)
                except Exception:
                    status, raw = 0, b""
                if status >= 400 or not raw:
                    self._reply(502, "text/plain", b"upstream unavailable")
                    return
                try:
                    content = _decrypt_one_image(raw)
                except Exception:
                    content = b""
                for candidate in (content, raw):
                    if not candidate:
                        continue
                    kind = _image_kind(candidate, loose=(candidate is raw))
                    if kind:
                        self._reply(200, kind, candidate)
                        return
                self._reply(502, "text/plain", b"image decode failed")

        class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        for port in range(LOCAL_PORT_START, LOCAL_PORT_START + 40):
            try:
                server = _Threaded(("127.0.0.1", port), _Handler)
            except Exception:
                continue
            try:
                thread = threading.Thread(target=server.serve_forever)
                thread.daemon = True
                thread.start()
            except Exception:
                try:
                    server.server_close()
                except Exception:
                    pass
                continue
            self._server = server
            self._port = port
            self._base = "http://127.0.0.1:%d/img" % port
            return self._base
        return ""

class Spider(BaseSpider):
    NAME = "ZakaTV"

    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self.extend = ""
        self._conf = {}
        self._http = _Http({})
        self._ready = False
        self._fail_at = 0.0
        self._last_error = ""
        self._config = None
        self._token = ""
        self._hosts = {}
        self._line = ""
        self._base = ""
        self._cache = {}
        self._img_server = None
        self._lock = None
        try:
            import threading
            self._lock = threading.RLock()
        except Exception:
            self._lock = None

    def init(self, extend=""):
        self.extend = extend or ""
        self._conf = _parse_ext(self.extend)
        self._http = _Http(self._conf)
        self._ready = False
        self._fail_at = 0.0
        self._last_error = ""
        self._line = ""
        self._base = ""
        self._cache = {}

    def destroy(self):
        self._cache = {}
        self._img_server = None

    def getDependence(self):
        return []

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def liveContent(self):
        return {}

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u

    def _cooldown(self):
        try:
            return float(self._conf.get("cooldown") or 20)
        except Exception:
            return 20.0

    def _months(self):
        try:
            return max(0, int(self._conf.get("months") or 12))
        except Exception:
            return 12

    def _cache_get(self, key, ttl):
        hit = self._cache.get(key)
        if hit and ttl and time.time() - hit[0] < ttl:
            return hit[1]
        return None

    def _cache_put(self, key, value):
        self._cache[key] = (time.time(), value)

    def _ensure_ready(self):
        if self._ready:
            return ""
        if self._fail_at and time.time() - self._fail_at < self._cooldown():
            return self._last_error or "初始化失败"
        try:
            self._bootstrap()
            self._ready = True
            self._fail_at = 0.0
            self._last_error = ""
            return ""
        except Exception as error:
            self._last_error = "初始化失败: %s" % _clean(type(error).__name__ + " " + str(error), 120)
            self._fail_at = time.time()
            return self._last_error

    def _bootstrap(self):
        lines = list(BOOTSTRAP_LINES)
        pinned = self._conf.get("line")
        if pinned:
            lines = [pinned] + [line for line in lines if line != pinned]
        if self._line:
            lines = [self._line] + [line for line in lines if line != self._line]
        last = None
        for line in lines:
            if not line:
                continue
            status, body = self._http.post_quiet(
                line.rstrip("/") + "/box/api/config?channel=Channel",
                None,
                {"Content-Type": "application/x-www-form-urlencoded"}
            )
            try:
                if status >= 400 or not body:
                    raise RuntimeError("line HTTP %s" % status)
                config = self._decode_box(body)
                if not isinstance(config.get("data"), dict):
                    raise ValueError("invalid config shape")
                self._config = config
                self._token = next(item["token"] for item in config["data"].get("token", []) if item.get("name") == "token_one")
                self._hosts = {item.get("name"): item.get("host", "") for item in config["data"].get("api", []) if isinstance(item, dict)}
                self._line = line
                return
            except Exception as error:
                last = error
        raise RuntimeError(type(last).__name__ if last else "bootstrap unavailable")

    @staticmethod
    def _decode_box(body):
        raw = _unpad(_aes(body, BOX_KEY, BOX_IV, decrypt=True))
        return json.loads(zlib.decompress(raw).decode("utf-8"))

    def _one_headers(self):
        timestamp = str(int(time.time()))
        uuid = getattr(self, "_uuid", None) or "48b067ec-6cfd-3491-84f5-023eb1e7d562"
        user_key = getattr(self, "_user_key", None) or "563e8eeef42931cc858dc0d1080f4f6f"
        platform = "3"
        ip = "0.0.0.0"
        first = hashlib.md5(".".join((ip, platform, timestamp, user_key, uuid)).encode()).hexdigest()
        sign = hashlib.md5((first + ONE_SIGN_SUFFIX).encode()).hexdigest()
        return {
            "ip": ip,
            "uuid": uuid,
            "timestamp": timestamp,
            "platform": platform,
            "token": self._token,
            "sign": sign,
            "user-key": user_key,
            "app-version": "2.6.3.1",
            "Content-Type": "application/x-www-form-urlencoded"
        }

    def _bases(self):
        primary = self._hosts.get("one") or ONE_API
        pool = [primary, self._base] + list(ONE_MIRRORS)
        out = []
        for base in pool:
            if base and base not in out:
                out.append(base)
        return out[:3]

    def _request(self, endpoint, params, ttl=0):
        key = endpoint + "|" + "&".join("%s=%s" % (name, params[name]) for name in sorted(params))
        if ttl:
            hit = self._cache_get(key, ttl)
            if hit is not None:
                return hit
        query = "&".join("%s=%s" % (name, params[name]) for name in sorted(params))
        payload = base64.b64encode(_aes(query.encode("utf-8"), ONE_KEY, ONE_IV)).decode()
        errors = []
        for base in self._bases():
            try:
                status, body = self._http.post(base.rstrip("/") + "/" + endpoint.lstrip("/"), payload, self._one_headers())
                text = body.decode("utf-8", "ignore").strip() if isinstance(body, (bytes, bytearray)) else str(body or "").strip()
                if status >= 400:
                    raise RuntimeError("HTTP %s" % status)
                if text.startswith("{"):
                    info = json.loads(text)
                    raise RuntimeError("服务端 %s: %s" % (info.get("code"), _clean(info.get("message"), 80)))
                decoded = json.loads(_unpad(_aes(base64.b64decode(text), ONE_KEY, ONE_IV, decrypt=True)).decode("utf-8"))
                if isinstance(decoded, dict) and decoded.get("code") not in (None, 0, 200):
                    raise RuntimeError("服务端 %s: %s" % (decoded.get("code"), _clean(decoded.get("message"), 80)))
                self._base = base
                if ttl:
                    self._cache_put(key, decoded)
                return decoded
            except Exception as error:
                errors.append("%s %s" % (base.split("//")[-1].rstrip("/").split("/")[0], _clean(type(error).__name__ + " " + str(error), 70)))
        raise RuntimeError(" | ".join(errors))

    def _one_url(self, name, path):
        prefix = self._hosts.get(name) or ""
        if not prefix:
            prefix = self._hosts.get("one") or ONE_API
        if not prefix:
            return ""
        return urllib.parse.urljoin(prefix, str(path).lstrip("/"))

    def _img_mode(self):
        return (self._conf.get("img") or "proxy").strip().lower()

    def _sign(self, url):
        try:
            return hashlib.md5(("one-img|" + str(url) + "|" + PROXY_SALT).encode()).hexdigest()[:16]
        except Exception:
            return ""

    def _proxy_base(self):
        mode = self._img_mode()
        if mode in ("local", "self", "server"):
            return self._local_base()
        base = ""
        try:
            base = self.getProxyUrl() or ""
        except Exception:
            base = ""
        if base:
            return base
        if mode in ("shell", "proxyshell"):
            return ""
        return self._local_base()

    def _local_base(self):
        try:
            if self._img_server is None:
                self._img_server = _LocalImageServer(self)
            return self._img_server.base()
        except Exception:
            self._img_server = None
            return ""

    def _proxy_url(self, url):
        if not url:
            return url
        if self._img_mode() in ("direct", "0", "off", "raw"):
            return url
        base = self._proxy_base()
        if not base:
            return url
        separator = "&" if "?" in base else "?"
        return base + separator + "url=" + urllib.parse.quote(url, safe="") + "&k=" + self._sign(url)

    def _pic(self, url):
        if not url:
            return ""
        return url if self._img_mode() in ("direct", "0", "off", "raw") else self._proxy_url(url)

    def _img_get(self, url):
        try:
            seconds = float(self._conf.get("imgtimeout") or 15)
        except Exception:
            seconds = 15.0
        headers = {"User-Agent": self._http.ua}
        last = None
        for use_proxy, proxy in self._http._targets():
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                if use_proxy:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                        urllib.request.HTTPSHandler(context=ctx)
                    )
                else:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({}),
                        urllib.request.HTTPSHandler(context=ctx)
                    )
                request = urllib.request.Request(url, headers=headers, method="GET")
                with opener.open(request, timeout=seconds) as handle:
                    return getattr(handle, "status", 200) or 200, handle.read()
            except Exception as error:
                last = error
        raise last if last else RuntimeError("img request failed")

    def _item(self, item):
        media = _choose_media(item)
        cover = item.get("thumb") or item.get("thumbnail") or ""
        if cover and not str(cover).startswith(("http://", "https://")):
            cover = self._one_url("one_img", cover)
        cover = self._pic(cover)
        playable = bool(media and not _looks_preview(media[1]))
        dur = _clean(item.get("video_length"), 20)
        remarks = "ZakaTV | %s" % dur if dur else "ZakaTV"
        return {
            "vod_id": str(item.get("id", "")),
            "vod_name": _clean(item.get("title"), 80),
            "vod_pic": cover,
            "vod_remarks": remarks,
            "vod_year": _clean(item.get("published_at"), 4),
            "vod_director": "📺ZakaTV",
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_content": "【官方TG群: https://t.me/+3t5XRPPo9mlkZDRl ZakaTV交流圈】\n" + _clean(item.get("description")),
            "vod_play_from": "One" if playable else "",
            "vod_play_url": "正片$" + str(item.get("id")) if playable else "",
            "style": {"type": "rect", "ratio": 1.78}
        }

    def _series_item(self, item, kind):
        cover = item.get("thumb") or item.get("thumbnail") or ""
        if cover and not str(cover).startswith(("http://", "https://")):
            cover = self._one_url("one_img", cover)
        cover = self._pic(cover)
        vid = ("m:" if kind == "manga" else "a:") + str(item.get("id", ""))
        latest = _clean(item.get("latest_at"), 10)
        remarks = "ZakaTV | %s" % latest if latest else "ZakaTV"
        author_text = _clean(item.get("author"), 40)
        actor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl | %s" % author_text if author_text else "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        return {
            "vod_id": vid,
            "vod_name": _clean(item.get("title"), 80),
            "vod_pic": cover,
            "vod_remarks": remarks,
            "vod_year": _clean(item.get("first_at"), 4),
            "vod_director": "📺ZakaTV",
            "vod_actor": actor,
            "vod_content": "【官方TG群: https://t.me/+3t5XRPPo9mlkZDRl ZakaTV交流圈】\n作者: %s" % author_text,
            "vod_play_from": "漫画" if kind == "manga" else "写真",
            "vod_play_url": "全篇$%s" % vid,
            "style": {"type": "rect", "ratio": 1.78}
        }

    def homeContent(self, filter):
        classes = [{"type_id": key, "type_name": FILM_FILTERS[key]} for key in FILM_ORDER]
        return {"class": classes, "filters": {}, "list": []}

    def homeVideoContent(self):
        try:
            error = self._ensure_ready()
            if error:
                return {"list": []}
            model, tag = (int(part) for part in FILM_ORDER[3].split("_"))
            result = self._request(
                "v2.5/article/discovery",
                {"demand_tag_id": tag, "model_id": model, "page": 1, "published_at": _month_str(0), "size": SIZE, "sort": "published_at"},
                ttl=300
            )
            items = result.get("data", []) if isinstance(result, dict) else []
            rows, seen = [], set()
            for item in items:
                identity = item.get("id")
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(self._item(item))
            return {"list": rows}
        except Exception:
            return {"list": []}

    def _month_pages(self, model, tag, month, cap=8):
        key = "mp|%s|%s|%s" % (model, tag, month)
        hit = self._cache_get(key, 1800)
        if hit is not None:
            return hit
        pages = 0
        page = 1
        while page <= cap:
            try:
                result = self._request(
                    "v2.5/article/discovery",
                    {"demand_tag_id": tag, "model_id": model, "page": page, "published_at": month, "size": SIZE, "sort": "published_at"}
                )
            except Exception:
                if page == 1:
                    raise
                break
            items = result.get("data", []) if isinstance(result, dict) else []
            if not items:
                break
            pages += 1
            if len(items) < SIZE:
                break
            page += 1
        self._cache_put(key, pages)
        return pages

    def _flat_page(self, model, tag, page):
        months = self._months()
        acc = 0
        back = 0
        blank_run = 0
        limit = months if months else 240
        while back < limit:
            month = _month_str(back)
            pages = self._month_pages(model, tag, month)
            if pages:
                blank_run = 0
                if page <= acc + pages:
                    inner = page - acc
                    result = self._request(
                        "v2.5/article/discovery",
                        {"demand_tag_id": tag, "model_id": model, "page": inner, "published_at": month, "size": SIZE, "sort": "published_at"},
                        ttl=300
                    )
                    items = result.get("data", []) if isinstance(result, dict) else []
                    if items:
                        return items, back, inner
                    return None
                acc += pages
            else:
                blank_run += 1
                if acc and blank_run >= 3:
                    return None
            back += 1
        return None

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        error = self._ensure_ready()
        if error:
            return _diag_page(page, "源未就绪", error)
        demand_tag_id = str(tid)
        if demand_tag_id not in FILM_FILTERS:
            demand_tag_id = FILM_ORDER[0]
        try:
            if demand_tag_id in ("manga", "album"):
                endpoint = "v2.5/series/manga/list" if demand_tag_id == "manga" else "v2.5/series/album/list"
                result = self._request(endpoint, {"page": page, "size": SIZE}, ttl=300)
                items = result.get("data", []) if isinstance(result, dict) else []
                rows = [self._series_item(item, demand_tag_id) for item in items if isinstance(item, dict) and item.get("id")]
                return {"page": page, "pagecount": page + 1 if len(rows) >= SIZE else page, "limit": SIZE, "total": len(rows), "list": rows}
            model, tag = (int(part) for part in demand_tag_id.split("_"))
        except Exception as error:
            return _diag_page(page, "分类参数不对", "%s %s" % (type(error).__name__, error))
        try:
            found = self._flat_page(model, tag, page)
            if not found:
                return {"page": page, "pagecount": page, "limit": SIZE, "total": 0, "list": []}
            items = found[0]
            seen, rows = set(), []
            for item in items:
                identity = item.get("id")
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(self._item(item))
            try:
                has_next = bool(self._flat_page(model, tag, page + 1))
            except Exception:
                has_next = True
            return {"page": page, "pagecount": page + 1 if has_next else page, "limit": SIZE, "total": len(rows), "list": rows}
        except Exception as error:
            return _diag_page(page, "列表拉取失败", "%s %s" % (type(error).__name__, error))

    def detailContent(self, ids):
        error = self._ensure_ready()
        if error:
            return {"list": [self._diag_row("源未就绪", error, "ext 可填 line= 换引导线路")]}
        try:
            raw = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
            kind = ""
            if raw.startswith(("m:", "a:")):
                kind = raw[:1]
                raw = raw[2:]
            item_id = int(raw)
            if kind:
                result = self._request("v2.5/series/chapters", {"series_id": item_id}, ttl=900)
                data = result.get("data") or {}
                chapters = (data.get("chapters") or []) if isinstance(data, dict) else []
                cover = data.get("thumb") or ""
                if cover and not str(cover).startswith(("http://", "https://")):
                    cover = self._one_url("one_img", cover)
                cover = self._pic(cover)
                play_url = "#".join("%s$%s" % (_clean(chapter.get("title") or "第%s话" % chapter.get("chapter", ""), 40), chapter.get("id")) for chapter in chapters if chapter.get("id"))
                author_text = _clean(data.get("author"), 40)
                actor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl | %s" % author_text if author_text else "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
                detail = {
                    "vod_id": raw,
                    "vod_name": _clean(data.get("title"), 80),
                    "vod_pic": cover,
                    "vod_year": _clean(data.get("first_at"), 4),
                    "vod_area": "",
                    "vod_class": "",
                    "vod_director": "📺ZakaTV",
                    "vod_actor": actor,
                    "vod_content": "【官方TG群: https://t.me/+3t5XRPPo9mlkZDRl ZakaTV交流圈】\n" + _clean(data.get("description")),
                    "vod_remarks": "ZakaTV · 共%d话" % len(chapters),
                    "vod_play_from": "漫画" if kind == "m" else "写真",
                    "vod_play_url": play_url,
                    "style": {"type": "rect", "ratio": 1.78}
                }
                return {"list": [detail]}
            result = self._request("v2.5/article/detail", {"id": item_id}, ttl=900)
            item = result.get("data", {}) if isinstance(result, dict) else {}
            if not isinstance(item, dict):
                item = {}
            media = _choose_media(item)
            if media:
                play_entries = [("正片", item_id)]
            elif self._poster_images(item) or self._series_pics(item):
                play_entries = [("图集", item_id)]
            else:
                play_entries = []
            series_id = item.get("series_id") or item.get("series")
            if series_id:
                try:
                    data = self._request("v2.5/series/chapters", {"series_id": int(series_id)}, ttl=900).get("data") or {}
                    chapters = data.get("chapters") or [] if isinstance(data, dict) else []
                    entries = [(_clean(chapter.get("title") or "第%s集" % chapter.get("chapter", ""), 40), chapter.get("id")) for chapter in chapters if chapter.get("id")]
                    if entries:
                        play_entries = entries
                except Exception:
                    pass
            play_url = "#".join("%s$%s" % (title, chapter_id) for title, chapter_id in play_entries)
            detail = self._item(item)
            detail.update({
                "vod_id": str(item_id),
                "vod_play_from": "One" if media else ("图集" if play_entries else ""),
                "vod_play_url": play_url
            })
            return {"list": [detail]}
        except Exception as error:
            return {"list": [self._diag_row("详情请求失败", "%s %s" % (type(error).__name__, error), "换个分类再点一次；还不行截图发群反馈")]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        error = self._ensure_ready()
        if error:
            return _diag_page(page, "源未就绪", error)
        try:
            result = self._request("v2.5/article/search", {"keyword": str(key), "page": page, "size": SIZE}, ttl=180)
            items = result.get("data", []) if isinstance(result, dict) else []
            seen, rows = set(), []
            for item in items:
                if not isinstance(item, dict):
                    continue
                identity = item.get("id")
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(self._item(item))
            return {"list": rows, "page": page, "pagecount": page + 1 if len(rows) >= SIZE else page, "limit": SIZE, "total": len(rows)}
        except Exception as error:
            return _diag_page(page, "搜索失败", "%s %s" % (type(error).__name__, error))

    def _poster_images(self, item):
        content = item.get("content") or item.get("description") or ""
        urls = []
        for src in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', str(content)):
            if not src:
                continue
            urls.append(src if src.startswith(("http://", "https://")) else self._one_url("one_img", src))
        return [url for url in urls if url]

    def _series_pics(self, item):
        urls = []
        for field in ("multiple_pic", "multi_pic_thumbnail800", "multi_pic_thumbnail"):
            value = item.get(field)
            if not value:
                continue
            rows = None
            if isinstance(value, (list, tuple)):
                rows = list(value)
            elif isinstance(value, str) and value.strip().startswith("["):
                try:
                    parsed = ast.literal_eval(value.strip())
                    if isinstance(parsed, (list, tuple)):
                        rows = list(parsed)
                except Exception:
                    rows = None
            if not rows:
                continue
            for rel in rows:
                if not isinstance(rel, str) or not rel:
                    continue
                url = rel if rel.startswith(("http://", "https://")) else self._one_url("one_img", rel)
                if url and url not in urls:
                    urls.append(url)
            if urls:
                break
        return urls

    def _pics(self, item):
        urls = self._poster_images(item)
        if not urls:
            urls = self._series_pics(item)
        if not urls:
            return ""
        packed = "&&".join(self._pic(url) for url in urls if url)
        return "pics://" + packed if packed else ""

    def playerContent(self, flag, id, vipFlags=None):
        error = self._ensure_ready()
        if error:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}, "error": error}
        try:
            raw = str(id).split("$")[-1].strip()
            if raw.startswith(("m:", "a:")):
                raw = raw[2:]
            item_id = int(raw)
            result = self._request("v2.5/article/detail", {"id": item_id}, ttl=900)
            item = result.get("data", {}) if isinstance(result, dict) else {}
            if not isinstance(item, dict):
                item = {}
            header = {"User-Agent": self._http.ua}
            if self._conf.get("playref") == "1":
                ref = (self._hosts.get("one") or ONE_API)
                header["Referer"] = ref
                header["Origin"] = ref.rstrip("/")
            media = _choose_media(item, strict=self._conf.get("strict") == "1")
            want_pics = (self._conf.get("pics") == "1") or not media or (self._conf.get("vfirst") or "1").strip() in ("0", "img", "pics", "off")
            if (not want_pics) and media:
                field, path = media
                url = self._one_url("one_video", path)
                if url:
                    return {"parse": 0, "playUrl": "", "url": url, "header": header, "media_field": field}
            pics = self._pics(item)
            if pics:
                return {"parse": 0, "playUrl": "", "url": pics, "header": header}
            if media:
                field, path = media
                url = self._one_url("one_video", path)
                if url:
                    return {"parse": 0, "playUrl": "", "url": url, "header": header, "media_field": field}
            return {"parse": 0, "playUrl": "", "url": "", "header": {}, "error": "无已证实正片源，未将试看或预览标为正片"}
        except Exception as error:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}, "error": "%s %s" % (type(error).__name__, error)}

    def _allowed_hosts(self):
        hosts = set()
        for name in ("one_img", "one_video"):
            netloc = urllib.parse.urlparse(self._hosts.get(name) or "").netloc.lower()
            if netloc:
                hosts.add(netloc.split(":")[0])
        for extra in str(self._conf.get("host") or "").split(","):
            extra = extra.strip().lower()
            if extra:
                hosts.add(extra.split(":")[0])
        return hosts

    def localProxy(self, param):
        if not isinstance(param, dict):
            return [400, "text/plain", b"invalid proxy parameters"]
        url = param.get("url", "")
        if isinstance(url, str) and not url.startswith(("http://", "https://")):
            try:
                decoded = urllib.parse.unquote(url)
                if decoded.startswith(("http://", "https://")):
                    url = decoded
            except Exception:
                pass
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return [400, "text/plain", b"invalid proxy URL"]
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.username or parsed.password or parsed.fragment:
                return [400, "text/plain", b"proxy url is not allowed"]
            signature = param.get("k") or ""
            if not (signature and signature == self._sign(url)):
                allowed = self._allowed_hosts()
                if not allowed and not self._hosts:
                    self._ensure_ready()
                    allowed = self._allowed_hosts()
                if not allowed or (parsed.hostname or "").lower() not in allowed:
                    return [403, "text/plain", b"proxy host is not allowed"]
            status, raw = self._img_get(url)
            if status >= 400 or not raw:
                return [502, "text/plain", ("proxy upstream HTTP %s" % status).encode()]
            try:
                content = _decrypt_one_image(raw)
            except Exception:
                content = b""
            for candidate in (content, raw):
                if not candidate:
                    continue
                kind = _image_kind(candidate, loose=(candidate is raw))
                if kind:
                    return [200, kind, candidate]
            return [502, "text/plain", b"proxy image integrity check failed"]
        except Exception as error:
            return [502, "text/plain", ("proxy error: " + type(error).__name__).encode()]
