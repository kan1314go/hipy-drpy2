# -*- coding: utf-8 -*-
"""
37cyx4.com 源 v13（FongMi / OK影视 / 影视仓 Python 源）

数据链（全部匿名直连，A 类公开站，无破解）：
  分类      -> portal.instruno.com/public2/json/category-list.json（动态过滤 tbname=movie）
  列表      -> portal.instruno.com/public2/json/category/<id>-<page>.json
  详情      -> portal.instruno.com/public2/json/video/<id>.json
  首页      -> portal.instruno.com/public2/json/category/1-1.json（带封面）
  排行榜    -> portal.instruno.com/public2/json/top/top.json（day/week/moon 各 20）
  搜索      -> 37cyx4.com/api/v2/search?keyword=<AES密文>&classid=0&page=N
  播放      -> MP4 直链优先，其次 HLS（m3u8 相对路径拼 CDN 池）
  封面      -> *.txt 内容是 data:image/jpeg;base64,...，走 localProxy type=pic 解码

加密（来源：portal.instruno.com/public2/assets/EAOH2Se4SxGFayzB.js 的 $crypto provider）：
  AES-256-CBC / PKCS7
  Key = 22946bc50fd63164b79df55070a85a92
  IV  = kaixin1234567890
  输入输出均 URL-safe base64（+→- /→_ 去尾=）

v17 红线：
  单请求 timeout=4（补图专用 _json_api_fast 为 timeout=2 不重试）；
  无线程 join；do=py 代理一律经 _sk() 带 &siteKey=；
  未写 proxies；未写 [a=cr:...] 可点击标签。
"""
import sys, json, base64, re, time, threading
from urllib.parse import quote, unquote

try:
    import requests
except Exception:
    requests = None

try:
    from Crypto.Cipher import AES as _AES
    from Crypto.Util.Padding import pad as _pad, unpad as _unpad
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False


# ================= 纯 Python AES-256-CBC 兜底（壳内有 pycryptodome 时不使用） =================
_SBOX = bytes.fromhex(
"637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
"b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
"09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
"d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
"cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
"e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
"ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
"e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")
_INV = [0] * 256
for _i, _b in enumerate(_SBOX):
    _INV[_b] = _i
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40]


def _xt(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1)


def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xt(a)
        b >>= 1
    return r


def _expand(key):
    nk, nr = 8, 14
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[x] for x in t]
            t[0] ^= _RCON[i // nk - 1]
        elif i % nk == 4:
            t = [_SBOX[x] for x in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(nr + 1)], nr


def _dec_block(blk, rk, nr):
    s = [blk[i] ^ rk[nr][i] for i in range(16)]
    for r in range(nr - 1, -1, -1):
        s = [s[0], s[13], s[10], s[7], s[4], s[1], s[14], s[11],
             s[8], s[5], s[2], s[15], s[12], s[9], s[6], s[3]]
        s = [_INV[x] for x in s]
        s = [s[i] ^ rk[r][i] for i in range(16)]
        if r:
            ns = [0] * 16
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                ns[4 * c + 0] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
                ns[4 * c + 1] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
                ns[4 * c + 2] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
                ns[4 * c + 3] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)
            s = ns
    return bytes(s)


def _enc_block(blk, rk, nr):
    s = [blk[i] ^ rk[0][i] for i in range(16)]
    for r in range(1, nr + 1):
        s = [_SBOX[x] for x in s]
        s = [s[0], s[5], s[10], s[15], s[4], s[9], s[14], s[3],
             s[8], s[13], s[2], s[7], s[12], s[1], s[6], s[11]]
        if r != nr:
            ns = [0] * 16
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                ns[4 * c + 0] = _mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3]
                ns[4 * c + 1] = a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3]
                ns[4 * c + 2] = a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3)
                ns[4 * c + 3] = _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)
            s = ns
        s = [s[i] ^ rk[r][i] for i in range(16)]
    return bytes(s)


def _py_cbc_dec(key, iv, data):
    rk, nr = _expand(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        p = _dec_block(blk, rk, nr)
        out += bytes(a ^ b for a, b in zip(p, prev))
        prev = blk
    return bytes(out)


def _py_cbc_enc(key, iv, data):
    rk, nr = _expand(key)
    padn = 16 - (len(data) % 16)
    data = data + bytes([padn]) * padn
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        c = _enc_block(bytes(a ^ b for a, b in zip(data[i:i + 16], prev)), rk, nr)
        out += c
        prev = c
    return bytes(out)


# ================= 常量 =================
KEY = b"22946bc50fd63164b79df55070a85a92"
IV = b"kaixin1234567890"
SITE = "https://37cyx4.com"
JSON_BASE = "https://portal.instruno.com/public2/json"
UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

CDN_DEFAULT = ["https://m3u8.41cdn.com", "https://m3u8.44cdn.com", "https://m3u8.46cdn.com",
               "https://m3u8.47cdn.com", "https://m3u8.48cdn.com", "https://m3u8.34cdn.com"]
CDN_ACTOR = ["https://m3u8.73cdn.com", "https://m3u8.74cdn.com"]
CDN_SELF = ["https://publices.ttjkbx.com"]

# category-list.json 拉取失败时的兜底（只放已实测有数据的 movie 分类）
DEFAULT_CLASS = [
    {"type_id": "1", "type_name": "国产"},
    {"type_id": "4", "type_name": "自拍视频"},
    {"type_id": "5", "type_name": "淫妻作乐"},
    {"type_id": "6", "type_name": "开放青年"},
    {"type_id": "8", "type_name": "网红主播"},
    {"type_id": "9", "type_name": "手机视频"},
    {"type_id": "28", "type_name": "女优"},
    {"type_id": "37", "type_name": "电影"},
    {"type_id": "38", "type_name": "经典三级"},
    {"type_id": "39", "type_name": "动漫卡通"},
    {"type_id": "40", "type_name": "无码中字"},
    {"type_id": "47", "type_name": "欧美系列"},
    {"type_id": "64", "type_name": "国产传媒"},
    {"type_id": "119", "type_name": "JVID专区"},
    {"type_id": "139", "type_name": "SWAG专区"},
    {"type_id": "157", "type_name": "AI 换脸"},
    {"type_id": "158", "type_name": "AI 黄剧"},
    {"type_id": "day", "type_name": "日排行榜"},
    {"type_id": "week", "type_name": "周排行榜"},
    {"type_id": "moon", "type_name": "月排行榜"},
]

# 已知返回 404 的分类（探活实测），必须排除
CAT_BLACKLIST = {"7"}


# ================= 加解密 =================
def _b64u_dec(s):
    s = str(s or "").replace("-", "+").replace("_", "/")
    s += "=" * ((-len(s)) % 4)
    return base64.b64decode(s)


def _b64u_enc(b):
    return base64.b64encode(b).decode().replace("+", "-").replace("/", "_").rstrip("=")


def aes_dec_text(s):
    raw = _b64u_dec(s)
    if _HAS_CRYPTO:
        pt = _AES.new(KEY, _AES.MODE_CBC, IV).decrypt(raw)
        try:
            pt = _unpad(pt, 16)
        except Exception:
            pass
        return pt.decode("utf-8", "replace")
    pt = _py_cbc_dec(KEY, IV, raw)
    p = pt[-1] if pt else 0
    if 0 < p <= 16:
        pt = pt[:-p]
    return pt.decode("utf-8", "replace")


def aes_dec_json(s):
    return json.loads(aes_dec_text(s))


def aes_enc_b64u(text):
    data = text.encode("utf-8")
    if _HAS_CRYPTO:
        ct = _AES.new(KEY, _AES.MODE_CBC, IV).encrypt(_pad(data, 16))
    else:
        ct = _py_cbc_enc(KEY, IV, data)
    return _b64u_enc(ct)


# ================= Spider =================
from base.spider import Spider as _Base


class Spider(_Base):
    _TXT_RE = re.compile(r"(?i)\.txt(\?|$)")

    def __init__(self):
        try:
            super().__init__()
        except TypeError:
            pass
        self.siteKey = ""
        self.session = None

    # ---------- 壳契约 ----------
    def getDependence(self):
        return ""

    def getName(self):
        return "37cyx4"

    def isVideoFormat(self, url):
        return True

    def isTextFormat(self, url):
        return False

    def destroy(self):
        try:
            if self.session is not None:
                self.session.close()
        except Exception:
            pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **kw: None

    # ---------- 初始化 ----------
    def init(self, extend=""):
        # 内核注入的 siteKey 优先（__dict__ 直查，绕过 noop __getattr__）
        self.siteKey = str(self.__dict__.get("siteKey") or "")
        if not self.siteKey and extend:
            try:
                e = extend if isinstance(extend, dict) else json.loads(extend)
                self.siteKey = str(e.get("siteKey") or e.get("site_id") or "")
            except Exception:
                self.siteKey = ""
        if requests is not None:
            self.session = requests.Session()
            self.session.headers.update({"User-Agent": UA, "Referer": SITE + "/"})
        return None

    def _sk(self):
        sk = str(self.__dict__.get("siteKey") or "")
        return ("&siteKey=" + quote(sk)) if sk else ""

    def getProxyUrl(self, local=True):
        try:
            from com.github.catvod import Proxy as JProxy
            return JProxy.getUrl(local)
        except Exception:
            return "http://127.0.0.1:9978/proxy"

    # ---------- HTTP ----------
    def _get(self, url, timeout=4):
        """单次 timeout=4，失败重试 1 次：最坏 4+4=8s，不越 v17 的 10s GC 红线。"""
        last = None
        for _ in range(2):
            try:
                if requests is not None:
                    r = self.session.get(url, timeout=timeout)
                    r.raise_for_status()
                    return r
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": SITE + "/"})
                return urllib.request.urlopen(req, timeout=timeout)
            except Exception as e:
                last = e
        raise last

    def _get_text(self, url):
        r = self._get(url)
        try:
            return r.text
        except Exception:
            return r.read().decode("utf-8", "replace")

    def _json_api(self, path):
        """取 json_url 下的静态数据并解密；进程内按 path 缓存，多线程安全"""
        cache = self.__dict__.setdefault("_cache", {})
        lock = self.__dict__.setdefault("_lock", threading.Lock())
        with lock:
            if path in cache:
                return cache[path]
        txt = self._get_text(JSON_BASE + path)
        d = json.loads(txt)
        if isinstance(d, dict) and "data" in d:
            d = aes_dec_json(d["data"])
        with lock:
            cache[path] = d
        return d

    def _json_api_fast(self, path):
        """补图专用：timeout=2、不重试，失败直接返回 {}"""
        txt = None
        try:
            if requests is not None:
                r = self.session.get(JSON_BASE + path, timeout=2)
                r.raise_for_status()
                txt = r.text
            else:
                import urllib.request
                req = urllib.request.Request(JSON_BASE + path,
                                             headers={"User-Agent": UA, "Referer": SITE + "/"})
                with urllib.request.urlopen(req, timeout=2) as f:
                    txt = f.read().decode("utf-8", "replace")
        except Exception:
            return {}
        try:
            d = json.loads(txt)
            if isinstance(d, dict) and "data" in d:
                d = aes_dec_json(d["data"])
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    # ---------- 通用 ----------
    def _empty(self, page=1):
        return {"page": page, "pagecount": 1, "limit": 0, "total": 0,
                "list": [], "parse": 0, "jx": 0}

    def _to_int(self, v, d=1):
        try:
            return int(str(v).strip())
        except Exception:
            return d

    def _clean(self, s):
        s = str(s or "")
        s = re.sub(r"[\x00-\x1f\x7f]", "", s)
        s = re.sub(r"[$#]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    # ---------- 封面 ----------
    def _pic(self, url):
        """封面分流：
        - data: 原样返回
        - *.txt  -> 内容是 data:image/...;base64，必须走 do=py&type=pic 解码
        - 其它直链（.jpg/.png/.gif/.webp）-> 直接给 URL，壳直连加载，省一跳
        """
        u = str(url or "").strip()
        if not u:
            return ""
        if u.startswith("data:"):
            return u
        if not self._TXT_RE.search(u):
            return u
        tok = _b64u_enc(u.encode("utf-8"))
        return "%s?do=py&type=pic&url=%s%s" % (self.getProxyUrl(), tok, self._sk())

    def _pic_by_id(self, vid):
        """按 id 取封面：先查补图缓存，再查已缓存的分类页"""
        pc = self.__dict__.get("_pic_cache")
        if pc is None:
            pc = self.__dict__["_pic_cache"] = {}
        k = str(vid)
        if k in pc:
            return pc[k]
        cache = self.__dict__.get("_cache") or {}
        for path, data in cache.items():
            if not path.startswith("/category/"):
                continue
            if not isinstance(data, dict):
                continue
            for it in (data.get("data") or []):
                if str(it.get("id")) == k:
                    return str(it.get("titlepic") or "")
        return ""

    def _pick_pic(self, it):
        pic = str(it.get("titlepic") or "").strip()
        if pic:
            return pic
        return self._pic_by_id(it.get("id"))

    def _fill_pics(self, items, cap=20, budget=6.0):
        """补图：
        1) 先查分类页缓存 / 补图缓存，命中零请求
        2) 未命中的串行走 /video/<id>.json（timeout=2、最多 cap 条）
        3) 最多花 budget 秒，拿不到留空，不越 v17 的 10s GC 红线
        注：容器无 pycryptodome，纯 Python AES 解密一份约 1.9s；
            壳内有 pycryptodome，约 0.05s，实际能补满。
        """
        if not items:
            return items
        pending = []
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("titlepic") or "").strip():
                continue
            vid = str(it.get("id") or "")
            if not vid:
                continue
            cached = self._pic_by_id(vid)
            if cached:
                it["titlepic"] = cached
            elif len(pending) < cap:
                pending.append((it, vid))
        if not pending:
            return items
        deadline = time.time() + budget
        for it, vid in pending:
            if time.time() > deadline:
                break
            try:
                d = self._json_api_fast("/video/%s.json" % vid) or {}
                tp = str(d.get("titlepic") or "").strip()
                if tp:
                    it["titlepic"] = tp
                    pc = self.__dict__.get("_pic_cache")
                    if pc is None:
                        pc = self.__dict__["_pic_cache"] = {}
                    pc[str(vid)] = tp
            except Exception:
                pass
        return items

    # ---------- vod ----------
    def _vod(self, it):
        vid = str(it.get("id") or "")
        if not vid:
            return None
        ts = self._to_int(it.get("newstime"), 0)
        year = time.strftime("%Y", time.localtime(ts)) if ts else ""
        return {
            "vod_id": vid,
            "vod_name": self._clean(it.get("title")),
            "vod_pic": self._pic(self._pick_pic(it)),
            "vod_year": year,
            "vod_area": self._clean(it.get("classname") or ""),
            "vod_remarks": self._clean(it.get("classname") or ""),
            "vod_tag": "",
        }

    def _vods(self, arr):
        out = []
        seen = set()
        for it in (arr or []):
            v = self._vod(it)
            if v and v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                out.append(v)
        return out

    # ---------- 分类（动态过滤：只留 tbname=movie，排除 404 黑名单） ----------
    def _cats(self):
        try:
            o = self._json_api("/category-list.json")
            if isinstance(o, dict):
                o = o.get("data") or o.get("list") or []
            out = []
            seen = set()

            def add(cid, nm):
                if not cid or not nm:
                    return
                cid = str(cid)
                if cid in seen or cid in CAT_BLACKLIST:
                    return
                seen.add(cid)
                out.append({"type_id": cid, "type_name": str(nm)})

            for top in (o or []):
                if not isinstance(top, dict):
                    continue
                if top.get("tbname") == "movie":
                    add(top.get("classid"), top.get("classname"))
                for it in (top.get("items") or []):
                    if not isinstance(it, dict):
                        continue
                    if it.get("tbname") != "movie":
                        continue
                    add(it.get("classid"), it.get("classname"))

            if out:
                try:
                    out.sort(key=lambda x: int(x["type_id"]))
                except Exception:
                    pass
                out.extend([
                    {"type_id": "day", "type_name": "日排行榜"},
                    {"type_id": "week", "type_name": "周排行榜"},
                    {"type_id": "moon", "type_name": "月排行榜"},
                ])
                return out
        except Exception:
            pass
        return [dict(x) for x in DEFAULT_CLASS]

    # ---------- 首页 ----------
    def homeContent(self, filter):
        try:
            cats = self._cats()
            lst = []
            try:
                # top.json 条目不携带 titlepic（实测全空），首页改走分类接口保证有封面
                o = self._json_api("/category/1-1.json") or {}
                lst = self._vods(o.get("data") or [])[:20]
            except Exception:
                lst = []
            return {"class": cats, "list": lst}
        except Exception:
            return {"class": [dict(x) for x in DEFAULT_CLASS]}

    def homeVideoContent(self):
        return {"list": []}

    # ---------- 分类内容 ----------
    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "")
        pg = self._to_int(pg, 1)
        if pg < 1:
            pg = 1
        try:
            if tid in ("day", "week", "moon"):
                # 用 /top/top.json：一次解密约 4s，内含 day/week/moon 各 20 条。
                # 不用 top-Day/Week/Moon.json —— Week 597 条、Moon 2465 条，
                # 纯 Python AES 全量解密 18~69s，越 v17 的 10s GC 红线。
                o = self._json_api("/top/top.json") or {}
                arr = o.get(tid) or []
                self._fill_pics(arr)
                lst = self._vods(arr)
                return {"list": lst, "page": 1, "pagecount": 1,
                        "limit": len(lst), "total": len(lst), "parse": 0, "jx": 0}

            o = self._json_api("/category/%s-%s.json" % (tid, pg)) or {}
            lst = self._vods(o.get("data") or [])
            last = self._to_int(o.get("last_page"), 1)
            total = self._to_int(o.get("total"), len(lst))
            per = self._to_int(o.get("per_page"), len(lst) or 1)
            return {"list": lst, "page": pg, "pagecount": max(last, 1),
                    "limit": per, "total": total, "parse": 0, "jx": 0}
        except Exception:
            return self._empty(pg)

    # ---------- 详情 ----------
    def detailContent(self, ids):
        try:
            if isinstance(ids, str):
                s = ids.strip()
                if s.startswith("["):
                    try:
                        id_list = [str(json.loads(s)[0])]
                    except Exception:
                        id_list = [s.split(",")[0].strip("[]\"' ")]
                else:
                    id_list = [s.split(",")[0].strip("\"' ")]
            elif isinstance(ids, (list, tuple)):
                id_list = [str(x).strip("\"' ") for x in ids]
            else:
                id_list = [str(ids).split(",")[0].strip("\"' ")]
            vid = id_list[0] if id_list else ""
            if not vid:
                return {"list": []}

            o = self._json_api("/video/%s.json" % vid)
            if not isinstance(o, dict):
                return {"list": []}

            crumb = ""
            try:
                bcs = o.get("breadcrumb") or []
                if bcs:
                    crumb = str(bcs[0].get("title") or "")
            except Exception:
                crumb = ""
            if crumb == "self":
                cdns = CDN_SELF
            elif crumb == "actor":
                cdns = CDN_ACTOR
            else:
                cdns = CDN_DEFAULT

            m3u8 = str(o.get("m3u8") or "")
            mp4 = str(o.get("mp4") or "")
            froms, urls = [], []
            # MP4 直链优先（放最前）
            if mp4:
                froms.append("MP4")
                urls.append("正片$" + mp4)
            if m3u8:
                if m3u8.startswith("http"):
                    cl = [m3u8]
                else:
                    cl = [c + m3u8 for c in cdns]
                froms.append("HLS")
                urls.append("正片$" + cl[0])
                if len(cl) > 1:
                    froms.append("HLS2")
                    urls.append("正片$" + cl[1])
            if not froms:
                froms = ["线路"]
                urls = ["暂无片源$http://"]

            ts = self._to_int(o.get("newstime"), 0)
            year = time.strftime("%Y", time.localtime(ts)) if ts else ""
            kws = self._clean(o.get("keyboard") or "").replace(",", " / ")
            catn = self._clean(o.get("category_name") or "")
            content_parts = []
            if catn:
                content_parts.append("分类：" + catn)
            if kws:
                content_parts.append("标签：" + kws)

            vod = {
                "vod_id": vid,
                "vod_name": self._clean(o.get("title")),
                "vod_pic": self._pic(o.get("titlepic") or ""),
                "vod_year": year,
                "vod_area": catn,
                "vod_remarks": catn,
                "vod_content": "\n".join(content_parts),
                "vod_play_from": "$$$".join(froms),
                "vod_play_url": "$$$".join(urls),
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        try:
            key = str(key or "").strip()
            if not key:
                return {"list": [], "page": 1}
            page = self._to_int(pg, 1)
            enc = aes_enc_b64u(key)
            url = "%s/api/v2/search?keyword=%s&classid=0&page=%s" % (SITE, enc, page)
            txt = self._get_text(url)
            d = json.loads(txt)
            if not isinstance(d, dict) or d.get("status") != 1:
                return {"list": [], "page": page}
            o = aes_dec_json(d.get("data") or "")
            arr = (o or {}).get("data") or []
            self._fill_pics(arr)
            lst = self._vods(arr)
            return {"list": lst, "page": page}
        except Exception:
            return {"list": [], "page": 1}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        hdr = {"User-Agent": UA, "Referer": SITE + "/"}
        try:
            v = str(id or "").strip()
            seg = v.split("#")[0]
            cand = seg.rsplit("$", 1)[-1] if "$" in seg else seg
            if cand.startswith("http"):
                return {"parse": 0, "url": cand, "header": hdr}
        except Exception:
            pass
        return {"parse": 1, "url": SITE + "/", "header": hdr}

    # ---------- 本地代理（封面 data:image base64 解码） ----------
    def localProxy(self, param):
        try:
            typ = str((param or {}).get("type") or "")
            u = str((param or {}).get("url") or "")
            if u:
                try:
                    u = _b64u_dec(u).decode("utf-8", "replace")
                except Exception:
                    u = unquote(u)
            if typ == "pic" and u:
                r = self._get(u)
                try:
                    body = r.content
                except Exception:
                    body = r.read()
                txt = body.decode("utf-8", "replace").strip()
                m = re.match(r"data:image/([A-Za-z0-9+.-]+);base64,(.*)", txt, re.S)
                if m:
                    try:
                        raw = base64.b64decode(re.sub(r"\s+", "", m.group(2)))
                        mime = "image/" + ("jpeg" if m.group(1).lower() in ("jpg", "jpeg")
                                           else m.group(1).lower())
                        return [200, mime, raw]
                    except Exception:
                        pass
                ct = ""
                try:
                    ct = r.headers.get("Content-Type") or ""
                except Exception:
                    ct = ""
                return [200, ct or "image/jpeg", body]
        except Exception:
            pass
        return [200, "image/jpeg", b""]


# ================= 自测 =================
if __name__ == "__main__":
    print("[OK] module load, Crypto =", _HAS_CRYPTO)
    sp = Spider()
    sp.init("")

    h = sp.homeContent(False)
    print("homeContent: class=%d list=%d" % (len(h.get("class") or []),
                                             len(h.get("list") or [])))
    names = [c["type_name"] for c in (h.get("class") or [])]
    print("  含图文?", "图文" in names, "| 含小说?", "小说" in names,
          "| 含自拍偷拍?", "自拍偷拍" in names)

    c = sp.categoryContent("4", 1, False, {})
    print("categoryContent(4,p1): list=%d pagecount=%s total=%s" % (
        len(c.get("list") or []), c.get("pagecount"), c.get("total")))

    if c.get("list"):
        vid = c["list"][0]["vod_id"]
        d = sp.detailContent([vid])
        vod = (d.get("list") or [{}])[0]
        print("detailContent:", vod.get("vod_name"), "| from=", vod.get("vod_play_from"))
        pu = vod.get("vod_play_url") or ""
        if pu:
            first = pu.split("$$$")[0].split("#")[0]
            pid = first.rsplit("$", 1)[-1]
            pc = sp.playerContent("MP4", pid, [])
            print("playerContent:", pc.get("parse"), str(pc.get("url"))[:110])

    s = sp.searchContent("自拍", False)
    print("searchContent: list=%d" % len(s.get("list") or []))
    print("_sk() =", sp._sk())
    print("[DONE]")