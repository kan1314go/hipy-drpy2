#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
import json
import base64
import urllib.request
import urllib.error
import urllib.parse
import http.cookiejar
import gzip
import zlib
import ssl
import time

try:
    from urllib.parse import quote, unquote
except ImportError:
    from urllib import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

SITE = "https://www.555fl2.com"
ALT_SITES = []
KNOWN_HOSTS = ("555fl2.com", "www.555fl2.com")

BRAND = "ZakaTV"
STREAM_EXTS = (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd")
MAX_SOURCES = 8

NOISE_TITLES = (
    "首页", "上一页", "下一页", "尾页", "立即播放", "播放", "详情",
    "收藏", "分享", "下载APP", "留言", "回到顶部"
)

ZONE_MATRIX = [
    {"id": "zone_home", "name": "🏠首页推荐", "subs": [
        {"n": "首页推荐", "v": "home"},
    ]},
    {"id": "zone_movie", "name": "🎬电影", "subs": [
        {"n": "全部电影", "v": "t1"},
    ]},
    {"id": "zone_tv", "name": "📺连续剧", "subs": [
        {"n": "全部剧集", "v": "t2"},
    ]},
    {"id": "zone_anime", "name": "🌸动漫", "subs": [
        {"n": "全部动漫", "v": "t4"},
    ]},
    {"id": "zone_variety", "name": "🎭综艺纪录", "subs": [
        {"n": "全部综艺", "v": "t3"},
    ]},
    {"id": "zone_short", "name": "🎞️擦边短剧", "subs": [
        {"n": "全部短剧", "v": "t126"},
    ]},
]

def _unescape(text):
    s = str(text or "")
    if "&" not in s:
        return s
    s = s.replace("&nbsp;", " ")
    s = s.replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    s = s.replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&amp;", "&")
    return s

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

def clean_label(text):
    t = str(text or "")
    t = re.sub(r"</?em>", "", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _unescape(t)
    t = re.sub(r"[\r\n\t\$#]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

def clean_pic(url):
    u = str(url or "").strip().replace("\\/", "/")
    if not u or u.startswith("data:"):
        return ""
    low = u.lower()
    for bad in ("lazyload", "loading", "placeholder", "blank.gif", "video_web_comment"):
        if bad in low:
            return ""
    return u

def fixed_int(value, default=1):
    try:
        n = int(str(value or default).strip())
    except Exception:
        n = default
    return n if n >= 1 else default

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = SITE
        self.active_host = SITE
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}
        self._init_session()

    def _init_session(self):
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        site = str(self.options.get("site") or self.options.get("url") or "").strip()
        if site.startswith("http"):
            self.siteUrl = site.rstrip("/")
            self.active_host = self.siteUrl
        return True

    def getName(self):
        return "555电影"

    def isVideoFormat(self, url):
        low = str(url or "").lower()
        if not low:
            return False
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "native-ad", "stat.php")):
            return False
        return any(k in low for k in STREAM_EXTS)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _hosts(self):
        hosts = [self.siteUrl.rstrip("/")]
        for h in ALT_SITES:
            h = h.rstrip("/")
            if h and h not in hosts:
                hosts.append(h)
        return hosts

    def _fix_host(self, url):
        u = str(url or "")
        if not u or self.active_host == self.siteUrl:
            return u
        m = re.match(r"^(?:https?:)?//([^/]+)(.*)$", u)
        if m and m.group(1).lower() in KNOWN_HOSTS:
            return self.active_host + m.group(2)
        return u

    def _abs(self, url):
        u = str(url or "").strip().replace("\\/", "/")
        if not u:
            return ""
        if u.startswith("//"):
            u = "https:" + u
        elif not u.startswith("http"):
            u = (self.siteUrl + u) if u.startswith("/") else (self.siteUrl + "/" + u)
        return self._fix_host(u)

    def _request(self, url, referer="", accept_encoding="gzip, deflate", stop_markers=None):
        headers = {
            "User-Agent": self._ua,
            "Referer": referer or (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": accept_encoding,
            "Connection": "close"
        }
        req = urllib.request.Request(url, headers=headers)
        with self.opener.open(req, timeout=10) as resp:
            code = resp.getcode()
            final = resp.geturl()
            try:
                enc = resp.headers.get("Content-Encoding", "") or ""
            except Exception:
                enc = ""
            if stop_markers:
                raw = b""
                while len(raw) < 400000:
                    chunk = resp.read(16384)
                    if not chunk:
                        break
                    raw += chunk
                    if raw[:2] == b"\x1f\x8b" or "gzip" in enc.lower():
                        raw += resp.read()
                        break
                    hit = [raw.find(m) for m in stop_markers if m in raw]
                    if hit and b"</script>" in raw[max(hit):]:
                        break
            else:
                raw = resp.read()
        return code, final, enc, raw

    @staticmethod
    def _decompress(raw, enc):
        enc = (enc or "").lower()
        if raw[:2] == b"\x1f\x8b" or "gzip" in enc:
            try:
                return gzip.decompress(raw)
            except Exception:
                return raw
        if "deflate" in enc:
            try:
                return zlib.decompress(raw)
            except Exception:
                try:
                    return zlib.decompress(raw, -zlib.MAX_WBITS)
                except Exception:
                    return raw
        return raw

    @staticmethod
    def _decode(raw):
        for codec in ("utf-8", "gbk"):
            try:
                return raw.decode(codec)
            except Exception:
                pass
        return raw.decode("utf-8", "ignore")

    def _fetch_url(self, url, referer="", stop_markers=None):
        last_err = ""
        accept_enc = "identity" if stop_markers else "gzip, deflate"
        for attempt in range(3):
            try:
                code, final, enc, raw = self._request(url, referer, accept_enc, stop_markers)
                if "br" in enc.lower():
                    code, final, enc, raw = self._request(url, referer, "identity", stop_markers)
                raw = self._decompress(raw, enc)
                return {"code": code, "text": self._decode(raw), "err": "", "final_url": final}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (403, 429, 451, 502, 503, 520, 521, 522) and attempt < 2:
                    self._init_session()
                    time.sleep(0.15)
                    continue
                body = ""
                try:
                    body = e.read().decode("utf-8", "ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": body, "err": last_err, "final_url": url}
            except Exception as e:
                last_err = str(e)
                if attempt < 2:
                    self._init_session()
                    time.sleep(0.15)
                    continue
                return {"code": -1, "text": "", "err": last_err, "final_url": url}
        return {"code": -1, "text": "", "err": last_err, "final_url": url}

    def _fetch(self, path, referer="", stop_markers=None):
        if not path:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        if path.startswith("//"):
            path = "https:" + path
        if path.startswith("http"):
            return self._fetch_url(self._fix_host(path), referer, stop_markers)
        if not path.startswith("/"):
            path = "/" + path

        last = {"code": -1, "text": "", "err": "no host", "final_url": path}
        for host in self._hosts():
            res = self._fetch_url(host + path, referer, stop_markers)
            if res["code"] == 200 and len(res["text"]) > 500:
                self.active_host = host
                return res
            last = res
        return last

    def _pic(self, inner):
        for attr in ("data-original", "data-src", "data-lazy-src", "src"):
            m = re.search(r"""%s=["']([^"']+)["']""" % attr, inner, re.I)
            if m:
                cand = clean_pic(_unescape(m.group(1)))
                if cand:
                    return self._abs(cand)
        m = re.search(r"""background-image\s*:\s*url\(\s*['"]?([^'")]+)""", inner, re.I)
        if m:
            cand = clean_pic(_unescape(m.group(1)))
            if cand:
                return self._abs(cand)
        return ""

    def _note(self, inner):
        m = re.search(r"""module-item-note[^>]*>([^<]{1,20})<""", inner, re.I)
        if m:
            t = clean_label(m.group(1))
            if t:
                return t
        m = re.search(r"""module-item-douban[^>]*>\s*豆瓣[:：]\s*([\d.]+)\s*分""", inner)
        if m:
            return "豆瓣%s" % m.group(1)
        return ""

    def _title(self, attrs, inner):
        m = re.search(r"""title=["']([^"']+)["']""", attrs, re.I)
        if m:
            t = clean_label(m.group(1))
            if t and t not in NOISE_TITLES:
                return t

        for item in re.findall(r"""alt=["']([^"']*)["']""", inner, re.I):
            t = clean_label(item)
            if t and len(t) >= 1 and t not in NOISE_TITLES:
                return t

        m = re.search(r"""module-poster-item-title[^>]*>([\s\S]*?)</div>""", inner, re.I)
        if m:
            t = clean_label(m.group(1))
            if t and t not in NOISE_TITLES:
                return t

        m = re.search(r"""<h[1-6][^>]*>([\s\S]*?)</h[1-6]>""", inner, re.I)
        if m:
            return clean_label(m.group(1))
        return ""

    def _cards(self, html):
        if not html:
            return []

        order = []
        records = {}

        for m in re.finditer(r"""<a\b([^>]*)>([\s\S]*?)</a>""", html, re.I):
            attrs = m.group(1) or ""
            inner = m.group(2) or ""
            hm = re.search(r"""href=["']([^"']+)["']""", attrs, re.I)
            if not hm:
                continue
            href = _unescape(hm.group(1)).strip()
            vm = re.search(r"/voddetail/(\d+)\.html", href, re.I)
            if not vm:
                continue
            vid = vm.group(1)

            rec = records.get(vid)
            if rec is None:
                rec = {"id": vid, "title": "", "pic": "", "note": ""}
                records[vid] = rec
                order.append(vid)

            if not rec["pic"]:
                rec["pic"] = self._pic(inner)
            if not rec["note"]:
                rec["note"] = self._note(inner)

            title = self._title(attrs, inner)
            if title and len(title) > len(rec["title"]):
                rec["title"] = title

        vod_list = []
        for vid in order:
            rec = records[vid]
            if not rec["title"]:
                continue
            if not rec["pic"] and not rec["note"]:
                continue
            vod_list.append({
                "vod_id": self._abs("/voddetail/%s.html" % vid),
                "vod_name": rec["title"],
                "vod_pic": rec["pic"],
                "vod_remarks": format_remarks("ZakaTV", rec["note"])
            })
        return vod_list

    @staticmethod
    def _pagecount(html, page, count):
        nums = [int(x) for x in re.findall(r"(\d+)---\.html", html or "")]
        if nums:
            return max(nums)
        return page + 1 if count > 0 else page

    @staticmethod
    def _slice_json(text, start):
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return ""

    @staticmethod
    def _cfg_url(url, encrypt):
        u = str(url or "").strip().replace("\\/", "/")
        if not u:
            return ""
        enc = str(encrypt or "0").strip()
        if enc in ("1", "2"):
            try:
                if enc == "2":
                    u = u[::-1]
                pad = len(u) % 4
                if pad:
                    u += "=" * (4 - pad)
                u = base64.b64decode(u).decode("utf-8", "ignore")
            except Exception:
                pass
        return u.strip()

    def _stream(self, html):
        if not html:
            return ""
        norm = html.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")

        for m in re.finditer(r"(player_[a-zA-Z0-9_]+|mac_player)\s*=\s*\{", html):
            blob = self._slice_json(html, m.end() - 1)
            if not blob:
                continue
            try:
                cfg = json.loads(blob)
            except Exception:
                continue
            if not isinstance(cfg, dict):
                continue
            cand = self._cfg_url(cfg.get("url") or "", cfg.get("encrypt", "0"))
            if cand:
                return self._abs(cand)

        m = re.search(r"""["']url["']\s*:\s*["']((?:https?:)?(?:\\?/){2}[^"']+\.(?:m3u8|mp4|flv)[^"']*)["']""", norm, re.I)
        if m:
            return self._abs(m.group(1))

        for ext in ("m3u8", "mp4", "flv"):
            m = re.search(r"""((?:https?:)?//[^\s"'<>\\]+?\.%s[^\s"'<>\\]*)""" % ext, norm, re.I)
            if m:
                return self._abs(m.group(1))

        m = re.search(r"""<iframe[^>]+src=["']([^"']+)["']""", norm, re.I)
        if m:
            src = _unescape(m.group(1)).strip()
            qm = re.search(r"[?&](?:url|v|vid|code)=([^&#]+)", src, re.I)
            if qm:
                inner = unquote(qm.group(1))
                if self.isVideoFormat(inner):
                    return self._abs(inner)
            return self._abs(src)

        return ""

    def homeContent(self, filter):
        classes = [{"type_name": z["name"], "type_id": z["id"]} for z in ZONE_MATRIX]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        res = self._fetch("/index/home.html")
        return {"list": self._cards(res.get("text", ""))[:30]}

    def _list_path(self, target, page):
        if target == "home":
            return "/index/home.html"

        m = re.match(r"^t(\d+)$", target or "")
        tid = m.group(1) if m else str(target or "")
        if page <= 1:
            return "/vodshow/%s-----------.html" % tid
        return "/vodshow/%s--------%d---.html" % (tid, page)

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        page = fixed_int(pg, 1)

        cate = ""
        if isinstance(extend, str) and extend.strip():
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if isinstance(extend, dict) and extend.get("sub"):
            cate = str(extend["sub"]).strip()
        if not cate:
            for z in ZONE_MATRIX:
                if z["id"] == tid:
                    cate = z["subs"][0]["v"]
                    break
        if not cate:
            cate = str(tid or "")

        res = self._fetch(self._list_path(cate, page))
        html = res.get("text", "")
        vod_list = self._cards(html)

        if cate == "home":
            return {"page": 1, "pagecount": 1, "limit": 30, "total": len(vod_list), "list": vod_list}

        pagecount = self._pagecount(html, page, len(vod_list))
        return {
            "page": page,
            "pagecount": pagecount,
            "limit": 30,
            "total": pagecount * 30,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw_id = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()

        vm = re.search(r"/voddetail/(\d+)\.html", raw_id)
        if vm:
            vid = vm.group(1)
            detail_url = self._abs("/voddetail/%s.html" % vid)
        else:
            vid = re.sub(r"\D", "", raw_id)
            detail_url = self._abs(raw_id)

        res = self._fetch(detail_url)
        html = res.get("text", "")

        title = ""
        m = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html, re.I)
        if m:
            title = clean_label(m.group(1))
        if not title:
            m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            if m:
                title = clean_label(re.split(r"\s*-\s*", m.group(1))[0])
        if not title:
            title = "超清正片"

        poster = ""
        m = re.search(r"""<meta[^>]+(?:property|name)=["']og:image["'][^>]+content=["']([^"']+)["']""", html, re.I)
        if m:
            poster = self._abs(_unescape(m.group(1)))
        if not poster:
            m = re.search(r"""data-original=["'](https?://[^"']+)["']""", html, re.I)
            if m:
                poster = self._abs(_unescape(m.group(1)))
        if not poster:
            m = re.search(r"""<div class="module-info-pic"[^>]*>[\s\S]*?src=["']([^"']+)["']""", html, re.I)
            if m:
                poster = self._abs(m.group(1))

        desc = ""
        m = re.search(r"""<div class="module-info-introduction-content"[^>]*>([\s\S]*?)</div>""", html, re.I)
        if m:
            desc = clean_label(m.group(1))

        sources = []
        seen = {}
        for m in re.finditer(
                r"""<a[^>]+href=["'](https?://[^"']*?/vodplay/\d+-(\d+)-(\d+)\.html|/vodplay/\d+-(\d+)-(\d+)\.html)["'][^>]*>([\s\S]*?)</a>""",
                html, re.I):
            link = m.group(1)
            sid = m.group(2) or m.group(4)
            nid = int(m.group(3) or m.group(5))
            raw_name = clean_label(m.group(6))
            is_fallback = (not raw_name) or (raw_name in NOISE_TITLES)
            name = ("正片" if nid == 1 else ("第%02d集" % nid)) if is_fallback else raw_name

            if sid not in seen:
                seen[sid] = {}
                sources.append(sid)
            bucket = seen[sid]
            prev = bucket.get(nid)
            if prev is None or (prev[2] and not is_fallback):
                bucket[nid] = (name, self._abs(link), is_fallback)

        labels = {}
        for m in re.finditer(
                r"""change\(\s*['"]\d+['"]\s*,\s*['"](\d+)['"]\s*,\s*0\s*\)[^>]*>\s*<span>([^<]+)</span>""",
                html, re.I):
            sid, name = m.group(1), clean_label(m.group(2))
            if sid not in labels and name:
                labels[sid] = name

        ordered = sorted(sources,
                         key=lambda s: (0 if "极速" in labels.get(s, "") else 1,
                                        sources.index(s)))

        play_from = []
        play_url = []
        for idx, sid in enumerate(ordered[:MAX_SOURCES]):
            bucket = seen.get(sid) or {}
            if not bucket:
                continue
            eps = sorted(bucket.items(), key=lambda kv: kv[0])
            orig_name = labels.get(sid) or ("线路%s" % sid)
            line_name = "Zaka专线" if idx == 0 else orig_name
            play_from.append(line_name)
            play_url.append("#".join("%s$%s" % (v[0], v[1]) for _, v in eps))

        if not play_from:
            fallback = self._abs("/vodplay/%s-1-1.html" % vid) if vid else detail_url
            play_from.append("Zaka专线")
            play_url.append("正片$%s" % fallback)

        if desc:
            content = "📺ZakaTV专线直连 | %s | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl" % desc[:120]
        else:
            content = "📺ZakaTV专线加速播放 | 官方TG交流群：https://t.me/+3t5XRPPo9mlkZDRl | 4K高清原生极速画质"

        vod = {
            "vod_id": raw_id,
            "vod_name": title,
            "vod_pic": poster,
            "vod_bg": poster,
            "vod_background": poster,
            "vod_banner": poster,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("ZakaTV", "共%d条线路" % len(play_from)),
            "vod_content": content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url)
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        raw = str(id or "").strip()

        stream = raw
        if not self.isVideoFormat(raw):
            res = self._fetch(raw, referer=raw, stop_markers=(b"player_aaaa",))
            cand = self._stream(res.get("text", ""))
            if not cand:
                res = self._fetch(raw, referer=raw)
                cand = self._stream(res.get("text", ""))
            if cand:
                stream = cand

        is_stream = self.isVideoFormat(stream)
        return {
            "parse": 0 if is_stream else 1,
            "playUrl": "",
            "url": stream,
            "header": {
                "User-Agent": self._ua,
                "Referer": self.siteUrl + "/",
                "Accept": "*/*",
                "Connection": "keep-alive"
            }
        }

    def _probe(self, url, referer=""):
        headers = {
            "User-Agent": self._ua,
            "Referer": referer or (self.siteUrl + "/"),
            "Accept": "*/*",
            "Range": "bytes=0-1",
            "Connection": "close"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with self.opener.open(req, timeout=10) as resp:
                return resp.getcode(), resp.headers.get("Content-Type", ""), resp.geturl()
        except urllib.error.HTTPError as e:
            ctype = e.headers.get("Content-Type", "") if e.headers else ""
            return e.code, ctype, url
        except Exception as e:
            return -1, str(e), url

    def searchContent(self, key, quick, pg="1"):
        del quick
        page = fixed_int(pg, 1)
        kw = quote(str(key or "").strip())
        path = "/vodsearch/%s----------%d---.html" % (kw, page)

        res = self._fetch(path)
        html = res.get("text", "")
        vod_list = self._cards(html)
        pagecount = self._pagecount(html, page, len(vod_list))

        return {
            "page": page,
            "pagecount": pagecount,
            "limit": 30,
            "total": pagecount * 30,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]