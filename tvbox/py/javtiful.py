#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import random
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl
import time

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

_MEM_SHORTS_POOL = []

def _unescape(text):
    s = str(text or "")
    if "&" not in s:
        return s
    s = s.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return s

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
    for bad in ("placeholder", "blank.gif", "lazyload", "/logo"):
        if bad in low:
            return ""
    return u

def format_remarks(brand="📺ZakaTV", meta=""):
    clean_meta = re.sub(r"[\r\n\t]+", " ", str(meta or "")).strip()
    return "%s | %s" % (brand, clean_meta) if clean_meta else brand

def fixed_int(value, default=1):
    try:
        n = int(str(value or default).strip())
    except Exception:
        n = default
    return n if n >= 1 else default

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteName = "Javtiful"
        self.siteUrl = "https://javtiful.com"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}
        self._lang = "zh"
        self._ref = ""

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
        ua = str(self.options.get("ua") or "").strip()
        if ua:
            self._ua = ua
        site = str(self.options.get("site") or self.options.get("url") or "").strip()
        if site.startswith("http"):
            self.siteUrl = site.rstrip("/")
        return True

    def getName(self):
        return self.siteName

    def isVideoFormat(self, url):
        low = str(url or "").lower()
        if not low:
            return False
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "placeholder", "55287.mp4")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".mpd"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _abs(self, url):
        u = str(url or "").strip().replace("\\/", "/")
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        return (self.siteUrl + u) if u.startswith("/") else (self.siteUrl + "/" + u)

    def _path(self, path):
        p = str(path or "")
        if not p.startswith("/"):
            p = "/" + p
        if self._lang:
            return "/" + self._lang + p
        return p

    def _fetch_url(self, url, data=None, referer="", headers_custom=None):
        if not url:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        ref = referer or self._ref or (self.siteUrl + "/")
        headers = {
            "User-Agent": self._ua,
            "Referer": ref,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close"
        }
        if headers_custom:
            headers.update(headers_custom)

        req_data = None
        if data is not None:
            if isinstance(data, dict):
                req_data = urllib.parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
                headers["X-Requested-With"] = "XMLHttpRequest"
            elif isinstance(data, (bytes, str)):
                req_data = data.encode("utf-8") if isinstance(data, str) else data

        for attempt in range(2):
            try:
                req = urllib.request.Request(url, data=req_data, headers=headers)
                with self.opener.open(req, timeout=10) as resp:
                    code = resp.getcode()
                    final = resp.geturl()
                    raw = resp.read()
                    enc = (resp.headers.get("Content-Encoding", "") or "").lower()
                    if raw[:2] == b"\x1f\x8b" or "gzip" in enc:
                        try:
                            raw = gzip.decompress(raw)
                        except Exception:
                            pass
                    elif "deflate" in enc:
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            try:
                                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                            except Exception:
                                pass
                    text = ""
                    for codec in ("utf-8", "gbk", "latin1"):
                        try:
                            text = raw.decode(codec)
                            break
                        except Exception:
                            pass
                    if code == 200:
                        self._ref = final or url
                    return {"code": code, "text": text, "err": "", "final_url": final}
            except urllib.error.HTTPError as e:
                if e.code in (451, 403, 429) and attempt == 0:
                    time.sleep(0.3)
                    continue
                body = ""
                try:
                    body = e.read().decode("utf-8", "ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": body, "err": str(e), "final_url": url}
            except Exception as e:
                if attempt == 0:
                    time.sleep(0.3)
                    continue
                return {"code": -1, "text": "", "err": str(e), "final_url": url}
        return {"code": -1, "text": "", "err": "timeout", "final_url": url}

    def _fetch(self, path, data=None, referer="", headers_custom=None):
        if not path:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        if path.startswith("//"):
            path = "https:" + path
        if path.startswith("http"):
            return self._fetch_url(path, data, referer, headers_custom)
        return self._fetch_url(self.siteUrl + self._path(path), data, referer, headers_custom)

    def _get_sort_filters(self):
        return [
            {"n": "最新", "v": ""},
            {"n": "今日新增", "v": "added_today"},
            {"n": "本周新增", "v": "added_week"},
            {"n": "本月新增", "v": "added_month"},
            {"n": "今日热门", "v": "popular_today"},
            {"n": "本周热门", "v": "popular_week"},
            {"n": "本月热门", "v": "popular_month"},
            {"n": "最多点赞", "v": "most_liked"},
            {"n": "最多观看", "v": "most_viewed"}
        ]

    def homeContent(self, filter):
        classes = [
            {"type_name": "沉浸短视", "type_id": "shorts"},
            {"type_name": "为你推荐", "type_id": "for_you"},
            {"type_name": "综合视频", "type_id": "videos"},
            {"type_name": "精选有码", "type_id": "censored"},
            {"type_name": "高清无码", "type_id": "uncensored"},
            {"type_name": "智能减码", "type_id": "mosaic_removed"},
            {"type_name": "本周热门", "type_id": "popular_week"},
            {"type_name": "最多观看", "type_id": "most_viewed"},
            {"type_name": "最多点赞", "type_id": "most_liked"},
            {"type_name": "题材分类", "type_id": "categories"},
            {"type_name": "片商频道", "type_id": "channels"},
            {"type_name": "热门女优", "type_id": "actresses"}
        ]

        filters = {}
        if filter:
            sort_opts = self._get_sort_filters()
            filter_item = [{"key": "sort", "name": "排序方式", "init": "", "value": sort_opts}]
            for c in classes:
                cid = c["type_id"]
                if cid in ("for_you", "videos", "censored", "uncensored", "mosaic_removed", "popular_week", "most_viewed", "most_liked"):
                    filters[cid] = filter_item

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        res = self._fetch("/main")
        cards = self._parse_video_cards(res.get("text", ""))
        return {"list": cards[:24]}

    def _block_pic(self, block):
        for attr in ("data-front-lazy-src", "data-src", "data-original", "data-lazy-src", "src"):
            m = re.search(r"""\s%s=["']([^"']+)["']""" % attr, block, re.I)
            if m:
                cand = clean_pic(_unescape(m.group(1)))
                if cand:
                    return self._abs(cand)
        m = re.search(r"""background-image\s*:\s*url\(\s*['"]?([^'")]+)""", block, re.I)
        if m:
            cand = clean_pic(_unescape(m.group(1)))
            if cand:
                return self._abs(cand)
        return ""

    def _block_note(self, block):
        parts = []
        m = re.search(r"""class=["'][^"']*video-card__details[^"']*["'][^>]*>([\s\S]*?)</span>""", block, re.I)
        if m:
            inner = m.group(1)
            strong = re.search(r"<strong>([\s\S]*?)</strong>", inner, re.I)
            if strong:
                parts.append(clean_label(strong.group(1)))
            tail = clean_label(re.sub(r"<strong>[\s\S]*?</strong>", " ", inner))
            if tail:
                parts.append(tail)
        m = re.search(r"""class=["'][^"']*video-card__type[^"']*["'][^>]*>([^<]{1,24})<""", block, re.I)
        if m:
            t = clean_label(m.group(1))
            if t and t not in parts:
                parts.append(t)
        return " · ".join([x for x in parts if x])[:40]

    def _parse_video_cards(self, html):
        cards = []
        if not html:
            return cards
        seen = set()
        blocks = re.findall(r"""<article class=["']video-card[^>]*>([\s\S]*?)</article>""", html, re.I)
        for block in blocks:
            hm = re.search(r"""href=["']([^"']*?/(?:[a-z]{2}/)?video/(\d+)/([^"'#]+))["']""", block, re.I)
            if not hm:
                continue
            vid = hm.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            href = _unescape(hm.group(1))
            tm = re.search(r"""video-card__title[^>]*title=["']([^"']+)["']""", block, re.I)
            if tm:
                title = clean_label(_unescape(tm.group(1)))
            else:
                m_title = re.search(r"""class=["'][^"']*video-card__title[^"']*["'][^>]*>([\s\S]*?)</a>""", block, re.I)
                title = clean_label(m_title.group(1)) if m_title else ""
            if not title:
                alt_m = re.search(r"""alt=["']([^"']*)["']""", block, re.I)
                title = clean_label(re.sub(r"^Thumbnail for\s*", "", alt_m.group(1), flags=re.I)) if alt_m else ""
            if not title:
                continue

            pic = self._block_pic(block)
            note = self._block_note(block)

            cards.append({
                "vod_id": self._abs(href),
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": format_remarks(self.brandDirector, note),
                "style": {"type": "rect", "ratio": 1.78}
            })
        return cards

    def _parse_waterfall_cards(self, html, tag_type):
        items = []
        if not html:
            return items
        seen = set()

        if tag_type == "category":
            blocks = re.findall(r"""<a[^>]+href=["']([^"']*?/category/([^"'#]+))["'][^>]*>([\s\S]*?)</a>""", html, re.I)
            for href, slug, inner in blocks:
                clean_href = _unescape(href)
                if clean_href in seen:
                    continue
                seen.add(clean_href)
                pic = self._block_pic(inner)
                cnt_m = re.search(r'([\d,]+\s*Videos?)', inner, re.I)
                cnt = cnt_m.group(1).strip() if cnt_m else ""
                name_m = re.search(r'<div[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>([\s\S]*?)</div>', inner, re.I)
                if name_m:
                    name = clean_label(name_m.group(1))
                else:
                    name = unquote(slug).replace("-", " ").title()

                items.append({
                    "vod_id": "waterfall@@category@@" + quote(clean_href),
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": format_remarks(self.brandDirector, cnt),
                    "vod_tag": "folder",
                    "style": {"type": "rect", "ratio": 1.78}
                })

        elif tag_type == "channel":
            blocks = re.findall(r"""<a[^>]+href=["']([^"']*?/channel/([^"'#]+))["'][^>]*>([\s\S]*?)</a>""", html, re.I)
            for href, slug, inner in blocks:
                clean_href = _unescape(href)
                if clean_href in seen:
                    continue
                seen.add(clean_href)
                pic = self._block_pic(inner)
                cnt_m = re.search(r'([\d,]+\s*Videos?)', inner, re.I)
                cnt = cnt_m.group(1).strip() if cnt_m else ""
                name_m = re.search(r'<div[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>([\s\S]*?)</div>', inner, re.I)
                if name_m:
                    name = clean_label(name_m.group(1))
                else:
                    name = unquote(slug).replace("-", " ").title()

                items.append({
                    "vod_id": "waterfall@@channel@@" + quote(clean_href),
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": format_remarks(self.brandDirector, cnt),
                    "vod_tag": "folder",
                    "style": {"type": "rect", "ratio": 1.78}
                })

        elif tag_type == "actress":
            blocks = re.findall(r"""<a[^>]+href=["']([^"']*?/actress/([^"'#]+))["'][^>]*>([\s\S]*?)</a>""", html, re.I)
            for href, slug, inner in blocks:
                clean_href = _unescape(href)
                if clean_href in seen:
                    continue
                seen.add(clean_href)
                pic = self._block_pic(inner)
                cnt_m = re.search(r'([\d,]+\s*Videos?)', inner, re.I)
                cnt = cnt_m.group(1).strip() if cnt_m else ""
                name_m = re.search(r'<div[^>]*class=["\'][^"\']*name[^"\']*["\'][^>]*>([\s\S]*?)</div>', inner, re.I)
                if name_m:
                    name = clean_label(name_m.group(1))
                else:
                    name = unquote(slug).replace("-", " ").title()

                items.append({
                    "vod_id": "waterfall@@actress@@" + quote(clean_href),
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": format_remarks(self.brandDirector, cnt),
                    "vod_tag": "folder",
                    "style": {"type": "oval", "ratio": 1.0}
                })

        return items

    def _pagecount(self, html, page, count):
        nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", html or "")]
        nums = [n for n in nums if n <= 20000]
        if nums:
            return max(nums)
        return page + 1 if count >= 20 else page

    def _fetch_shorts_batch(self, cursor=""):
        target = self.siteUrl + "/shorts/feed"
        if cursor:
            target += "?cursor=" + quote(cursor)
        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/shorts",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "close"
        }
        res = self._fetch_url(target, headers_custom=headers)
        data = {}
        try:
            data = json.loads(res.get("text", ""))
        except Exception:
            data = {}
        items = data.get("items") or []
        next_c = str(data.get("cursor") or "").strip()
        return items, next_c

    def _append_shorts_cache(self, urls):
        global _MEM_SHORTS_POOL
        if not urls:
            return
        cached_str = self.getCache("jav_persistent_shorts_pool") or ""
        pool = [u for u in cached_str.split("\n") if u] if cached_str else list(_MEM_SHORTS_POOL)
        added = False
        for u in urls:
            if u and u not in pool:
                pool.append(u)
                added = True
        if added:
            if len(pool) > 300:
                pool = pool[-250:]
            _MEM_SHORTS_POOL = list(pool)
            self.setCache("jav_persistent_shorts_pool", "\n".join(pool))

    def _get_shorts_pool(self):
        global _MEM_SHORTS_POOL
        cached_str = self.getCache("jav_persistent_shorts_pool") or ""
        if cached_str:
            return [u for u in cached_str.split("\n") if u]
        return list(_MEM_SHORTS_POOL)

    def categoryContent(self, tid, pg, filter, extend):
        page = fixed_int(pg, 1)
        sort = ""
        if isinstance(extend, dict):
            sort = extend.get("sort", "")
        slug = str(tid).strip("/")

        if slug.startswith("waterfall@@") or "/category/" in slug or "/channel/" in slug or "/actress/" in slug:
            raw_path = slug
            if slug.startswith("waterfall@@"):
                raw_path = unquote(slug.split("@@")[2])

            target = raw_path if page == 1 else (raw_path + ("&page=%d" if "?" in raw_path else "?page=%d") % page)
            if sort:
                target += ("&sort=%s" if "?" in target else "?sort=%s") % sort

            res = self._fetch(target)
            html = res.get("text", "")
            cards = self._parse_video_cards(html)
            pagecount = self._pagecount(html, page, len(cards))
            return {
                "list": cards,
                "page": int(page),
                "pagecount": int(pagecount),
                "limit": 24,
                "total": int(pagecount * 24)
            }

        elif slug == "shorts":
            cur_cursor = self.getCache("jav_shorts_cur_%d" % page) or ""

            all_items = []
            seen_uids = set()
            cursor_step = cur_cursor

            for _ in range(2):
                batch_items, next_c = self._fetch_shorts_batch(cursor_step)
                if not batch_items:
                    break
                for it in batch_items:
                    uid = it.get("uid")
                    if uid and uid not in seen_uids:
                        seen_uids.add(uid)
                        all_items.append(it)
                    elif not uid:
                        all_items.append(it)
                cursor_step = next_c
                if not cursor_step:
                    break

            if cursor_step:
                self.setCache("jav_shorts_cur_%d" % (page + 1), cursor_step)

            new_media_urls = [it.get("media") for it in all_items if it.get("media")]
            self._append_shorts_cache(new_media_urls)

            short_cards = []
            for i, it in enumerate(all_items):
                caption = clean_label(it.get("caption") or ("Shorts %d" % (i + 1)))
                poster = it.get("poster") or ""
                media = it.get("media") or ""

                vod_id = "short_play@@%s@@%s@@%s" % (
                    quote(media),
                    quote(caption),
                    quote(poster)
                )
                short_cards.append({
                    "vod_id": vod_id,
                    "vod_name": caption,
                    "vod_pic": poster,
                    "vod_remarks": format_remarks(self.brandDirector, "短视频"),
                    "style": {"type": "rect", "ratio": 0.75}
                })

            has_more = bool(cursor_step) or (len(all_items) >= 4)
            calc_pagecount = int(page + 1 if has_more else page)
            std_limit = len(short_cards) if short_cards else 16
            calc_total = int(calc_pagecount * std_limit)

            return {
                "list": short_cards,
                "page": int(page),
                "pagecount": calc_pagecount,
                "limit": int(std_limit),
                "total": calc_total
            }

        elif slug == "for_you":
            target = "/foryou" if page == 1 else ("/foryou?page=%d" % page)
            if sort:
                target += ("&sort=%s" if "?" in target else "?sort=%s") % sort
            res = self._fetch(target)
            html = res.get("text", "")
            cards = self._parse_video_cards(html)
            pagecount = self._pagecount(html, page, len(cards))
            return {
                "list": cards,
                "page": int(page),
                "pagecount": int(pagecount),
                "limit": 24,
                "total": int(pagecount * 24)
            }

        elif slug == "categories":
            target = "/categories" if page == 1 else ("/categories?page=%d" % page)
            res = self._fetch(target)
            html = res.get("text", "")
            folders = self._parse_waterfall_cards(html, "category")
            pagecount = self._pagecount(html, page, len(folders))
            return {
                "list": folders,
                "page": int(page),
                "pagecount": int(pagecount),
                "limit": 24,
                "total": int(pagecount * 24)
            }

        elif slug == "channels":
            target = "/channels" if page == 1 else ("/channels?page=%d" % page)
            res = self._fetch(target)
            html = res.get("text", "")
            folders = self._parse_waterfall_cards(html, "channel")
            pagecount = self._pagecount(html, page, len(folders))
            return {
                "list": folders,
                "page": int(page),
                "pagecount": int(pagecount),
                "limit": 24,
                "total": int(pagecount * 24)
            }

        elif slug == "actresses":
            target = "/actresses" if page == 1 else ("/actresses?page=%d" % page)
            res = self._fetch(target)
            html = res.get("text", "")
            actresses = self._parse_waterfall_cards(html, "actress")
            pagecount = self._pagecount(html, page, len(actresses))
            return {
                "list": actresses,
                "page": int(page),
                "pagecount": int(pagecount),
                "limit": 24,
                "total": int(pagecount * 24)
            }

        else:
            base_map = {
                "videos": "/videos",
                "censored": "/censored",
                "uncensored": "/uncensored",
                "mosaic_removed": "/reducing-mosaic",
                "popular_week": "/videos?sort=popular_week",
                "most_viewed": "/videos?sort=most_viewed",
                "most_liked": "/videos?sort=most_liked"
            }
            path_part = base_map.get(slug, "/censored")
            params = []
            if page > 1:
                params.append("page=%d" % page)
            if sort:
                params.append("sort=%s" % sort)

            if params:
                sep = "&" if "?" in path_part else "?"
                target = "%s%s%s" % (path_part, sep, "&".join(params))
            else:
                target = path_part

            res = self._fetch(target)
            html = res.get("text", "")
            cards = self._parse_video_cards(html)
            pagecount = self._pagecount(html, page, len(cards))
            return {
                "list": cards,
                "page": int(page),
                "pagecount": int(pagecount),
                "limit": 24,
                "total": int(pagecount * 24)
            }

    def _jsonld(self, html):
        if not html:
            return {}
        for m in re.finditer(r"""<script[^>]+type=["']application/ld\+json["'][^>]*>([\s\S]*?)</script>""", html, re.I):
            try:
                data = json.loads(m.group(1).strip())
            except Exception:
                continue
            if isinstance(data, dict) and data.get("@type") == "VideoObject":
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "VideoObject":
                        return item
        return {}

    def _duration(self, iso):
        m = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", str(iso or "").strip(), re.I)
        if not m:
            return ""
        h = int(m.group(1) or 0)
        mi = int(m.group(2) or 0)
        s = int(m.group(3) or 0)
        if h:
            return "%02d:%02d:%02d" % (h, mi, s)
        return "%02d:%02d" % (mi, s)

    def detailContent(self, ids):
        raw_id = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()

        if raw_id.startswith("waterfall@@"):
            parts = raw_id.split("@@")
            target_href = unquote(parts[2])
            folder_title = target_href.strip("/").split("/")[-1].replace("-", " ").title()

            all_cards = []
            seen_ids = set()

            for p in range(1, 4):
                sep = "&" if "?" in target_href else "?"
                p_url = target_href if p == 1 else ("%s%spage=%d" % (target_href, sep, p))
                res = self._fetch(p_url)
                batch = self._parse_video_cards(res.get("text", ""))
                if not batch:
                    break
                for c in batch:
                    if c["vod_id"] not in seen_ids:
                        seen_ids.add(c["vod_id"])
                        all_cards.append(c)
                if len(all_cards) >= 60:
                    break

            episodes = []
            for i, c in enumerate(all_cards):
                c_name = re.sub(r'[\$#]', '', c["vod_name"])[:20]
                episodes.append("%02d·%s$%s" % (i + 1, c_name, c["vod_id"]))

            return {
                "list": [{
                    "vod_id": raw_id,
                    "vod_name": folder_title,
                    "vod_pic": all_cards[0]["vod_pic"] if all_cards else "",
                    "vod_actor": self.brandActor,
                    "vod_director": self.brandDirector,
                    "vod_remarks": format_remarks(self.brandDirector, "共%d部" % len(all_cards)),
                    "vod_content": "📺ZakaTV专线直连 | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl",
                    "vod_play_from": "Zaka专线",
                    "vod_play_url": "#".join(episodes) if episodes else "暂无正片$http://127.0.0.1"
                }]
            }

        elif raw_id.startswith("short_play@@"):
            parts = raw_id.split("@@")
            target_media = unquote(parts[1])
            target_caption = unquote(parts[2]) if len(parts) > 2 else "沉浸短视频"
            target_poster = unquote(parts[3]) if len(parts) > 3 else ""

            pool = self._get_shorts_pool()
            if len(pool) < 30:
                step_c = ""
                for _ in range(4):
                    fresh_batch, step_c = self._fetch_shorts_batch(step_c)
                    if not fresh_batch:
                        break
                    new_urls = [it.get("media") for it in fresh_batch if it.get("media")]
                    self._append_shorts_cache(new_urls)
                    if not step_c:
                        break
                pool = self._get_shorts_pool()

            episodes = ["本片$%s" % target_media]

            candidates = [u for u in pool if u and u != target_media]
            random.shuffle(candidates)

            for idx, cand_url in enumerate(candidates[:100]):
                episodes.append("%02d$%s" % (idx + 2, cand_url))

            return {
                "list": [{
                    "vod_id": raw_id,
                    "vod_name": target_caption or "沉浸短视",
                    "vod_pic": target_poster,
                    "vod_actor": self.brandActor,
                    "vod_director": self.brandDirector,
                    "vod_remarks": format_remarks(self.brandDirector, "沉浸连刷"),
                    "vod_content": "📺ZakaTV短视频沉浸连刷模式 | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl",
                    "vod_play_from": "Zaka专线",
                    "vod_play_url": "#".join(episodes)
                }]
            }

        else:
            url = self._abs(raw_id)
            res = self._fetch(url)
            html = res.get("text", "")

            title = ""
            m = re.search(r"""<h1[^>]*>([\s\S]*?)</h1>""", html, re.I)
            if m:
                title = clean_label(m.group(1))
            if not title:
                m = re.search(r"""<title>([\s\S]*?)</title>""", html, re.I)
                if m:
                    title = clean_label(re.split(r"\s*\|\s*", m.group(1))[0])
            if not title:
                title = "Javtiful Video"

            poster = ""
            for pat in (
                r"""<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']""",
                r"""<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']"""
            ):
                m = re.search(pat, html, re.I)
                if m:
                    poster = self._abs(_unescape(m.group(1)))
                    break
            if not poster:
                m = re.search(r"""data-front-lazy-src=["']([^"']+)["']""", html, re.I)
                if m:
                    poster = self._abs(clean_pic(_unescape(m.group(1))))

            actors = []
            for m in re.finditer(r"""href=["'][^"']*?/actress/([^"'#]+)["'][^>]*>([\s\S]*?)</a>""", html, re.I):
                name = clean_label(m.group(2))
                if name and len(name) <= 24 and name not in actors:
                    actors.append(name)
            actor = " / ".join(actors[:4])

            channel = ""
            m = re.search(r"""href=["'][^"']*?/channel/([^"'#]+)["'][^>]*>([\s\S]*?)</a>""", html, re.I):
                channel = clean_label(m.group(2))

            cates = []
            for m in re.finditer(r"""href=["'][^"']*?/category/([^"'#]+)["'][^>]*>([\s\S]*?)</a>""", html, re.I):
                name = clean_label(m.group(2))
                if name and len(name) <= 20 and name not in cates:
                    cates.append(name)

            ld = self._jsonld(html)
            if not poster and ld.get("thumbnailUrl"):
                thumb = ld.get("thumbnailUrl")
                if isinstance(thumb, list) and thumb:
                    thumb = thumb[0]
                poster = self._abs(_unescape(str(thumb)))
            if ld.get("name") and not title:
                title = clean_label(ld.get("name"))

            duration = self._duration(str(ld.get("duration") or ""))
            if not duration:
                m = re.search(r"""<strong>[\d]{2,3}</strong>\s*(\d{2}:\d{2}:\d{2})""", html)
                if m:
                    duration = m.group(1)

            vid = ""
            m = re.search(r"/(?:[a-z]{2}/)?video/(\d+)", url)
            if m:
                vid = m.group(1)

            play_page = url
            embed = str(ld.get("embedUrl") or "").strip()
            if embed:
                play_page = self._abs(embed)
            elif vid:
                play_page = self.siteUrl + "/embed/%s" % vid

            episodes = ["正片$%s" % play_page]
            rec_cards = self._parse_video_cards(html)
            rec_idx = 1
            for rc in rec_cards:
                r_url = self._abs(rc["vod_id"])
                if r_url != url:
                    clean_name = re.sub(r'[\$#]', '', rc["vod_name"])[:20]
                    episodes.append("%02d·%s$%s" % (rec_idx, clean_name, r_url))
                    rec_idx += 1
                if rec_idx > 24:
                    break

            remarks = [x for x in (duration, cates[0] if cates else "") if x]

            return {
                "list": [{
                    "vod_id": raw_id,
                    "vod_name": title,
                    "vod_pic": poster,
                    "vod_bg": poster,
                    "vod_background": poster,
                    "vod_banner": poster,
                    "vod_actor": actor or self.brandActor,
                    "vod_director": channel or self.brandDirector,
                    "vod_remarks": format_remarks(self.brandDirector, " · ".join(remarks)),
                    "vod_content": "📺ZakaTV专线直连 | %s | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl" % title,
                    "vod_play_from": "Zaka专线",
                    "vod_play_url": "#".join(episodes)
                }]
            }

    @staticmethod
    def _watch_config(html):
        if not html:
            return {}
        m = re.search(r"""<script[^>]+id=["']watch-config["'][^>]*>([\s\S]*?)</script>""", html, re.I)
        if not m:
            return {}
        try:
            cfg = json.loads(m.group(1).strip())
        except Exception:
            return {}
        return cfg if isinstance(cfg, dict) else {}

    def _playback(self, vid, referer=""):
        res = self._fetch("/embed/%s" % vid, referer=referer)
        html = res.get("text", "")
        cfg = self._watch_config(html)

        playback = cfg.get("playback") or {}
        endpoint = str(playback.get("endpoint") or "").strip()
        ticket = str(playback.get("ticket") or "").strip()
        if not (endpoint and ticket) and referer:
            res = self._fetch(referer)
            cfg = self._watch_config(res.get("text", ""))
            playback = cfg.get("playback") or {}
            endpoint = str(playback.get("endpoint") or "").strip()
            ticket = str(playback.get("ticket") or "").strip()

        if not (endpoint and ticket):
            return [], res.get("final_url") or ""

        url = endpoint if endpoint.startswith("http") else (self.siteUrl + endpoint)
        body = urllib.parse.urlencode({"ticket": ticket}).encode("utf-8")
        headers = {
            "User-Agent": self._ua,
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Referer": res.get("final_url") or (self.siteUrl + "/"),
            "Origin": self.siteUrl,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close"
        }

        for _ in range(2):
            try:
                req = urllib.request.Request(url, data=body, headers=headers)
                with self.opener.open(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8", "ignore"))
            except urllib.error.HTTPError as e:
                if e.code == 419 and _ == 0:
                    again = self._fetch("/embed/%s" % vid, referer=referer)
                    pb2 = self._watch_config(again.get("text", "")).get("playback") or {}
                    if pb2.get("ticket"):
                        ticket = str(pb2["ticket"])
                        body = urllib.parse.urlencode({"ticket": ticket}).encode("utf-8")
                        headers["Referer"] = again.get("final_url") or headers["Referer"]
                        continue
                return [], res.get("final_url") or ""
            except Exception:
                return [], res.get("final_url") or ""

            sources = data.get("sources") or []
            if data.get("success") and sources:
                def _size(s):
                    try:
                        return int(s.get("size") or 0)
                    except Exception:
                        return 0
                sources = sorted(sources, key=_size, reverse=True)
                return sources, res.get("final_url") or ""
            if data.get("renewTicket"):
                ticket = str(data["renewTicket"])
                body = urllib.parse.urlencode({"ticket": ticket}).encode("utf-8")
                continue
            break
        return [], res.get("final_url") or ""

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "").strip()
        page = self._abs(raw)

        if self.isVideoFormat(raw):
            return {
                "parse": 0,
                "playUrl": "",
                "url": raw,
                "header": self._stream_header(raw, self.siteUrl + "/shorts")
            }

        vid = ""
        m = re.search(r"/(?:[a-z]{2}/)?video/(\d+)", page) or \
            re.search(r"/(?:[a-z]{2}/)?embed/(\d+)", page) or \
            re.search(r"\b(\d{4,8})\b", page)
        if m:
            vid = m.group(1)

        if vid:
            sources, final = self._playback(vid, referer=page)
            if sources:
                best = sources[0]
                stream = str(best.get("src") or "").strip().replace("\\/", "")
                if stream:
                    return {
                        "parse": 0,
                        "playUrl": "",
                        "url": stream,
                        "header": self._stream_header(stream, final or page)
                    }

        return {
            "parse": 1,
            "playUrl": "",
            "url": (self.siteUrl + "/embed/%s" % vid) if vid else page,
            "header": {
                "User-Agent": self._ua,
                "Referer": page,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
            }
        }

    def _stream_header(self, stream_url, referer=""):
        header = {
            "User-Agent": self._ua,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        }
        if referer:
            header["Referer"] = referer
        m = re.match(r"^(https?://[^/]+)", str(stream_url or ""))
        if m:
            header["Origin"] = m.group(1)
        return header

    def searchContent(self, key, quick, pg="1"):
        page = fixed_int(pg, 1)
        kw = quote(str(key or "").strip(), safe="")
        path = "/search?q=%s" % kw
        if page > 1:
            path += "&page=%d" % page
        res = self._fetch(path)
        html = res.get("text", "")
        cards = self._parse_video_cards(html)
        pagecount = self._pagecount(html, page, len(cards))
        return {
            "list": cards,
            "page": int(page),
            "pagecount": int(pagecount),
            "limit": 24,
            "total": int(pagecount * 24)
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]
