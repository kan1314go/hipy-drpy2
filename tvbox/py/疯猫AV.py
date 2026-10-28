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
from urllib.parse import urlparse, quote, unquote
import http.cookiejar
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

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

def clean_label(text):
    t = str(text or "").strip()
    t = re.sub(r"[\$#\r\n\t]+", " ", t)
    return t.strip()

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://n-20261020.fmav786.icu"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

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
        return True

    def getName(self):
        return "ZakaTV"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def _fetch(self, target_url, data=None, referer=""):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        req_data = None
        if data is not None:
            if isinstance(data, dict):
                req_data = urllib.parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            elif isinstance(data, (bytes, str)):
                req_data = data.encode("utf-8") if isinstance(data, str) else data

        last_err = ""
        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, data=req_data, headers=headers)
                with self.opener.open(req, timeout=8) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "bytes": raw, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (451, 403, 429) and attempt == 0:
                    continue
                err_raw = ""
                try:
                    err_raw = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": err_raw, "bytes": b"", "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": last_err, "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_name": "🔥本周热播", "type_id": "route_actor_hot"},
            {"type_name": "⏱️10分钟以上", "type_id": "route_role_10min"},
            {"type_name": "91加精视频", "type_id": "x4B4"},
            {"type_name": "91最新视频", "type_id": "S4B4"},
            {"type_name": "快播系列", "type_id": "F4B4"},
            {"type_name": "国产自拍", "type_id": "Z4B4"},
            {"type_name": "网曝吃瓜", "type_id": "94B4"},
            {"type_name": "AI短剧", "type_id": "b4B4"},
            {"type_name": "日韩系列", "type_id": "W4B4"},
            {"type_name": "探花约炮", "type_id": "w4B4"},
            {"type_name": "主播诱惑", "type_id": "c4B4"},
            {"type_name": "乱伦侵犯", "type_id": "54B4"},
            {"type_name": "传媒剧情", "type_id": "H4B4"},
            {"type_name": "抖音快手", "type_id": "E4B4"},
            {"type_name": "伦理三级", "type_id": "84B4"},
            {"type_name": "动漫动画", "type_id": "R4B4"}
        ]
        result = {"class": classes}
        if filter:
            result["filters"] = {}
        return result

    def homeVideoContent(self):
        return {"list": []}

    def _build_cate_url(self, tid, page):
        if tid == "route_actor_hot":
            return "/actor/p%s.html?a=hot" % page
        elif tid == "route_role_10min":
            return "/role/p%s.html?a=10min" % page
        elif tid.startswith("route_"):
            return tid.replace("route_", "/")
        else:
            if page == 1:
                return "/fly/%s_p.html" % tid
            return "/fly/%s_p%s.html" % (tid, page)

    def categoryContent(self, tid, pg, filter, extend):
        del filter, extend
        slug = str(tid).strip("/")
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1

        target_path = self._build_cate_url(slug, page)
        res = self._fetch(target_path)
        html = res.get("text", "")

        vod_list = []
        pattern = r'(class="[^"]*resent-grid[^"]*"[\s\S]*?</h5>)'
        cards = re.findall(pattern, html, re.I)

        for card in cards:
            link_m = re.search(r'href=["\'](/js/[^"\']+\.html)["\']', card, re.I)
            if not link_m:
                continue
            v_url = link_m.group(1).strip()

            pic_m = re.search(r'(?:data-original|src)=["\']([^"\']+)["\']', card, re.I)
            pic = pic_m.group(1).strip() if pic_m else ""

            title = ""
            title_m = re.search(r'class="title"[^>]*>([\s\S]*?)</a>', card, re.I)
            if title_m:
                title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            if not title:
                title_alt = re.search(r'alt=["\']([^"\']+)["\']', card, re.I)
                if title_alt and title_alt.group(1).strip():
                    title = title_alt.group(1).strip()

            dur_m = re.search(r'class="duration-time"[^>]*>([\s\S]*?)</p>', card, re.I)
            duration = re.sub(r'<[^>]+>', '', dur_m.group(1)).strip() if dur_m else ""

            if v_url and pic:
                vod_list.append({
                    "vod_id": v_url,
                    "vod_name": title if title else "精彩视频",
                    "vod_pic": pic if pic.startswith("http") else (self.siteUrl + pic),
                    "vod_remarks": format_remarks("ZakaTV", duration),
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 12 else page,
            "limit": 20,
            "total": 999,
            "list": vod_list
        }

    def _resolve_real_stream(self, bf_page_url):
        res_p = self._fetch(bf_page_url)
        p_html = res_p.get("text", "")

        cfg_m = re.search(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\});', p_html)
        if not cfg_m:
            return ""

        raw_cfg_str = cfg_m.group(1).replace("\\/", "/")
        url_match = re.search(r'"url"\s*:\s*"([^"]+)"', raw_cfg_str)
        note_match = re.search(r'"note"\s*:\s*"([^"]*)"', raw_cfg_str)
        from_match = re.search(r'"from"\s*:\s*"([^"]*)"', raw_cfg_str)

        target_stream_url = url_match.group(1) if url_match else ""
        play_note = note_match.group(1) if note_match else ""
        play_from = from_match.group(1) if from_match else "ck91player"

        parse_endpoint = "/ck91.php" if "ck91" in play_from else "/ck.php"
        api_url = "%s?url=%s&key=%s" % (parse_endpoint, quote(target_stream_url), play_note)

        res_api = self._fetch(api_url, referer=self.siteUrl + bf_page_url)
        api_html = res_api.get("text", "")

        m3u8_matches = re.findall(r'(https?://[^\s"\'\$<>]+\.m3u8[^\s"\'\$<>]*)', api_html, re.I)
        if m3u8_matches:
            return m3u8_matches[0].replace("\\u002F", "/").replace("\\/", "")

        var_url_m = re.search(r'(?:var\s+plyerurl|var\s+url|video_url)\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']', api_html, re.I)
        if var_url_m:
            return var_url_m.group(1).replace("\\u002F", "/").replace("\\/", "")

        return ""

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        detail_url = raw_id if raw_id.startswith("http") else (self.siteUrl + raw_id)
        res_d = self._fetch(detail_url)
        d_html = res_d.get("text", "")

        title_m = re.search(r'<title>(.*?)</title>', d_html, re.I | re.S)
        raw_title = title_m.group(1).strip() if title_m else "Zaka专线高清视频"
        main_title = re.sub(r'_(?:影片介绍|疯猫av|免费在线播放).*$', '', raw_title).strip()

        play_links = re.findall(r'href=["\'](/bf/[^"\']+\.html)["\']', d_html, re.I)
        target_play_page = play_links[0] if play_links else detail_url
        main_play_target = self.siteUrl + target_play_page if target_play_page.startswith("/") else target_play_page

        episodes = ["正片$%s@@@%s" % (main_play_target, quote(main_title))]

        rec_blocks = re.findall(r'(class="[^"]*resent-grid[^"]*"[\s\S]*?</h5>)', d_html, re.I)
        seen_urls = set([raw_id, detail_url, target_play_page])
        rec_idx = 1

        for blk in rec_blocks:
            v_m = re.search(r'href=["\'](/js/[^"\']+\.html)["\']', blk, re.I)
            if not v_m:
                continue
            rec_href = v_m.group(1).strip()
            if rec_href in seen_urls:
                continue
            seen_urls.add(rec_href)

            t_m = re.search(r'class="title"[^>]*>([\s\S]*?)</a>', blk, re.I)
            rec_title = re.sub(r'<[^>]+>', '', t_m.group(1)).strip() if t_m else ""
            if not rec_title:
                alt_m = re.search(r'alt=["\']([^"\']+)["\']', blk, re.I)
                rec_title = alt_m.group(1).strip() if alt_m else ""

            if not rec_title:
                continue

            clean_t = clean_label(rec_title)
            display_t = (clean_t[:20] + "...") if len(clean_t) > 20 else clean_t

            rec_full_url = self.siteUrl + rec_href
            episodes.append("%02d·%s$%s@@@%s" % (rec_idx, display_t, rec_full_url, quote(rec_title)))
            rec_idx += 1
            if rec_idx > 30:
                break

        vod = {
            "vod_id": raw_id,
            "vod_name": main_title,
            "vod_pic": "",
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("ZakaTV", "全%s部连播" % len(episodes)),
            "vod_content": "📺ZakaTV专线直连 | %s | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl" % main_title,
            "vod_play_from": "Zaka专线",
            "vod_play_url": "#".join(episodes)
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw_val = str(id).strip()
        desc_title = ""
        if "@@@" in raw_val:
            target_page, raw_t = raw_val.split("@@@", 1)
            desc_title = unquote(raw_t)
        else:
            target_page = raw_val

        real_stream = ""
        actual_bf = target_page
        if "/js/" in target_page:
            res_d = self._fetch(target_page)
            d_html = res_d.get("text", "")
            bf_links = re.findall(r'href=["\'](/bf/[^"\']+\.html)["\']', d_html, re.I)
            if bf_links:
                actual_bf = self.siteUrl + bf_links[0] if bf_links[0].startswith("/") else bf_links[0]

        real_stream = self._resolve_real_stream(actual_bf)
        if not real_stream:
            real_stream = actual_bf

        is_stream = any(k in real_stream.lower() for k in (".m3u8", ".mp4", ".ts"))
        result = {
            "parse": 0 if is_stream else 1,
            "playUrl": "",
            "url": real_stream,
            "header": {
                "User-Agent": self._ua
            }
        }
        if desc_title:
            result["desc"] = desc_title
        return result

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1

        search_url = "/ss/key__p.html"
        post_data = {"wd": key}
        res = self._fetch(search_url, data=post_data, referer=self.siteUrl + "/")
        html = res.get("text", "")

        vod_list = []
        pattern = r'(class="[^"]*resent-grid[^"]*"[\s\S]*?</h5>)'
        cards = re.findall(pattern, html, re.I)

        for card in cards:
            link_m = re.search(r'href=["\'](/js/[^"\']+\.html)["\']', card, re.I)
            if not link_m:
                continue
            v_url = link_m.group(1).strip()

            pic_m = re.search(r'(?:data-original|src)=["\']([^"\']+)["\']', card, re.I)
            pic = pic_m.group(1).strip() if pic_m else ""

            title = ""
            title_m = re.search(r'class="title"[^>]*>([\s\S]*?)</a>', card, re.I)
            if title_m:
                title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            if not title:
                title_alt = re.search(r'alt=["\']([^"\']+)["\']', card, re.I)
                if title_alt and title_alt.group(1).strip():
                    title = title_alt.group(1).strip()

            dur_m = re.search(r'class="duration-time"[^>]*>([\s\S]*?)</p>', card, re.I)
            duration = re.sub(r'<[^>]+>', '', dur_m.group(1)).strip() if dur_m else ""

            if v_url and pic:
                vod_list.append({
                    "vod_id": v_url,
                    "vod_name": title if title else "精彩视频",
                    "vod_pic": pic if pic.startswith("http") else (self.siteUrl + pic),
                    "vod_remarks": format_remarks("ZakaTV", duration),
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 12 else page,
            "limit": 20,
            "total": 999,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}