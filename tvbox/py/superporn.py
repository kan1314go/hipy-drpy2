#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
import http.cookiejar
import http.client
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"


class PersistentHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, context=None):
        super(PersistentHTTPSHandler, self).__init__(context=context)
        self._pool = {}

    def https_open(self, req):
        host = req.host
        conn = self._pool.get(host)
        if conn is None or conn.sock is None:
            conn = http.client.HTTPSConnection(host, context=self._context, timeout=20)
            self._pool[host] = conn
        try:
            return self.do_open(lambda h, timeout=20: conn, req)
        except Exception:
            self._pool.pop(host, None)
            return super(PersistentHTTPSHandler, self).https_open(req)


class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.navUrls = ["https://x99dh.net", "https://x99dh.lat"]
        self.targetSiteName = "SuperPorn"
        self.cacheKey = "nav_direct_superporn_site_url"
        self.defaultHost = "https://cn.superporn.ws"
        self.baseHost = self.defaultHost

        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        try:
            self.ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except Exception:
            pass

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            PersistentHTTPSHandler(context=self.ctx)
        )
        self._warmed_up = False

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}

        self._refresh_site_url_from_nav()
        return True

    def getName(self):
        return "Zaka·SuperPorn·自愈版"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def _decompress(self, raw, enc=""):
        if not raw:
            return b""
        if raw.startswith(b"\x1f\x8b") or enc == "gzip":
            try:
                return gzip.decompress(raw)
            except Exception:
                pass
        elif enc == "deflate":
            try:
                return zlib.decompress(raw)
            except Exception:
                try:
                    return zlib.decompress(raw, -zlib.MAX_WBITS)
                except Exception:
                    pass
        return raw

    def _refresh_site_url_from_nav(self):
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "max-age=0",
            "Connection": "close",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }

        for nav in self.navUrls:
            raw = b""
            enc = ""
            try:
                req = urllib.request.Request(nav, headers=headers)
                with self.opener.open(req, timeout=8) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
            except urllib.error.HTTPError as e:
                try:
                    raw = e.read()
                    enc = getattr(e, "headers", {}).get("Content-Encoding", "")
                except Exception:
                    raw = b""
            except Exception:
                continue

            if not raw:
                continue

            decomp = self._decompress(raw, enc)
            try:
                html_text = decomp.decode("utf-8")
            except Exception:
                html_text = decomp.decode("latin1", errors="ignore")

            if not html_text:
                continue

            b64_blocks = re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', html_text)
            for b in b64_blocks:
                try:
                    dec = base64.b64decode(b).decode("utf-8", errors="ignore")
                    unq = urllib.parse.unquote(dec)
                    if "[" in unq and "{" in unq and self.targetSiteName in unq:
                        site_list = json.loads(unq)
                        if isinstance(site_list, list):
                            for item in site_list:
                                if str(item.get("name", "")).strip() == self.targetSiteName:
                                    direct_target_url = item.get("url", "").strip()
                                    if direct_target_url:
                                        parsed = urllib.parse.urlparse(direct_target_url)
                                        base_host = "%s://%s" % (parsed.scheme, parsed.netloc)
                                        self.baseHost = base_host
                                        self.setCache(self.cacheKey, base_host)
                                        return True
                except Exception:
                    continue

        cached_host = self.getCache(self.cacheKey)
        if cached_host and str(cached_host).startswith("http"):
            self.baseHost = str(cached_host).strip().rstrip("/")
            return True

        self.baseHost = self.defaultHost
        return False

    def _warmup_session(self):
        if self._warmed_up:
            return
        try:
            req = urllib.request.Request(self.baseHost + "/enter", headers={
                "User-Agent": self._ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "keep-alive"
            })
            with self.opener.open(req, timeout=15) as resp:
                resp.read()
            self._warmed_up = True
        except Exception:
            pass

    def _fetch(self, target_url, referer="", retry=2):
        if not target_url:
            return {"code": 0, "text": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.baseHost + target_url

        self._warmup_session()

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.baseHost + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        domain_retried = False

        for attempt in range(retry):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=20) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    raw = self._decompress(raw, enc)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "final_url": final_url}
            except urllib.error.HTTPError as e:
                if e.code in (404, 451, 500, 502, 503) and not domain_retried:
                    old_host = urllib.parse.urlparse(self.baseHost).netloc
                    self.delCache(self.cacheKey)
                    self._warmed_up = False
                    if self._refresh_site_url_from_nav():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.baseHost).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if e.code in (451, 403, 429) and attempt < retry - 1:
                    continue
                err_text = ""
                try:
                    raw_err = e.read()
                    enc = getattr(e, "headers", {}).get("Content-Encoding", "")
                    err_text = self._decompress(raw_err, enc).decode("utf-8", errors="ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": err_text, "final_url": target_url}
            except Exception:
                if not domain_retried:
                    old_host = urllib.parse.urlparse(self.baseHost).netloc
                    self.delCache(self.cacheKey)
                    self._warmed_up = False
                    if self._refresh_site_url_from_nav():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.baseHost).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if attempt < retry - 1:
                    continue
                return {"code": -1, "text": "", "final_url": target_url}

        return {"code": -1, "text": "", "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_name": "日本人", "type_id": "japanese"},
            {"type_name": "女同", "type_id": "lesbian"},
            {"type_name": "MILF", "type_id": "milf"},
            {"type_name": "成人动漫", "type_id": "hentai"},
            {"type_name": "丰臀", "type_id": "big-ass"},
            {"type_name": "黑人", "type_id": "ebony"},
            {"type_name": "拉丁裔", "type_id": "latina"},
            {"type_name": "肛交", "type_id": "anal"},
            {"type_name": "3P", "type_id": "threesome"},
            {"type_name": "内射", "type_id": "creampie"},
            {"type_name": "女性向", "type_id": "female-friendly"},
            {"type_name": "BBW", "type_id": "bbw"},
            {"type_name": "青少年", "type_id": "teen"},
            {"type_name": "Big tits", "type_id": "big-tits"},
            {"type_name": "异族", "type_id": "interracial"},
            {"type_name": "巨根", "type_id": "big-cock"},
            {"type_name": "亚洲人", "type_id": "asian"},
            {"type_name": "公开场合", "type_id": "public"},
            {"type_name": "群交", "type_id": "gangbang"},
            {"type_name": "POV", "type_id": "pov"},
            {"type_name": "喷射", "type_id": "squirting"},
            {"type_name": "成熟", "type_id": "mature"},
            {"type_name": "性高潮", "type_id": "orgasm"}
        ]

        result = {"class": classes}

        if filter:
            filter_item = [
                {
                    "key": "order",
                    "name": "排序",
                    "init": "",
                    "value": [
                        {"n": "默认排序", "v": ""},
                        {"n": "趋势上升", "v": "trending"},
                        {"n": "最受欢迎", "v": "popular"}
                    ]
                }
            ]
            filters = {}
            for item in classes:
                filters[item["type_id"]] = filter_item
            result["filters"] = filters

        return result

    def homeVideoContent(self):
        cate_res = self.categoryContent("japanese", "1", False, {})
        return {"list": cate_res.get("list", [])[:12]}

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        extend = extend if isinstance(extend, dict) else {}
        slug = str(tid).strip("/")

        page_str = str(pg).strip() if pg else "1"
        page_int = int(page_str) if page_str.isdigit() else 1

        if page_int > 1:
            target_path = "/%s/%s" % (slug, page_int)
        else:
            target_path = "/%s" % slug

        order_val = extend.get("order", "").strip()
        if order_val:
            target_path += "?order=" + urllib.parse.quote(order_val)

        target_url = self.baseHost + target_path
        res = self._fetch(target_url)
        html_text = res.get("text", "")

        vod_list = []
        cards_raw = html_text.split('class="thumb-video')
        for block in cards_raw[1:]:
            if 'thumb-video__avatar--serie' in block and '/video/' not in block[:300]:
                continue

            link_m = re.search(r'href=["\']([^"\']*/video/[^"\']+)["\']', block)
            if not link_m:
                continue
            vod_href = link_m.group(1).strip()

            alt_m = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', block)
            vod_name = alt_m.group(1).strip() if alt_m else ""
            if not vod_name:
                t_m = re.search(r'title=["\']([^"\']+)["\']', block)
                vod_name = t_m.group(1).strip() if t_m else ""

            if not vod_name or vod_name in ("无标题", "Oriental Delights"):
                continue

            img_m = re.search(r'data-src=["\'](https?://[^"\']+)["\']', block)
            if not img_m:
                img_m = re.search(r'src=["\'](https?://[^"\']+)["\']', block)
            vod_pic = img_m.group(1).strip() if img_m else ""

            dur_m = re.search(r'class=["\']duracion["\'][^>]*>([\s\S]*?)</span>', block)
            vod_remarks = re.sub(r'\s+', ' ', dur_m.group(1)).strip() if dur_m else ""

            clean_vid = vod_href
            if clean_vid.startswith("http"):
                clean_vid = re.sub(r'https?://[^/]+', '', clean_vid)
            if not clean_vid.startswith("/"):
                clean_vid = "/" + clean_vid

            vod_list.append({
                "vod_id": "vod" + clean_vid,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_remarks,
                "style": {"type": "rect", "ratio": 1.78}
            })

        if len(vod_list) > 0:
            pagecount = page_int + 50
            total = pagecount * len(vod_list)
        else:
            pagecount = page_int
            total = page_int * 20

        return {
            "page": page_int,
            "pagecount": pagecount,
            "limit": len(vod_list),
            "total": total,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        path = raw_id[3:] if str(raw_id).startswith("vod/") else str(raw_id)
        if not path.startswith("/"):
            path = "/" + path

        target_url = self.baseHost + path
        res = self._fetch(target_url)
        html_text = res.get("text", "")

        source_m = re.search(r'<source[^>]+src=["\']([^"\']+)["\']', html_text, re.I)
        direct_stream_url = source_m.group(1).strip() if source_m else ""

        if not direct_stream_url:
            js_stream_m = re.search(r'["\'](https?://[^"\']+\.mp4[^"\']*)["\']', html_text, re.I)
            if js_stream_m:
                direct_stream_url = js_stream_m.group(1).strip()

        iframe_m = re.search(r'<iframe[^>]+src=["\']([^"\']*/embed/[^"\']*)["\']', html_text, re.I)
        embed_url = iframe_m.group(1).strip() if iframe_m else ""

        title_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html_text, re.I)
        if not title_m:
            title_m = re.search(r'<title>([^<]+)</title>', html_text, re.I)
        raw_title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else "视频详情"

        pic_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
        if not pic_m:
            pic_m = re.search(r'poster=["\']([^"\']+)["\']', html_text, re.I)
        vod_pic = pic_m.group(1).strip() if pic_m else ""

        desc_m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
        vod_desc = desc_m.group(1).strip() if desc_m else raw_title

        play_from_list = []
        play_url_list = []

        if direct_stream_url:
            play_from_list.append("Zaka直连")
            play_url_list.append("正片$" + direct_stream_url)

        if embed_url:
            play_from_list.append("内核嗅探")
            play_url_list.append("备用$" + embed_url)
        elif not direct_stream_url:
            play_from_list.append("备用嗅探")
            play_url_list.append("正片$" + target_url)

        intro_text = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.tgGroup, vod_desc)

        escaped_intro = intro_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": raw_title,
                "vod_pic": vod_pic,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": "1080P超清",
                "vod_content": escaped_intro,
                "vod_play_from": "$$$".join(play_from_list),
                "vod_play_url": "$$$".join(play_url_list)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id).strip()
        is_embed = "/embed/" in url or "/video/" in url

        return {
            "parse": 1 if is_embed else 0,
            "jx": 0,
            "url": url,
            "header": {
                "User-Agent": self._ua,
                "Referer": self.baseHost + "/"
            }
        }

    def searchContent(self, key, quick, pg="1"):
        page_str = str(pg).strip() if pg else "1"
        page_int = int(page_str) if page_str.isdigit() else 1

        target_path = "/search?q=" + urllib.parse.quote(key)
        if page_int > 1:
            target_path += "&p=" + str(page_int)

        target_url = self.baseHost + target_path
        res = self._fetch(target_url)
        html_text = res.get("text", "")

        vod_list = []
        cards_raw = html_text.split('class="thumb-video')
        for block in cards_raw[1:]:
            if 'thumb-video__avatar--serie' in block and '/video/' not in block[:300]:
                continue

            link_m = re.search(r'href=["\']([^"\']*/video/[^"\']+)["\']', block)
            if not link_m:
                continue
            vod_href = link_m.group(1).strip()

            alt_m = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', block)
            vod_name = alt_m.group(1).strip() if alt_m else ""
            if not vod_name:
                t_m = re.search(r'title=["\']([^"\']+)["\']', block)
                vod_name = t_m.group(1).strip() if t_m else ""

            if not vod_name or vod_name in ("无标题", "Oriental Delights"):
                continue

            img_m = re.search(r'data-src=["\'](https?://[^"\']+)["\']', block)
            if not img_m:
                img_m = re.search(r'src=["\'](https?://[^"\']+)["\']', block)
            vod_pic = img_m.group(1).strip() if img_m else ""

            dur_m = re.search(r'class=["\']duracion["\'][^>]*>([\s\S]*?)</span>', block)
            vod_remarks = re.sub(r'\s+', ' ', dur_m.group(1)).strip() if dur_m else ""

            clean_vid = vod_href
            if clean_vid.startswith("http"):
                clean_vid = re.sub(r'https?://[^/]+', '', clean_vid)
            if not clean_vid.startswith("/"):
                clean_vid = "/" + clean_vid

            vod_list.append({
                "vod_id": "vod" + clean_vid,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_remarks,
                "style": {"type": "rect", "ratio": 1.78}
            })

        if len(vod_list) > 0:
            pagecount = page_int + 50
            total = pagecount * len(vod_list)
        else:
            pagecount = page_int
            total = page_int * 20

        return {
            "page": page_int,
            "pagecount": pagecount,
            "limit": len(vod_list),
            "total": total,
            "list": vod_list
        }

    def action(self, action):
        if action == "toast":
            return {"msg": "当前有效发布域: %s" % self.baseHost}
        return {"msg": "Zaka蜘蛛运行就绪"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}
