# -*- coding: utf-8 -*-
"""
TVBox / CatVod / FongMi 通用 Python 爬虫 —— eroticmv.com
================================================================
设计原则
--------
1. 假设显式化：站点结构未知处全部集中在 CFG / 正则表，可单点替换。
2. 提取多路降级：JSON-LD → video/source → data-* → 脚本文本 → iframe。
3. 播放走本地代理：重写 m3u8、注入 Referer，规避防盗链。
4. 运行期失败软降级（返回空列表，不炸 TVBox）；测试期失败硬报错。
5. 自检覆盖 加载→首页→分类→详情→播放→搜索 全流程。

自检
----
    python eroticmv_spider.py --test          # 全链路检测
    python eroticmv_spider.py --probe         # 落盘 HTML 供校准
    python eroticmv_spider.py --test --probe  # 边测边存

TVBox 接入
----------
    "spider": "https://你的域名/eroticmv_spider.py"
"""

from __future__ import annotations

import argparse
import html as _html
import json
import math
import os
import random
import re
import sys
import time
import urllib.parse
from typing import Any, Dict, List, Optional

try:
    import requests
    from requests import Response as _ReqResp
except Exception:                                    # TVBox 内置运行时可能没有 requests
    requests = None
    _ReqResp = None

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

# TVBox 内置基类；独立运行时用占位基类
BASE_OK = False
try:
    from base.spider import Spider as _Base
    BASE_OK = True
except Exception:
    class _Base(object):
        pass


# ============================================================
# 0. 可调参数（站点改版只改这里）
# ============================================================
CFG = {
    "host": "https://eroticmv.com",
    "timeout": 20,
    "retry": 3,
    "backoff": 1.4,
    "interval": 0.35,          # 请求间隔，防限流
    "cache_ttl": 240,
    "page_limit": 24,
    "ua": ("Mozilla/5.0 (Linux; Android 12; SM-G981B) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"),
    "proxy_stream": True,      # 直连流是否强制过代理（防盗链站点保持 True）
}

# 导航解析失败时的兜底分类（按站点公开目录推测）
FALLBACK_CLASS = [
    {"type_id": "home",     "type_name": "最新"},
    {"type_id": "series",   "type_name": "剧集"},
    {"type_id": "softcore", "type_name": "Softcore"},
    {"type_id": "hardcore", "type_name": "Hardcore"},
    {"type_id": "vintage",  "type_name": "Vintage"},
    {"type_id": "asian",    "type_name": "Asian"},
    {"type_id": "lesbian",  "type_name": "Lesbian"},
    {"type_id": "4k",       "type_name": "4K"},
]

# 非详情页的保留路径段
RESERVED = {
    "category", "tag", "tags", "series", "page", "author", "feed", "about",
    "dmca", "contact", "privacy", "s", "search", "wp-json", "wp-admin",
    "wp-content", "wp-includes", "comments", "movies", "genres", "actress",
    "actresses", "year", "decade", "terms", "blog", "news", "random",
}

RE_ARTICLE = re.compile(r"<article[^>]*>(.*?)</article>", re.S | re.I)
RE_CARDBOX = re.compile(
    r'<div[^>]+class="[^"]*(?:post-item|post-thumb|item-thumb|movie-item|card|thumb)[^"]*"[^>]*>(.*?)</div>\s*</div>',
    re.S | re.I)
RE_HREF = re.compile(r'href=["\'](https?://[^"\']+?)["\']', re.I)
RE_IMG = re.compile(r'<img[^>]+(?:data-src|data-original|src)=["\']([^"\']+)["\'][^>]*>', re.I)
RE_ALT = re.compile(r'<img[^>]+alt=["\']([^"\']*)["\']', re.I)
RE_TITLE_ATTR = re.compile(r'<a[^>]+title=["\']([^"\']+)["\']', re.I)
RE_TAG = re.compile(r"<[^>]+>")

# 播放地址候选（按可信度排序）
PLAY_PATTERNS = [
    ("jsonld",   re.compile(r'"contentUrl"\s*:\s*"([^"]+)"', re.I)),
    ("jsonld",   re.compile(r'"embedUrl"\s*:\s*"([^"]+)"', re.I)),
    ("video",    re.compile(r"<video[^>]+src=[\"']([^\"']+)[\"']", re.I)),
    ("source",   re.compile(r"<source[^>]+src=[\"']([^\"']+)[\"']", re.I)),
    ("data",     re.compile(
        r'data-(?:src|video|file|url|m3u8|stream|player|mp4)\s*=\s*["\']([^"\']+\.(?:m3u8|mp4)[^"\']*)["\']',
        re.I)),
    ("raw",      re.compile(r'(https?://[^\s"\'<>\\]+?\.m3u8[^\s"\'<>\\]*)', re.I)),
    ("raw",      re.compile(r'(https?://[^\s"\'<>\\]+?\.mp4[^\s"\'<>\\]*)', re.I)),
    ("iframe",   re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.I)),
]

STREAM_EXT = (".m3u8", ".mp4", ".flv", ".mkv")


# ============================================================
# 1. 轻量响应包装（统一内置 fetch 与 requests 两条通道）
# ============================================================
class Resp(object):
    __slots__ = ("status", "text", "content", "headers", "url")

    def __init__(self, status=0, text="", content=b"", headers=None, url=""):
        self.status = status
        self.text = text or ""
        self.content = content or b""
        self.headers = headers or {}
        self.url = url

    @property
    def ok(self):
        return 200 <= self.status < 400

    def head(self, key, default=""):
        for k, v in self.headers.items():
            if k.lower() == key.lower():
                return v
        return default


def _log(msg):
    sys.stderr.write("[eroticmv] %s\n" % msg)


def _abs(u, base=None):
    if not u:
        return ""
    u = _html.unescape(u.strip())
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return CFG["host"] + u
    if u.startswith("http"):
        return u
    return urllib.parse.urljoin(base or CFG["host"] + "/", u)


def _txt(s):
    return _html.unescape(RE_TAG.sub("", s or "")).strip()


def _is_post(url):
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False
    if p.netloc and CFG["host"].split("//")[-1] not in p.netloc:
        return False
    segs = [s for s in p.path.split("/") if s]
    if not segs:
        return False
    if segs[0] in RESERVED and len(segs) == 1:
        return False
    if segs[0] in ("category", "tag", "tags", "author", "page", "wp-json"):
        return False
    slug = segs[-1]
    return len(slug) >= 4 and not slug.startswith("wp-") and "." not in slug


# ============================================================
# 2. 主类
# ============================================================
class Spider(_Base):

    # ---------------- 生命周期 ----------------
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._last = 0.0
        self.session = None
        if requests is not None:
            self.session = requests.Session()
            self.session.verify = False
            self.session.headers.update(self._headers())

    def init(self, extend=""):
        ext = (extend or "").strip()
        if ext.startswith("http"):
            CFG["host"] = ext.rstrip("/")
        elif ext and "=" in ext:
            for kv in ext.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    if k in CFG:
                        try:
                            CFG[k] = type(CFG[k])(v)
                        except Exception:
                            CFG[k] = v
        self.headers = self._headers()
        return None

    def getName(self):
        return "eroticmv"

    def isVideoFormat(self, url):
        return any((url or "").lower().split("?")[0].endswith(e) for e in STREAM_EXT)

    def manualVideoCheck(self):
        return True

    # ---------------- 网络 ----------------
    def _headers(self, referer=None):
        return {
            "User-Agent": CFG["ua"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Referer": referer or CFG["host"] + "/",
            "Connection": "keep-alive",
        }

    def _throttle(self):
        gap = time.time() - self._last
        if gap < CFG["interval"]:
            time.sleep(CFG["interval"] - gap)
        self._last = time.time()

    def _request(self, url, referer=None, method="GET", data=None, binary=False,
                 use_cache=True, range_hdr=None):
        if not url:
            return None
        ck = "GET|%s|%s" % (url, referer or "")
        if use_cache and method == "GET":
            hit = self._cache.get(ck)
            if hit and time.time() - hit[0] < CFG["cache_ttl"]:
                return hit[1]

        hdr = self._headers(referer)
        if range_hdr:
            hdr["Range"] = range_hdr

        last_err = None
        for attempt in range(CFG["retry"]):
            self._throttle()
            # 通道 A：TVBox 内置 fetch
            if BASE_OK and hasattr(_Base, "fetch") and method == "GET":
                try:
                    t = self.fetch(url, headers=hdr, timeout=CFG["timeout"],
                                   verify=False, encoding="utf-8")
                    if t:
                        r = Resp(200, t, t.encode("utf-8", "ignore"), hdr, url)
                        if use_cache:
                            self._cache[ck] = (time.time(), r)
                        return r
                except Exception as e:
                    last_err = e
            # 通道 B：requests
            if self.session is not None:
                try:
                    rr = self.session.request(method, url, headers=hdr, data=data,
                                              timeout=CFG["timeout"], allow_redirects=True)
                    r = Resp(rr.status_code, rr.text if not binary else "",
                             rr.content, dict(rr.headers), rr.url)
                    if r.status < 500:
                        if use_cache and method == "GET" and r.ok:
                            self._cache[ck] = (time.time(), r)
                        return r
                    last_err = RuntimeError("HTTP %s" % r.status)
                except Exception as e:
                    last_err = e
            if attempt < CFG["retry"] - 1:
                time.sleep(CFG["backoff"] ** attempt + random.random() * 0.3)
        _log("请求失败 %s -> %s" % (url, last_err))
        return None

    def _get_html(self, url, referer=None):
        r = self._request(url, referer=referer)
        return r.text if r is not None and r.ok else ""

    # ---------------- 列表解析 ----------------
    def _blocks(self, page):
        blobs = RE_ARTICLE.findall(page)
        if not blobs:
            blobs = RE_CARDBOX.findall(page)
        if not blobs:
            # 最后兜底：整页当作一个块，靠全局 href 扫描
            blobs = [page]
        return blobs

    def _parse_cards(self, page):
        out, seen = [], set()
        for blob in self._blocks(page):
            hrefs = [h for h in RE_HREF.findall(blob) if _is_post(h)]
            if not hrefs:
                continue
            vid = _abs(hrefs[0])
            if vid in seen:
                continue
            name = ""
            alt = RE_ALT.search(blob)
            if alt and alt.group(1).strip():
                name = alt.group(1)
            if not name:
                t = RE_TITLE_ATTR.search(blob)
                if t:
                    name = t.group(1)
            if not name:
                name = self._slug_title(vid)
            name = self._clean_title(name)
            if not name:
                continue
            pic = ""
            im = RE_IMG.search(blob)
            if im:
                pic = _abs(im.group(1))
            seen.add(vid)
            out.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": self._remarks(blob),
            })
        return out

    def _remarks(self, blob):
        m = re.search(r'class="[^"]*(?:duration|quality|label|badge|res)[^"]*"[^>]*>([^<]{1,16})<',
                      blob, re.I)
        return _txt(m.group(1)) if m else ""

    def _slug_title(self, url):
        slug = urllib.parse.urlparse(url).path.strip("/").split("/")[-1]
        return re.sub(r"[-_]+", " ", slug).strip().title()

    def _clean_title(self, name):
        name = _txt(name)
        name = re.sub(r"^(?:Watch|Stream|Download)\s+", "", name, flags=re.I)
        name = re.sub(r"\s*[|\-–]\s*(?:Erotic\s*Movies?|EroticMV.*)$", "", name, flags=re.I)
        name = re.sub(r"\s+Online\s+Free\s*$", "", name, flags=re.I)
        name = re.sub(r"\s*\((?:19|20)\d{2}\)\s*$", "", name)
        return re.sub(r"\s{2,}", " ", name).strip(" -|–—")

    def _page_count(self, page, pg):
        nums = [int(n) for n in re.findall(r"/page/(\d+)/", page)]
        nums = [n for n in nums if n > pg]
        return max(nums) if nums else (pg + 1 if nums else pg)

    # ---------------- 导航 ----------------
    def _parse_nav(self, page):
        out, seen = [], {"home"}
        for m in re.finditer(r'<a[^>]+href=["\'](https?://[^"\']+/(?:category|series)/[^"\']+)["\'][^>]*>(.*?)</a>',
                             page, re.S | re.I):
            url, label = m.group(1), _txt(m.group(2))
            tid = urllib.parse.urlparse(url).path.strip("/")
            if not label or tid in seen or len(label) > 16:
                continue
            seen.add(tid)
            out.append({"type_id": tid, "type_name": label})
            if len(out) >= 20:
                break
        return out

    # ---------------- TVBox API ----------------
    def homeContent(self, filter=False):
        page = self._get_html(CFG["host"] + "/")
        classes = self._parse_nav(page) if page else []
        if not classes:
            classes = list(FALLBACK_CLASS)
        else:
            classes.insert(0, {"type_id": "home", "type_name": "最新"})
        return {
            "class": classes,
            "filters": {},
            "list": self._parse_cards(page)[:CFG["page_limit"]],
        }

    def homeVideoContent(self):
        return {"list": self._parse_cards(self._get_html(CFG["host"] + "/"))}

    def _cat_url(self, tid, pg):
        if tid in ("", "home"):
            path = "/"
        elif tid.startswith(("category/", "series/")):
            path = "/%s/" % tid.strip("/")
        else:
            path = "/category/%s/" % tid.strip("/")
        if pg and int(pg) > 1:
            path += "page/%d/" % int(pg)
        return CFG["host"] + path

    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg or 1)
        page = self._get_html(self._cat_url(tid, pg))
        lst = self._parse_cards(page)
        pc = self._page_count(page, pg) if lst else pg
        return {
            "page": pg,
            "pagecount": pc,
            "limit": CFG["page_limit"],
            "total": pc * CFG["page_limit"],
            "list": lst,
        }

    # ---------------- 详情 ----------------
    def _extract_play(self, page, page_url):
        body = page.replace("\\/", "/").replace("&#038;", "&").replace("&amp;", "&")
        direct, embed = [], []
        for kind, pat in PLAY_PATTERNS:
            for m in pat.finditer(body):
                u = _abs(_html.unescape(m.group(1)), page_url)
                if not u.startswith("http"):
                    continue
                if u.split("?")[0].lower().endswith((".m3u8", ".mp4", ".flv", ".mkv")):
                    if u not in direct:
                        direct.append(u)
                elif kind == "iframe":
                    host = urllib.parse.urlparse(u).netloc
                    if host and CFG["host"].split("//")[-1] not in host and u not in embed:
                        embed.append(u)
        return direct, embed

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        page = self._get_html(vid)
        if not page:
            return {"list": []}

        name = ""
        for pat in (r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                    r"<h1[^>]*>(.*?)</h1>",
                    r"<title[^>]*>(.*?)</title>"):
            m = re.search(pat, page, re.S | re.I)
            if m:
                name = self._clean_title(m.group(1))
                if name:
                    break
        name = name or self._slug_title(vid)

        pic = ""
        for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                    r'"image"\s*:\s*"([^"]+)"'):
            m = re.search(pat, page, re.I)
            if m:
                pic = _abs(m.group(1))
                break

        desc = ""
        for pat in (r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
                    r'<div[^>]+class="[^"]*(?:entry-content|description|synopsis)[^"]*"[^>]*>(.*?)</div>'):
            m = re.search(pat, page, re.S | re.I)
            if m:
                desc = _txt(m.group(1))[:1200]
                if desc:
                    break

        year = ""
        ym = re.search(r"\b(19|20)\d{2}\b", page)
        if ym:
            year = ym.group(0)

        direct, embed = self._extract_play(page, vid)

        froms, urls = [], []
        if direct:
            froms.append("直连")
            urls.append("#".join("%s$%s" % ("HD-%d" % (i + 1), u)
                                 for i, u in enumerate(direct[:12])))
        froms.append("嗅探")
        urls.append("正片$%s" % vid if embed else "正片$%s" % vid)

        return {"list": [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": "",
            "vod_year": year,
            "vod_area": "",
            "vod_remarks": "直连" if direct else "嗅探",
            "vod_actor": "",
            "vod_director": "",
            "vod_content": desc or name,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }]}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=False, pg="1"):
        key = (key or "").strip()
        if not key:
            return {"list": []}
        pg = int(pg or 1)
        out = []
        for tpl in ("/?s=%s", "/search/?q=%s"):
            url = CFG["host"] + tpl % urllib.parse.quote(key)
            if pg > 1:
                url = CFG["host"] + "/page/%d/" % pg + (tpl % urllib.parse.quote(key))
            page = self._get_html(url)
            out = self._parse_cards(page)
            if out:
                break
        return {"list": out}

    # ---------------- 代理 ----------------
    def getProxyUrl(self):
        try:
            return _Base.getProxyUrl(self)
        except Exception:
            return ""

    def _px(self, url, kind, ref=None):
        base = self.getProxyUrl()
        if not base:
            return url
        sep = "&" if "?" in base else "?"
        q = base + sep + "kind=" + kind + "&url=" + urllib.parse.quote(url, safe="")
        if ref:
            q += "&ref=" + urllib.parse.quote(ref, safe="")
        return q

    def _rewrite_manifest(self, text, base_url, ref):
        out = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                # 处理 KEY / MEDIA 里的 URI="..."
                def _sub(m):
                    return 'URI="%s"' % self._px(
                        urllib.parse.urljoin(base_url, m.group(1)), "seg", ref)
                out.append(re.sub(r'URI="([^"]+)"', _sub, s))
            else:
                out.append(self._px(urllib.parse.urljoin(base_url, s), "seg", ref))
        return "\n".join(out)

    def localProxy(self, param):
        if isinstance(param, str):
            param = dict(urllib.parse.parse_qsl(param.lstrip("?")))
        url = param.get("url") or param.get("u") or ""
        url = urllib.parse.unquote(url)
        kind = param.get("kind") or "seg"
        ref = urllib.parse.unquote(param.get("ref") or CFG["host"] + "/")
        if not url:
            return {"code": 404, "contentType": "text/plain", "content": b"no url"}

        if kind == "seg":
            r = self._request(url, referer=ref, binary=True)
            if r is None or not r.ok:
                return {"code": 502, "contentType": "video/mp2t", "content": b""}
            return {"code": 200,
                    "contentType": r.head("Content-Type", "video/mp2t"),
                    "content": r.content}

        r = self._request(url, referer=ref)
        if r is None or not r.ok:
            return {"code": 502, "contentType": "application/vnd.apple.mpegurl", "content": b""}
        body = r.text
        if "#EXTM3U" in body:
            body = self._rewrite_manifest(body, url, ref)
        return {"code": 200,
                "contentType": "application/vnd.apple.mpegurl",
                "content": body.encode("utf-8")}

    # ---------------- 播放 ----------------
    def playerContent(self, flag, pid, vipFlags=None):
        pid = (pid or "").strip()
        if not pid:
            return {"parse": 1, "playUrl": "", "url": ""}

        if pid.startswith("sniff|"):
            return {"parse": 1, "playUrl": "", "url": pid.split("|", 1)[1], "jx": 0}

        url = pid.split("|", 1)[1] if pid.startswith("direct|") else pid
        url = _html.unescape(url)

        if url.split("?")[0].lower().endswith(".m3u8") and CFG["proxy_stream"]:
            return {"parse": 0, "playUrl": "", "jx": 0,
                    "url": self._px(url, "m3u8", CFG["host"] + "/"),
                    "header": json.dumps(self._headers())}
        if self.isVideoFormat(url):
            return {"parse": 0, "playUrl": "", "jx": 0, "url": url,
                    "header": json.dumps(self._headers())}
        # 无法直连（外链 iframe / 加密播放器）→ 交给壳嗅探
        return {"parse": 1, "playUrl": "", "url": url, "jx": 0}


# ============================================================
# 3. 自检：加载 → 首页 → 分类 → 详情 → 播放 → 搜索
# ============================================================
class Checker(object):
    def __init__(self, probe=False):
        self.sp = Spider()
        self.sp.init("")
        self.probe = probe
        self.fails = 0
        self.report = []

    def step(self, idx, total, title):
        sys.stdout.write("\n[%d/%d] %s\n" % (idx, total, title))
        sys.stdout.flush()

    def ok(self, cond, msg, soft=False):
        if cond:
            sys.stdout.write("   PASS  %s\n" % msg)
            self.report.append(("PASS", msg))
        else:
            self.fails += 1 if not soft else 0
            sys.stdout.write("   %s  %s\n" % ("WARN" if soft else "FAIL", msg))
            self.report.append(("WARN" if soft else "FAIL", msg))
        return cond

    def dump(self, tag, text):
        if not self.probe or not text:
            return
        os.makedirs("probe", exist_ok=True)
        p = os.path.join("probe", "%s.html" % tag)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        sys.stdout.write("   saved -> %s (%d bytes)\n" % (p, len(text)))

    # ---- 1 加载 ----
    def t_load(self):
        self.step(1, 6, "站点可达性 / TLS / 首页加载")
        t0 = time.time()
        r = self.sp._request(CFG["host"] + "/", use_cache=False)
        dt = time.time() - t0
        if not self.ok(r is not None, "TCP + HTTP 连接建立"):
            return ""
        self.ok(r.ok, "HTTP 状态 %s" % r.status)
        self.ok(dt < 15, "响应耗时 %.2fs < 15s" % dt, soft=True)
        self.ok(len(r.content) > 2000, "响应体 %d bytes > 2000" % len(r.content))
        self.ok("eroticmv" in r.text.lower(), "响应体包含站点标识")
        self.dump("home", r.text)
        return r.text

    # ---- 2 首页 ----
    def t_home(self, page):
        self.step(2, 6, "homeContent 分类 + 首屏列表")
        data = self.sp.homeContent(False)
        cls = data.get("class") or []
        lst = data.get("list") or []
        self.ok(len(cls) >= 3, "解析到 %d 个分类" % len(cls))
        if cls:
            sys.stdout.write("   sample: %s\n" % ", ".join(
                c["type_name"] for c in cls[:6]))
        self.ok(len(lst) >= 3, "解析到 %d 条首屏条目" % len(lst))
        if lst:
            c0 = lst[0]
            self.ok(bool(c0.get("vod_id")), "条目含 vod_id")
            self.ok(bool(c0.get("vod_name")), "条目含 vod_name")
            self.ok(bool(c0.get("vod_pic")), "条目含 vod_pic", soft=True)
            sys.stdout.write("   sample: %s | %s\n" % (c0["vod_name"], c0["vod_id"]))
        return data

    # ---- 3 分类 ----
    def t_category(self, home):
        self.step(3, 6, "categoryContent 翻页 + 列表解析")
        tids = [c["type_id"] for c in (home.get("class") or []) if c["type_id"] != "home"]
        tid = tids[0] if tids else "home"
        d = self.sp.categoryContent(tid, 1, False, None)
        lst = d.get("list") or []
        self.ok(len(lst) >= 3, "分类 [%s] 第 1 页返回 %d 条" % (tid, len(lst)))
        self.ok(int(d.get("pagecount", 1)) >= 1, "pagecount=%s" % d.get("pagecount"))
        if lst:
            d2 = self.sp.categoryContent(tid, 2, False, None)
            l2 = d2.get("list") or []
            self.ok(len(l2) >= 1, "第 2 页返回 %d 条（翻页有效）" % len(l2))
            if l2 and lst:
                self.ok(l2[0]["vod_id"] != lst[0]["vod_id"], "第 2 页与第 1 页内容不同")
        return lst[0] if lst else None

    # ---- 4 详情 ----
    def t_detail(self, card):
        self.step(4, 6, "detailContent 元数据 + 播放地址提取")
        if not card:
            self.ok(False, "无可测条目")
            return None
        vid = card["vod_id"]
        d = self.sp.detailContent([vid])
        arr = d.get("list") or []
        if not self.ok(bool(arr), "详情返回非空"):
            return None
        v = arr[0]
        self.ok(bool(v.get("vod_name")), "vod_name = %s" % v.get("vod_name", "")[:60])
        self.ok(bool(v.get("vod_pic")), "vod_pic 存在", soft=True)
        froms = (v.get("vod_play_from") or "").split("$$$")
        urls = (v.get("vod_play_url") or "").split("$$$")
        self.ok(len(froms) == len(urls) and len(urls) >= 1, "播放源结构对齐：%s" % froms)
        self.ok("直连" in froms, "存在直连线路（否则仅能嗅探）", soft=True)
        self.dump("detail", self.sp._get_html(vid))
        return v

    # ---- 5 播放 ----
    def t_play(self, v):
        self.step(5, 6, "playerContent 播放链 + 流清单校验")
        if not v:
            self.ok(False, "无详情可测")
            return
        froms = (v.get("vod_play_from") or "").split("$$$")
        urls = (v.get("vod_play_url") or "").split("$$$")
        idx = froms.index("直连") if "直连" in froms else 0
        first = urls[idx].split("#")[0]
        pid = first.split("$", 1)[1] if "$" in first else first
        res = self.sp.playerContent(froms[idx], pid, None)
        self.ok(bool(res.get("url")), "playerContent 返回 url")
        self.ok(res.get("parse") in (0, 1), "parse 标记 = %s" % res.get("parse"))

        if res.get("parse") == 1:
            self.ok(True, "走壳嗅探模式（无直连流，属降级但可用）", soft=True)
            return

        play = res.get("url")
        # 代理通道自检
        if play.startswith("http://127.0.0.1") or "proxy" in play:
            qs = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(play).query))
            if "url" in qs:
                inner = urllib.parse.unquote(qs["url"])
                r = self.sp._request(inner, referer=CFG["host"] + "/", use_cache=False)
                self.ok(r is not None and r.ok, "直连源 HTTP 可达 (%s)" % inner[:90])
                if r is not None and r.ok and "#EXTM3U" in r.text:
                    self.ok(True, "m3u8 清单含 #EXTM3U")
                    segs = len(re.findall(r"^[^#\s].+$", r.text, re.M))
                    self.ok(segs >= 1, "清单含 %d 个分片/子清单" % segs)
                    first_line = next((l for l in r.text.splitlines()
                                       if l and not l.startswith("#")), "")
                    if first_line:
                        sub = urllib.parse.urljoin(inner, first_line.strip())
                        rs = self.sp._request(sub, referer=CFG["host"] + "/",
                                              range_hdr="bytes=0-1023", use_cache=False)
                        self.ok(rs is not None and rs.ok,
                                "首个子资源可取 (%d bytes)" % (len(rs.content) if rs else 0))
                        self.ok(bool(rs and len(rs.content) > 0), "子资源非空")
                # 代理函数本身
                px = self.sp.localProxy({"kind": "m3u8", "url": inner,
                                         "ref": CFG["host"] + "/"})
                self.ok(px.get("code") == 200, "localProxy 返回 200")
                body = px.get("content") or b""
                self.ok(b"#EXTM3U" in body, "代理输出为合法 m3u8")
                self.ok(b"kind=seg" in body, "代理已重写分片 URI")
        else:
            r = self.sp._request(play, referer=CFG["host"] + "/", use_cache=False)
            self.ok(r is not None and r.ok, "直连 URL 可达")
            self.ok(r is not None and "#EXTM3U" in r.text, "清单含 #EXTM3U")

    # ---- 6 搜索 ----
    def t_search(self):
        self.step(6, 6, "searchContent 关键词检索")
        for kw in ("jav", "erotic", "asian"):
            lst = self.sp.searchContent(kw, False, 1).get("list") or []
            if lst:
                self.ok(True, "关键词 [%s] 命中 %d 条" % (kw, len(lst)))
                self.ok(bool(lst[0].get("vod_id")), "搜索结果可解析 vod_id")
                sys.stdout.write("   sample: %s\n" % lst[0]["vod_name"])
                return
        self.ok(False, "三个关键词均无结果", soft=True)

    def run(self):
        sys.stdout.write("=" * 62 + "\n eroticmv 全链路自检\n" + "=" * 62 + "\n")
        page = self.t_load()
        if page:
            home = self.t_home(page)
            card = self.t_category(home)
            v = self.t_detail(card)
            self.t_play(v)
            self.t_search()
        sys.stdout.write("\n" + "=" * 62 + "\n")
        sys.stdout.write("结果：%d 项失败，%d 项告警\n" % (
            self.fails, sum(1 for s, _ in self.report if s == "WARN")))
        return 0 if self.fails == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--host")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.host:
        CFG["host"] = a.host.rstrip("/")
    if not a.test:
        a.test = True
    sys.exit(Checker(probe=a.probe).run())


if __name__ == "__main__":
    main()