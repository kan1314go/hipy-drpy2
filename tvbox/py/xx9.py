# -*- coding: utf-8 -*-
import sys
import json
import time
import base64
import ssl
import gzip
import zlib
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"
        def getProxyUrl(self): return "http://127.0.0.1:9978/proxy?do=py"

_AES_SBOX = (
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
)
_AES_INV_SBOX = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_v] = _i
_AES_INV_SBOX = tuple(_AES_INV_SBOX)
_AES_RCON = (0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36)

def _aes_xtime(a):
    return (((a << 1) ^ 0x1b) & 0xff) if (a & 0x80) else ((a << 1) & 0xff)

def _aes_gmul(a, b):
    p = 0
    while b:
        if b & 1:
            p ^= a
        a = _aes_xtime(a)
        b >>= 1
    return p

_AES_M09 = tuple(_aes_gmul(i, 0x09) for i in range(256))
_AES_M0B = tuple(_aes_gmul(i, 0x0b) for i in range(256))
_AES_M0D = tuple(_aes_gmul(i, 0x0d) for i in range(256))
_AES_M0E = tuple(_aes_gmul(i, 0x0e) for i in range(256))

_AES_M02 = tuple(_aes_xtime(i) for i in range(256))
_AES_M03 = tuple(_aes_xtime(i) ^ i for i in range(256))

def _aes_expand_key(key):
    ek = list(key)
    for i in range(10):
        t = ek[-4:]
        t = t[1:] + t[:1]
        t = [_AES_SBOX[b] for b in t]
        t[0] ^= _AES_RCON[i]
        for _j in range(4):
            t = [t[k] ^ ek[-16+k] for k in range(4)]
            ek += t
    return [ek[i:i+16] for i in range(0, 176, 16)]

def _aes_encrypt_block(blk, rk):
    s = [a ^ b for a, b in zip(blk, rk[0])]
    for r in range(1, 10):
        s = [_AES_SBOX[b] for b in s]
        s = [s[0],s[5],s[10],s[15],s[4],s[9],s[14],s[3],s[8],s[13],s[2],s[7],s[12],s[1],s[6],s[11]]
        o = [0] * 16
        for c in range(4):
            a0, a1, a2, a3 = s[c*4], s[c*4+1], s[c*4+2], s[c*4+3]
            o[c*4]   = _AES_M02[a0] ^ _AES_M03[a1] ^ a2 ^ a3
            o[c*4+1] = a0 ^ _AES_M02[a1] ^ _AES_M03[a2] ^ a3
            o[c*4+2] = a0 ^ a1 ^ _AES_M02[a2] ^ _AES_M03[a3]
            o[c*4+3] = _AES_M03[a0] ^ a1 ^ a2 ^ _AES_M02[a3]
        s = [a ^ b for a, b in zip(o, rk[r])]
    s = [_AES_SBOX[b] for b in s]
    s = [s[0],s[5],s[10],s[15],s[4],s[9],s[14],s[3],s[8],s[13],s[2],s[7],s[12],s[1],s[6],s[11]]
    return bytes(a ^ b for a, b in zip(s, rk[10]))

def _aes_decrypt_block(blk, rk):
    s = [a ^ b for a, b in zip(blk, rk[10])]
    for r in range(9, 0, -1):
        s = [s[0],s[13],s[10],s[7],s[4],s[1],s[14],s[11],s[8],s[5],s[2],s[15],s[12],s[9],s[6],s[3]]
        s = [_AES_INV_SBOX[b] for b in s]
        s = [a ^ b for a, b in zip(s, rk[r])]
        o = [0] * 16
        for c in range(4):
            a0, a1, a2, a3 = s[c*4], s[c*4+1], s[c*4+2], s[c*4+3]
            o[c*4]   = _AES_M0E[a0] ^ _AES_M0B[a1] ^ _AES_M0D[a2] ^ _AES_M09[a3]
            o[c*4+1] = _AES_M09[a0] ^ _AES_M0E[a1] ^ _AES_M0B[a2] ^ _AES_M0D[a3]
            o[c*4+2] = _AES_M0D[a0] ^ _AES_M09[a1] ^ _AES_M0E[a2] ^ _AES_M0B[a3]
            o[c*4+3] = _AES_M0B[a0] ^ _AES_M0D[a1] ^ _AES_M09[a2] ^ _AES_M0E[a3]
        s = o
    s = [s[0],s[13],s[10],s[7],s[4],s[1],s[14],s[11],s[8],s[5],s[2],s[15],s[12],s[9],s[6],s[3]]
    s = [_AES_INV_SBOX[b] for b in s]
    return bytes(a ^ b for a, b in zip(s, rk[0]))

class PureAesEcb(object):
    def __init__(self, key):
        self.rk = _aes_expand_key(key)

    def encrypt(self, data):
        out = bytearray()
        for i in range(0, len(data), 16):
            out += _aes_encrypt_block(data[i:i+16], self.rk)
        return bytes(out)

    def decrypt(self, data):
        out = bytearray()
        for i in range(0, len(data), 16):
            out += _aes_decrypt_block(data[i:i+16], self.rk)
        return bytes(out)

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = clean_meta.replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(BaseSpider):
    GATEWAY_POOL = [
        "https://pl5kjl.jas49cht5sqrwet.xyz/fast-endecode/main/request",
        "https://pl5kjl.m93abv5upsv4s8f.xyz/fast-endecode/main/request",
        "https://api.y7hvaad8g.xyz/fast-endecode/main/request",
    ]

    KEYS = {
        0: "G7i3OPcfNhBnAYpc",
        1: "84UZNK33cSVylz6Y",
        2: "jeSWRcTwHyAKwJDB",
        3: "i1hvJx9vuRt5zEBS",
        4: "1Yy1KOa75R7cnmkg",
        6: "T0RVp7KIPamrtQ33",
        8: "ugvseZc5Kkj8ecmV",
        9: "G7i3OPcfNhBnAYpc",
    }
    REM = 2
    ADS_CODE = "DFH"

    PLAY_LINES = [
        ("国线1", "https://rr.rxjhwl.com"),
        ("国线2", "https://ww.wealwelloa.com"),
        ("国线3", "https://cc.cloudworki.com"),
        ("国线4", "https://gg.gmdalian.com"),
        ("海线1", "https://allmusiclub.almusiclub.com"),
    ]

    PIC_BASE = "https://qv1tx2.shoupingxz.com"
    UA = "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

    THEMES = [
        ("27", "国产精选"), ("9", "主播剧情"), ("26", "业余素人"),
        ("47", "第一视角"), ("7", "欧美精选"), ("35", "日韩精选"),
        ("41", "粉嫩处女"), ("66", "偷窥偷拍监控"), ("50", "网爆偷拍泄密"),
        ("39", "AV精选"), ("40", "职业探花"), ("55", "网红裸舞"),
        ("59", "抖音风合集"), ("36", "动漫精选"), ("67", "街拍街射"),
        ("42", "明星AI换脸"), ("15", "经典老片"), ("16", "成人综艺"),
        ("24", "恐怖科幻伦理"), ("19", "官方推荐"),
    ]

    def __init__(self):
        super(Spider, self).__init__()
        self._jwt = None
        self._jwt_ts = 0
        self._access = None
        self._access_ts = 0
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self.ctx))

    def init(self, extend=""):
        self._jwt = None
        self._jwt_ts = 0
        self._access = None
        self._access_ts = 0
        return True

    def getName(self):
        return "xx9"

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".ts", "index.png"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._jwt = None
        self._access = None

    def liveContent(self):
        return ""

    def action(self, action):
        return {"msg": "ok"}

    def _rnd(self, n):
        import random
        cs = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        return "".join(random.choice(cs) for _ in range(n))

    def _pad(self, b):
        n = 16 - (len(b) % 16)
        return b + bytes([n]) * n

    def _unpad(self, b):
        if not b:
            return b
        pad = b[-1]
        if 1 <= pad <= 16 and bytes(b[-pad:]) == bytes([pad]) * pad:
            return b[:-pad]
        return b

    def _enc(self, obj, key):
        raw = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        c = PureAesEcb(key.encode('utf-8'))
        return base64.b64encode(c.encrypt(self._pad(raw))).decode('utf-8')

    def _dec(self, b64, key):
        c = PureAesEcb(key.encode('utf-8'))
        raw = self._unpad(c.decrypt(base64.b64decode(b64)))
        return raw.decode('utf-8', errors='ignore')

    def _mktime(self):
        t = int(time.time() * 1000)
        return t - (t % 10) + self.REM

    def _http_request(self, url, data=None, headers=None, timeout=6):
        req_headers = {
            "User-Agent": self.UA,
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=data, headers=req_headers)
        with self.opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
            if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                raw = gzip.decompress(raw)
            elif enc == "deflate":
                try:
                    raw = zlib.decompress(raw)
                except Exception:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            return raw

    def _call(self, uri, method, params=None, body=None, use_jwt=True, use_access=False, _retry=True):
        key = self.KEYS[self.REM]
        t = self._mktime()
        plain = {"method": method, "uri": uri}
        if body is not None:
            plain["body"] = body
        else:
            plain["params"] = params if params is not None else {}
        payload = json.dumps({"data": self._enc(plain, key), "time": t}).encode('utf-8')
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.UA,
            "Origin": "https://xx9.com",
            "Referer": "https://xx9.com/",
        }
        if use_jwt:
            jwt = self._get_jwt()
            if jwt:
                headers["jwtToken"] = jwt
        if use_access:
            acc = self._get_access()
            if acc:
                headers["accessToken"] = acc

        text = None
        for gw in self.GATEWAY_POOL:
            try:
                raw_resp = self._http_request(gw, data=payload, headers=headers, timeout=6)
                text = raw_resp.decode('utf-8', errors='ignore')
                if text:
                    break
            except Exception:
                continue
        if not text:
            return {}
        try:
            j = json.loads(text)
        except Exception:
            return {}
        if isinstance(j, dict) and isinstance(j.get("data"), str) and j.get("data") and ("time" in j):
            try:
                j = json.loads(self._dec(j["data"], key))
            except Exception:
                return j
        if use_access and _retry and isinstance(j, dict):
            code = str(j.get("code") or "")
            if code in ("1032", "1019"):
                self._access = None
                self._access_ts = 0
                return self._call(uri, method, params=params, body=body,
                                  use_jwt=use_jwt, use_access=use_access, _retry=False)
        return j

    def _get_jwt(self):
        now = time.time()
        if self._jwt and (now - self._jwt_ts) < 3600:
            return self._jwt
        try:
            r = self._call("app/jwt-token", 1, params={"adsCode": self.ADS_CODE}, use_jwt=False)
            jwt = r.get("result") if isinstance(r, dict) else None
            if jwt:
                self._jwt = jwt
                self._jwt_ts = now
        except Exception:
            pass
        return self._jwt

    def _get_access(self):
        now = time.time()
        if self._access and (now - self._access_ts) < 1800:
            return self._access
        try:
            body = {
                "osType": "h5",
                "sign": self._rnd(32),
                "machineCode": "chrome",
                "version": "xx9.com",
            }
            r = self._call("user/register/free", 2, body=body, use_jwt=True, use_access=False)
            res = r.get("result") if isinstance(r, dict) else None
            acc = res.get("accessToken") if isinstance(res, dict) else None
            if acc:
                self._access = acc
                self._access_ts = now
        except Exception:
            pass
        return self._access

    def _abs_pic(self, p):
        if not p:
            return ""
        if p.startswith("http"):
            return p
        return self.PIC_BASE + p

    def _pic(self, p):
        u = self._abs_pic(p)
        if not u:
            return ""
        try:
            base = self.getProxyUrl()
        except Exception:
            base = None
        if not base:
            return u
        return base + "&url=" + quote(u, safe="") + "&type=img"

    def _vod_list_item(self, it):
        vid = it.get("id") or it.get("vodId")
        title = it.get("title") or ""
        pic = self._pic(it.get("vodPic") or it.get("gif") or "")
        dur = it.get("vodDuration")
        remark = ""
        if isinstance(dur, int) and dur > 0:
            m, s = divmod(dur, 60)
            remark = "%d:%02d" % (m, s)
        tags = it.get("tags")
        if not remark and isinstance(tags, list) and tags:
            remark = " ".join(tags[:3])
        return {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": format_remarks("ZakaTV", remark),
            "style": {"type": "rect", "ratio": 1.78}
        }

    def _search(self, params):
        r = self._call("cms/vod/search", 2, params=params)
        data = r.get("data") if isinstance(r, dict) else None
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("list") or data.get("records") or []
        total = r.get("total") if isinstance(r, dict) else 0
        return items, (total or 0)

    def homeContent(self, filter):
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.THEMES]
        result = {
            "class": classes
        }
        if filter:
            filters = {}
            sort_filter = {
                "key": "sort",
                "name": "排序",
                "value": [
                    {"n": "最新", "v": "1"},
                    {"n": "最热", "v": "2"},
                ],
            }
            for tid, _ in self.THEMES:
                filters[tid] = [sort_filter]
            result["filters"] = filters
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1
        sort_type = 1
        if isinstance(extend, dict):
            sv = extend.get("sort")
            if sv:
                try:
                    sort_type = int(sv)
                except Exception:
                    sort_type = 1
        page_size = 30
        items, total = self._search({
            "themeIds": str(tid),
            "page": page, "pageSize": page_size,
            "explore": False, "sortType": sort_type,
        })
        vod = [self._vod_list_item(it) for it in items]
        if not vod:
            return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}
        pagecount = 1
        if total:
            pagecount = (int(total) + page_size - 1) // page_size
        return {
            "list": vod,
            "page": page,
            "pagecount": pagecount,
            "limit": page_size,
            "total": int(total) if total else len(vod),
        }

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        r = self._call("cms/vod/detail/%s" % vid, 1, params={"needCdnAuth": True}, use_access=True)
        res = r.get("result") if isinstance(r, dict) else None
        if isinstance(res, dict):
            vod = res.get("vod", res)
        else:
            vod = res if isinstance(res, dict) else {}
        if not vod:
            return {"list": []}

        title = vod.get("title") or ""
        clean_pic = self._abs_pic(vod.get("vodPic") or "")
        proxy_pic = self._pic(vod.get("vodPic") or "")
        intro = vod.get("vodIntro") or ""
        tags = vod.get("tags")
        tag_str = ",".join(tags) if isinstance(tags, list) else ""
        dur = vod.get("vodDuration")
        remark = ""
        if isinstance(dur, int) and dur > 0:
            m, s = divmod(dur, 60)
            remark = "时长 %d:%02d" % (m, s)

        full = vod.get("vodFullPlayUrl")
        n_parts = len(full) if isinstance(full, list) and full else 1

        eps = []
        if n_parts <= 1:
            eps.append("正片$%s|0" % vid)
        else:
            for i in range(n_parts):
                eps.append("P%d$%s|%d" % (i + 1, vid, i))
        play_eps = "#".join(eps)

        froms = ["Zaka专线"]
        urls = [play_eps]
        for name, _domain in self.PLAY_LINES:
            froms.append(name)
            urls.append(play_eps)

        if intro:
            content_str = "📺ZakaTV专线直连 | %s | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl" % intro
        else:
            content_str = "📺ZakaTV专线加速播放 | 官方TG交流群：https://t.me/+3t5XRPPo9mlkZDRl | 4K高清原生极速画质"

        vod_obj = {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": proxy_pic,
            "vod_bg": clean_pic,
            "vod_background": clean_pic,
            "vod_banner": clean_pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("ZakaTV", remark),
            "vod_content": content_str,
            "vod_tag": tag_str,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        return {"list": [vod_obj]}

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        items, _ = self._search({
            "title": key,
            "page": page, "pageSize": 30,
            "explore": False, "sortType": 1,
        })
        return {"list": [self._vod_list_item(it) for it in items]}

    def playerContent(self, flag, id, vipFlags):
        vid = id
        idx = 0
        if "|" in id:
            vid, sidx = id.split("|", 1)
            try:
                idx = int(sidx)
            except Exception:
                idx = 0

        domain = None
        for name, dom in self.PLAY_LINES:
            if name == flag:
                domain = dom
                break
        if not domain:
            domain = self.PLAY_LINES[0][1]

        play_url = ""
        try:
            r = self._call("cms/vod/detail/%s" % vid, 1, params={"needCdnAuth": True}, use_access=True)
            res = r.get("result") if isinstance(r, dict) else None
            vod = res.get("vod", res) if isinstance(res, dict) else {}
            full = vod.get("vodFullPlayUrl")
            addr = None
            if isinstance(full, list) and full:
                if idx >= len(full):
                    idx = 0
                addr = full[idx].get("addr")
            if not addr:
                addr = vod.get("preview")
            if addr:
                play_url = domain + addr
        except Exception:
            play_url = ""

        if play_url and (".m3u8" not in play_url.lower()) and (".mp4" not in play_url.lower()):
            sep = "&" if "?" in play_url else "?"
            play_url = play_url + sep + "format=.m3u8"

        return {
            "parse": 0,
            "playUrl": "",
            "url": play_url,
            "header": {
                "User-Agent": self.UA,
                "Referer": "https://xx9.com/",
            },
        }

    def _img_mime(self, b):
        if not b or len(b) < 12:
            return None
        if b[:4] == b"\x89PNG":
            return "image/png"
        if b[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if b[:6] in (b"GIF89a", b"GIF87a"):
            return "image/gif"
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            return "image/webp"
        return None

    def localProxy(self, param):
        url = None
        if isinstance(param, dict):
            url = param.get("url")
        if url:
            try:
                url = unquote(url)
            except Exception:
                pass
        if not url:
            return [404, "text/plain", b""]
        headers = {
            "User-Agent": self.UA,
            "Referer": "https://xx9.com/",
        }
        try:
            raw = self._http_request(url, headers=headers, timeout=6)
            if not raw or len(raw) > 20971520:
                return [404, "text/plain", b""]
            mime = self._img_mime(raw)
            if mime:
                return [200, mime, raw]
            if len(raw) > 1:
                key = raw[0]
                table = bytes(i ^ key for i in range(256))
                img = raw[1:].translate(table)
                mime = self._img_mime(img)
                if mime:
                    return [200, mime, img]
            return [200, "image/jpeg", raw]
        except Exception:
            return [404, "text/plain", b""]