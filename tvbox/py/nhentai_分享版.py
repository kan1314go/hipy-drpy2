# -*- coding: utf-8 -*-
"""
nHentai 图源（API v2）

旧版 /api/galleries/* 已被官方废弃，现在返回 403「Use new API https://nhentai.net/api/v2/docs」，
这就是之前分类下空白的原因。本版改用 v2 接口：

  GET /api/v2/cdn                     -> {"image_servers":[...], "thumb_servers":[...]}
  GET /api/v2/galleries?page=N        -> {"result":[{id,media_id,english_title,thumbnail,num_pages,...}],
                                          "num_pages":..,"per_page":25,"total":..}
  GET /api/v2/galleries/popular?period=day|week|month
  GET /api/v2/galleries/tagged?tag_id=<id>&page=N
  GET /api/v2/galleries/{id}          -> {title:{english,pretty,japanese},cover:{path},pages:[{path}],tags:[...]}
  GET /api/v2/tags/{tag_type}/{slug}  -> 按 slug 换 tag_id（本版做兜底用）

注意：
  * thumbnail / cover / pages 里的 path 都是相对路径，必须拼上 /api/v2/cdn 返回的服务器；
    官方明确要求「按返回的 path 原样使用」，不要自己猜扩展名。
  * 浏览接口不强制 API Key；如果你在 nhentai 账号里生成了 key，可以配置 {"key": "..."}。
"""

import sys
import os
import re
import json
import time
import gzip
import zlib
import ssl
import html as html_lib
import urllib.parse
import urllib.request
import urllib.error

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    BaseSpider = object

# Cloudflare 对「非浏览器 UA」比较敏感，这里用普通浏览器 UA 提高成功率
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
BASE = "https://nhentai.net"
API = BASE + "/api/v2"
TIMEOUT = 20

# 你的 nhentai API Key（账号设置 → API Keys 生成）。
# 带 Key 的请求走已认证通道，能绕过 Cloudflare 对匿名请求的 403。
# 想换/停用：配置里传 {"key": "新的key"}，传 {"key": ""} 则不带 Key。
DEFAULT_KEY = ""      # 分享版：不含任何 Key，用的人填自己的

# slug -> tag_id：**仅作兜底**。真实 id 一律以 /api/v2/tags/{type}/{slug} 的返回为准，
# 因为 v2 的编号和旧接口不一致（实测 doujinshi 是 33172，不是旧表里的 9098，
# 这正是「除中文/英文外分类全空」的原因）。
SLUG2ID = {
    "language/chinese": 29963,
    "language/english": 12227,
    "language/japanese": 6346,
    "category/doujinshi": 33172,
}

# 分类 slug -> 中文显示名（分类列表以 API 返回为准，这里只负责显示）
CAT_LABELS = {
    "doujinshi": "同人志",
    "manga": "单行本",
    "artistcg": "画集",
    "gamecg": "游戏CG",
    "imageset": "图集",
    "cosplay": "Cos写真",
    "asianporn": "亚洲",
    "western": "西方",
    "non-h": "非H",
}

CLASSES = [
    {"type_id": "popular?period=day", "type_name": "热门榜单"},
    {"type_id": "language/chinese", "type_name": "中文"},
    {"type_id": "language/english", "type_name": "英文"},
    {"type_id": "language/japanese", "type_name": "日文"},
    {"type_id": "category/doujinshi", "type_name": "同人志"},
    {"type_id": "category/manga", "type_name": "单行本"},
    {"type_id": "category/imageset", "type_name": "图集"},
    {"type_id": "category/cosplay", "type_name": "Cos写真"},
    {"type_id": "category/western", "type_name": "西方"},
    {"type_id": "category/non-h", "type_name": "非H"},
]


class Spider(BaseSpider):
    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self.siteName = "nHentai"
        self.apikey = DEFAULT_KEY
        self._cdn_cache = None
        self._tag_cache = {}
        self._list_cache = {}
        self._last_code = -1
        self._last_err = ""
        self._last_html = 0
        self._last_api_code = -1
        self._last_html_code = -1
        self._diag_tag = ""
        self._key_ok = None
        self._cat_map = None
        self._cat_list = None
        self._first_ids = {}

    def getName(self):
        return self.siteName

    def init(self, extend=""):
        self.headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            # 关键：Cloudflare 会对部分接口回 brotli(br)，而标准库解不了 br，
            # 表现就是「某些分类明明接口有数据，却解析成空」。直接要明文最稳。
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }
        self.baseUrl = BASE
        # extend 可以是 {"key": "APIKEY"} 或 {"base": "https://镜像"}；{"key": ""} 表示不带 Key
        if isinstance(extend, dict):
            if extend.get("base"):
                self.baseUrl = str(extend["base"]).rstrip("/")
            if "key" in extend:
                self.apikey = str(extend.get("key") or "").strip()
        elif extend and str(extend).strip().startswith("http"):
            self.baseUrl = str(extend).strip().rstrip("/")
        self.apiUrl = self.baseUrl + "/api/v2"
        self.headers["Referer"] = self.baseUrl + "/"
        # 补一组「同源 XHR」的浏览器头，降低 Cloudflare 挑战概率
        self.headers.update({
            "Origin": self.baseUrl,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        })
        self._init_opener()

    def _init_opener(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        handlers = [urllib.request.HTTPSHandler(context=ctx)]
        p = self._proxies()
        if p:
            handlers.append(urllib.request.ProxyHandler(p))
        self.opener = urllib.request.build_opener(*handlers)

    def getDependence(self):
        return []

    def _proxies(self):
        p = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") \
            or os.environ.get("all_proxy") or os.environ.get("ALL_PROXY")
        return {"http": p, "https": p} if p else None

    def _headers(self):
        h = dict(self.headers)
        if self.apikey:
            h["Authorization"] = "Key " + self.apikey
        return h

    def _fetch(self, url):
        """返回 (状态码, 文本)；同时记录 _last_code / _last_err 供诊断卡片使用"""
        self._last_err = ""
        try:
            req = urllib.request.Request(url, headers=self._headers())
            resp = self.opener.open(req, timeout=TIMEOUT)
            with resp:
                code = resp.getcode()
                self._last_code = code
                raw = resp.read()
                enc = ""
                try:
                    enc = (resp.headers.get("Content-Encoding", "") or "").lower()
                except Exception:
                    enc = ""
            # 服务端无视 Accept-Encoding 直接回 br 时，换明文再取一次
            if "br" in enc:
                self._last_err = "br"
                h2 = dict(self._headers())
                h2["Accept-Encoding"] = "identity"
                req2 = urllib.request.Request(url, headers=h2)
                with self.opener.open(req2, timeout=TIMEOUT) as r2:
                    raw = r2.read()
                    enc = ""
                    self._last_code = r2.getcode()
            if raw[:2] == b"\x1f\x8b" or "gzip" in enc:
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            elif "deflate" in enc:
                try:
                    raw = zlib.decompress(raw)
                except Exception:
                    pass
            return self._last_code, raw.decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            self._last_code = e.code
            self._last_err = "HTTP %s" % e.code
            return e.code, ""
        except Exception as e:
            self._last_code = -1
            self._last_err = str(e)[:60]
            return -1, ""

    def _get_json(self, url, tries=3):
        for i in range(tries):
            code, text = self._fetch(url)
            self._last_api_code = code
            if code == 200 and text.strip():
                try:
                    return json.loads(text)
                except Exception as e:
                    self._last_err = "json: %s" % str(e)[:40]
                    return None
            if code == 429:          # 官方要求把 429 当作退避信号
                time.sleep(2 + i * 2)
                continue
            if code == 403 and i == 0:
                # Cloudflare 的 403 有时是瞬时的，等一下再试一次
                time.sleep(1.2)
                continue
            if code in (401, 403):
                return None
            time.sleep(0.6)
        return None

    def _get_html(self, url):
        code, text = self._fetch(url)
        self._last_html_code = code
        return text if code == 200 else ""

    # ---------------- CDN ----------------

    def _cdn(self):
        """返回 (image_base, thumb_base)"""
        if self._cdn_cache:
            return self._cdn_cache
        data = self._get_json(self.apiUrl + "/cdn") or {}
        imgs = data.get("image_servers") or ["https://i1.nhentai.net"]
        thumbs = data.get("thumb_servers") or ["https://t1.nhentai.net"]
        self._cdn_cache = (str(imgs[0]).rstrip("/"), str(thumbs[0]).rstrip("/"))
        return self._cdn_cache

    def _img(self, path):
        if not path:
            return ""
        p = str(path).strip()
        if p.startswith("http"):
            return p
        return self._cdn()[0] + "/" + p.lstrip("/")

    def _thumb(self, path):
        if not path:
            return ""
        p = str(path).strip()
        if p.startswith("http"):
            return p
        return self._cdn()[1] + "/" + p.lstrip("/")

    # ---------------- 解析 ----------------

    def _clean(self, s):
        if not s:
            return ""
        t = html_lib.unescape(str(s))
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _parse_list(self, data):
        """兼容两种返回：popular 直接给数组，galleries/tagged 给 {"result": [...]}"""
        items = []
        if isinstance(data, dict):
            galleries = data.get("result") or []
        elif isinstance(data, list):
            galleries = data
        else:
            galleries = []

        for g in galleries:
            if not isinstance(g, dict):
                continue
            gid = str(g.get("id") or "")
            if not gid:
                continue
            title = self._clean(g.get("english_title") or g.get("japanese_title")) or gid
            cover = self._thumb(g.get("thumbnail") or "")
            items.append({
                "id": gid,
                "media_id": str(g.get("media_id") or ""),
                "title": title,
                "cover": cover,
                "num_pages": g.get("num_pages") or 0,
                "japanese_title": self._clean(g.get("japanese_title")),
            })
        return items

    def _vod(self, it):
        remark = "📖 %dP" % it["num_pages"] if it.get("num_pages") else "📖 nHentai"
        return {
            "vod_id": it["id"],
            "vod_name": it["title"] or ("本子 %s" % it["id"]),
            "vod_pic": it["cover"],
            "vod_remarks": remark,
        }

    def _pagecount(self, data, pg):
        """兼容 popular 接口（顶层数组，无分页信息）"""
        if isinstance(data, list):
            return pg + 1
        try:
            n = int(data.get("num_pages") or 0)
            if n > 0:
                return n
        except Exception:
            pass
        return pg + 1

    # ---------------- 标签 id ----------------

    def _categories(self):
        """拉取 /api/v2/tags/category，得到「真实分类名/slug -> id」对照表。
        v2 的分类 slug 和我原先猜的不完全一致（图集/Cos/西方/非H 会 400），
        所以以服务端返回为准。"""
        if self._cat_map is not None:
            return self._cat_map
        m, names = {}, []
        data = self._get_json(self.apiUrl + "/tags/category")
        arr = None
        if isinstance(data, list):
            arr = data
        elif isinstance(data, dict):
            arr = data.get("result") or data.get("data") or data.get("tags")
        if isinstance(arr, list):
            for t in arr:
                if not isinstance(t, dict) or not t.get("id"):
                    continue
                slug = str(t.get("slug") or "").strip().lower()
                name = str(t.get("name") or "").strip().lower()
                for key in (slug, name):
                    if key:
                        m[key] = t["id"]
                        m["category/" + key] = t["id"]
                if slug:
                    names.append((slug, str(t.get("name") or slug)))
        self._cat_map = m
        self._cat_list = names
        return m

    def _tag_id(self, slug):
        """slug -> tag_id：先查分类表，再问单个标签接口，最后用内置表兜底。"""
        if slug in self._tag_cache:
            return self._tag_cache[slug]

        key = str(slug)
        if "/" in key:
            short = key.split("/", 1)[1].lower()
        else:
            short = key.lower()
        cats = self._categories()
        if short in cats:
            self._tag_cache[slug] = cats[short]
            return cats[short]

        parts = key.split("/", 1)
        if len(parts) == 2:
            url = "%s/tags/%s/%s" % (self.apiUrl, parts[0], urllib.parse.quote(parts[1]))
            data = self._get_json(url)
            if isinstance(data, dict) and data.get("id"):
                self._tag_cache[slug] = data["id"]
                return data["id"]

            # 兜底：按名字搜标签（slug 改名时还能找到）
            try:
                q = urllib.parse.quote(parts[1].replace("-", " "))
                found = self._get_json("%s/tags/search?query=%s" % (self.apiUrl, q))
                cands = None
                if isinstance(found, dict):
                    cands = found.get("result") or found.get("data")
                elif isinstance(found, list):
                    cands = found
                if isinstance(cands, list):
                    for t in cands:
                        if isinstance(t, dict) and t.get("id") and t.get("type") == parts[0]:
                            self._tag_cache[slug] = t["id"]
                            return t["id"]
            except Exception:
                pass

        # 兜底二：内置表
        tid = SLUG2ID.get(slug)
        if tid:
            self._tag_cache[slug] = tid
        return tid

    # ---------------- 列表 ----------------

    def homeContent(self, filter):
        # 分类以 /api/v2/tags/category 返回的真实 slug 为准，
        # 避免我硬编码的 slug 和服务端不一致（400）。
        classes = [
            {"type_id": "popular?period=day", "type_name": "热门榜单"},
            {"type_id": "language/chinese", "type_name": "中文"},
            {"type_id": "language/english", "type_name": "英文"},
            {"type_id": "language/japanese", "type_name": "日文"},
        ]
        try:
            self._categories()
        except Exception:
            pass
        cats = self._cat_list or []
        if cats:
            for slug, name in cats:
                classes.append({"type_id": "category/" + slug,
                                "type_name": CAT_LABELS.get(slug, name)})
        else:
            # 拉不到分类表时退回静态列表
            classes.extend([c for c in CLASSES
                            if c["type_id"].startswith("category/")])
        result = {"class": classes}
        try:
            result["list"] = self.categoryContent("", 1, None, None)["list"]
        except Exception:
            result["list"] = []
        return result

    def homeVideoContent(self):
        return self.categoryContent("popular?period=day", 1, None, None)

    def categoryContent(self, tid, page, filter, ext):
        try:
            pg = max(int(page), 1) if page else 1
        except Exception:
            pg = 1
        tid = (tid or "").strip()

        try:
            html_url = ""
            data = None
            if tid.startswith("popular"):
                period = re.search(r"period=(\w+)", tid)
                period = period.group(1) if period else "day"
                html_url = "%s/popular?period=%s&page=%d" % (self.baseUrl, period, pg)
                data = self._get_cached(
                    "%s/galleries/popular?period=%s&page=%d" % (self.apiUrl, period, pg))
            elif tid:
                # 分类：先拿真实 tag_id（API 优先，内置表兜底），再走 tagged；
                # 拿不到 id 就直接走 HTML 列表页，别返回空。
                html_url = "%s/%s/?page=%d" % (self.baseUrl, tid, pg)
                tag_id = tid if tid.isdigit() else self._tag_id(tid)
                self._diag_tag = str(tag_id or "未解析")
                if tag_id:
                    data = self._get_cached(
                        "%s/galleries/tagged?tag_id=%s&page=%d" % (self.apiUrl, tag_id, pg))
            else:
                # 「全部最新」已移除：无分类时统一走热门榜单（/galleries 被 CF 拦）
                html_url = "%s/popular?period=day&page=%d" % (self.baseUrl, pg)
                data = self._get_cached(
                    "%s/galleries/popular?period=day&page=%d" % (self.apiUrl, pg))

            items = self._parse_list(data) if data else []
            pc = self._pagecount(data, pg) if data else pg

            # 分页保护：有些接口（popular）并不认 page 参数，翻第 2 页返回的还是同一批。
            # 记住首页首条 id，之后若首条没变，就判定「该分类不支持翻页」，直接收尾，
            # 避免 TVBox 一直往下加载同一批造成列表重复。
            key = tid or "all"
            first_id = items[0]["id"] if items else ""
            if pg == 1 and first_id:
                self._first_ids[key] = first_id
            elif pg > 1 and first_id:
                prev_first = self._first_ids.get(key)
                if prev_first and first_id == prev_first:
                    return {"list": [], "page": pg, "pagecount": pg,
                            "limit": 25, "total": pg * 25}
                if isinstance(data, list):
                    # 顶层数组没有 num_pages，用 pg+1 继续试
                    pc = pg + 1
                elif pc <= pg:
                    pc = pg + 1

            # 接口空/超时（大分类如日文容易超时）时，退回 HTML 列表页
            if not items and html_url:
                html = self._get_html(html_url)
                self._last_html = len(html or "")
                items = self._parse_html_list(html)
                pc = pg + 1 if len(items) >= 20 else pg

            if not items:
                # 返回一张诊断卡，TVBox 里能直接看到是哪一步失败（HTTP 码/HTML 长度）
                return {"list": [self._diag_card(tid, pg)], "page": pg,
                        "pagecount": pg, "limit": 25, "total": 1}

            # popular / galleries 可能返回顶层数组，没有 per_page/total 字段
            per_page, total = 25, pc * 25
            if isinstance(data, dict):
                try:
                    per_page = int(data.get("per_page") or 25)
                except Exception:
                    per_page = 25
                try:
                    total = int(data.get("total") or pc * 25)
                except Exception:
                    total = pc * 25

            return {
                "list": [self._vod(it) for it in items],
                "page": pg,
                "pagecount": pc,
                "limit": per_page,
                "total": total,
            }
        except Exception:
            return {"list": [], "page": pg, "pagecount": pg, "limit": 25, "total": 0}

    def _key_status(self):
        """探测 API Key 是否被服务端接受（请求 /api/v2 根路径，200 视为有效）"""
        if self._key_ok is not None:
            return self._key_ok
        if not self.apikey:
            self._key_ok = False
            return False
        code, _ = self._fetch(self.apiUrl)
        self._key_ok = (code == 200)
        self._key_code = code
        return self._key_ok

    def _diag_card(self, tid, pg):
        """分类为空时塞一张诊断卡：分别显示接口码、页面码、tag_id、Key 状态"""
        ok = self._key_status()
        kc = getattr(self, "_key_code", "")
        key_txt = ("✓" if ok else "✗%s" % (kc if kc else "")) if self.apikey else "无"
        return {
            "vod_id": "diag",
            "vod_name": "[诊断] %s" % (tid or "全部最新"),
            "vod_pic": "",
            "vod_remarks": "接口%s | 页面%s | tag %s | key%s" % (
                getattr(self, "_last_api_code", "?"),
                getattr(self, "_last_html_code", "?"),
                getattr(self, "_diag_tag", "无"),
                key_txt),
        }

    def _get_cached(self, url):
        """20 秒内重复请求走缓存：nhentai 对高频请求会临时封禁"""
        now = time.time()
        hit = self._list_cache.get(url)
        if hit and now - hit[0] < 20:
            return hit[1]
        data = self._get_json(url)
        if data:
            self._list_cache[url] = (now, data)
        return data

    # ---------------- 搜索 ----------------

    def searchContent(self, key, quick, page="1"):
        try:
            pg = max(int(page), 1) if page else 1
        except Exception:
            pg = 1
        q = urllib.parse.quote(str(key or ""))

        # v2 文档里没有独立的画廊搜索接口，先试 galleries?query=
        data = self._get_json("%s/galleries?query=%s&page=%d" % (self.apiUrl, q, pg))
        if data and data.get("result"):
            items = self._parse_list(data)
            pc = self._pagecount(data, pg)
            return {"list": [self._vod(it) for it in items], "page": pg,
                    "pagecount": pc, "limit": 25, "total": pc * 25}

        # 兜底：老式 HTML 搜索页
        html = self._get_html("%s/search/?q=%s&page=%d" % (self.baseUrl, q, pg))
        items = self._parse_html_list(html)
        pc = pg + 1 if len(items) >= 20 else pg
        return {"list": [self._vod(it) for it in items], "page": pg,
                "pagecount": pc, "limit": 25, "total": pc * 25}

    def _parse_html_list(self, html):
        """HTML 兜底解析：按 <a href="/g/ID/"> 整块取，避免相邻卡片的窗口重叠串数据"""
        items = []
        seen = set()
        if not html:
            return items

        for m in re.finditer(
                r'<a[^>]+href="(?:https?://[^"]+)?/g/(\d+)/?"[^>]*>([\s\S]{0,1500}?)</a>',
                html, re.I):
            gid, inner = m.group(1), m.group(2)
            if gid in seen:
                continue
            seen.add(gid)

            im = re.search(r'(?:data-src|data-original|src)="([^"]+)"', inner, re.I)
            cover = im.group(1) if im else ""
            if cover.startswith("//"):
                cover = "https:" + cover
            if cover and not cover.startswith("http"):
                cover = ""

            tm = re.search(r'alt="([^"]*)"', inner, re.I) or \
                re.search(r'title="([^"]*)"', m.group(0), re.I)
            title = self._clean(tm.group(1)) if tm else ""
            if not title:
                cm = re.search(r'/g/%s/[^"]*"[^>]*>([\s\S]{1,300}?)</a>' % gid, html, re.I)
                if cm:
                    title = self._clean(re.sub(r"<[^>]+>", " ", cm.group(1)))

            items.append({
                "id": gid,
                "media_id": "",
                "title": title or gid,
                "cover": cover,
                "num_pages": 0,
            })
        return items

    # ---------------- 详情 ----------------

    def detailContent(self, ids):
        raw = ids[0] if ids else ""
        gm = re.search(r'/g/(\d+)', str(raw))
        if gm:
            gid = gm.group(1)
        else:
            dm = re.search(r'(\d+)', str(raw))
            gid = dm.group(1) if dm else ""
        if not gid:
            return {"list": [{"vod_id": str(raw), "vod_name": "解析失败",
                              "vod_play_from": "nHentai", "vod_play_url": ""}]}

        info = self._get_json("%s/galleries/%s" % (self.apiUrl, gid))
        if not info:
            return {"list": [{"vod_id": gid, "vod_name": "获取详情失败（接口无返回）",
                              "vod_play_from": "nHentai", "vod_play_url": ""}]}

        title_obj = info.get("title") or {}
        title = self._clean(title_obj.get("english") or title_obj.get("pretty")
                            or title_obj.get("japanese")) or ("本子 %s" % gid)

        cover = self._img((info.get("cover") or {}).get("path") or "")
        if not cover:
            cover = self._thumb((info.get("thumbnail") or {}).get("path") or "")

        pages = info.get("pages") or []
        imgs = []
        for p in pages:
            if isinstance(p, dict) and p.get("path"):
                imgs.append(self._img(p.get("path")))
        if not imgs and info.get("num_pages"):
            # 没有 pages 时按官方规则不要自己拼，直接留空，避免触发 CDN 封禁
            imgs = []

        tags = info.get("tags") or []
        by_type = {}
        for t in tags:
            if isinstance(t, dict):
                by_type.setdefault(t.get("type"), []).append(self._clean(t.get("name")))
        languages = by_type.get("language") or []
        artists = by_type.get("artist") or []
        categories = by_type.get("category") or []
        parodies = by_type.get("parody") or []

        num_pages = info.get("num_pages") or len(pages)
        upload = info.get("upload_date") or 0
        date_str = time.strftime("%Y-%m-%d", time.gmtime(upload)) if upload else ""
        content = " | ".join(filter(None, [
            " ".join(categories), " ".join(languages), " ".join(parodies),
            "%dP" % num_pages, date_str,
        ]))

        play_url = "全集$pics://" + "&&".join(imgs) if imgs else ""
        vod = {
            "vod_id": gid,
            "vod_name": title,
            "vod_pic": cover,
            "vod_bg": cover,
            "vod_remarks": "%dP" % num_pages,
            "vod_play_from": "nHentai",
            "vod_play_url": play_url,
            "vod_content": content or "nHentai 本子",
            "vod_director": " ".join(artists) or "nHentai",
            "vod_actor": " ".join(languages) or "-",
        }
        return {"list": [vod]}

    def playerContent(self, flag, pid, vipFlags):
        target = str(pid).strip()
        if "$" in target:
            target = target.split("$", 1)[1]
        if not target:
            return {"parse": 0, "url": "", "msg": "图片为空"}
        return {
            "parse": 0,
            "url": target,
            "header": json.dumps({
                "User-Agent": UA,
                "Referer": self.baseUrl + "/",
                "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
            }),
        }

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.opener = None


if __name__ == "__main__":
    sp = Spider()
    sp.init({})
    print("分类数:", len(sp.homeContent(True)["class"]))
    r = sp.categoryContent("", 1, None, None)
    print("首页条数:", len(r["list"]), "总页:", r["pagecount"])
    for v in r["list"][:3]:
        print("  -", v["vod_name"][:30], "|", v["vod_remarks"], "|", v["vod_pic"][:60])
