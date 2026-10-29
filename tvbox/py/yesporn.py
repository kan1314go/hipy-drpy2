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

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.navUrls = ["https://x99dh.net", "https://x99dh.lat"]
        self.targetSiteName = "YesPorn"
        self.cacheKey = "nav_direct_yesporn_site_url"
        self.defaultHost = "https://cn.yesporn.ws"
        self.siteUrl = self.defaultHost
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

        self._refresh_site_url_from_nav()
        return True

    def getName(self):
        return "YesPorn·动态自愈版"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

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
                                        self.siteUrl = base_host
                                        self.setCache(self.cacheKey, base_host)
                                        return True
                except Exception:
                    continue

        cached_host = self.getCache(self.cacheKey)
        if cached_host and str(cached_host).startswith("http"):
            self.baseHost = str(cached_host).strip().rstrip("/")
            self.siteUrl = self.baseHost
            return True

        self.baseHost = self.defaultHost
        self.siteUrl = self.defaultHost
        return False

    def _fetch(self, target_url, referer="", check_host=True):
        if not target_url:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.baseHost + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.baseHost + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        last_err = ""
        domain_retried = False

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=15) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    raw = self._decompress(raw, enc)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (404, 451, 500, 502, 503) and check_host and not domain_retried:
                    old_host = urllib.parse.urlparse(self.baseHost).netloc
                    self.delCache(self.cacheKey)
                    if self._refresh_site_url_from_nav():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.baseHost).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if e.code in (451, 403, 429) and attempt == 0:
                    continue
                err_raw = ""
                try:
                    raw_err = e.read()
                    enc = getattr(e, "headers", {}).get("Content-Encoding", "")
                    err_raw = self._decompress(raw_err, enc).decode("utf-8", errors="ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": err_raw, "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if check_host and not domain_retried:
                    old_host = urllib.parse.urlparse(self.baseHost).netloc
                    self.delCache(self.cacheKey)
                    if self._refresh_site_url_from_nav():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.baseHost).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "err": last_err, "final_url": target_url}

    def homeContent(self, filter):
        result = {
            "class": [
                {"type_name": "🔥最新更新", "type_id": "/latest-updates/"},
                {"type_name": "⭐最高评分", "type_id": "/top-rated/"},
                {"type_name": "👀最受欢迎", "type_id": "/most-popular/"},
                {"type_name": "👑Reality Kings", "type_id": "/channels/realitykings-x0njpa/"},
                {"type_name": "🔞Bangbros", "type_id": "/channels/bangbros-x0njpa/"},
                {"type_name": "💎Pure Taboo", "type_id": "/channels/puretaboo-g7g6z5/"}
            ]
        }
        if filter:
            result["filters"] = {}
        return result

    def homeVideoContent(self):
        res = self.categoryContent("/latest-updates/", "1", False, {})
        return {"list": res.get("list", [])}

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        extend = extend if isinstance(extend, dict) else {}
        route = str(tid).strip()
        page_int = int(pg) if str(pg).isdigit() else 1

        clean_route = route.rstrip("/")
        if page_int > 1:
            req_url = "%s%s/%d/" % (self.baseHost, clean_route, page_int)
        else:
            req_url = "%s%s/" % (self.baseHost, clean_route)

        res = self._fetch(req_url)
        html_text = res.get("text", "")
        if not html_text:
            return {"page": page_int, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        blocks = html_text.split('class="thumb thumb_rel item')
        vod_list = []

        for blk in blocks[1:]:
            href_m = re.search(r'href=["\']([^"\']+/video/(\d+)/[^"\']*)["\']', blk, re.I)
            title_m = re.search(r'title=["\']([^"\']+)["\']', blk, re.I)
            img_m = re.search(r'(?:data-webp|data-original)=["\']([^"\']+)["\']', blk, re.I)
            duration_m = re.search(r'class=["\']item-time[^"\']*["\'][^>]*>([\s\S]*?)</div>', blk, re.I)

            if href_m and title_m:
                vod_url = href_m.group(1).strip()
                vid = href_m.group(2).strip()
                title = title_m.group(1).strip()
                pic = img_m.group(1).strip() if img_m else ""
                
                remarks = ""
                if duration_m:
                    remarks = re.sub(r'<[^>]+>', '', duration_m.group(1)).strip()

                v_identifier = "%s|%s" % (vod_url, vid)

                vod_list.append({
                    "vod_id": v_identifier,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                    "style": {"type": "rect", "ratio": 1.78}
                })

        page_count = page_int + 1 if len(vod_list) >= 20 else page_int
        if page_count < 1:
            page_count = 1

        return {
            "page": page_int,
            "pagecount": page_count,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_token = str(raw_id).strip()

        if "|" in target_token:
            parts = target_token.split("|")
            target_url = parts[0]
            vid = parts[1]
        else:
            target_url = target_token
            vid_m = re.search(r'/video/(\d+)/', target_url)
            vid = vid_m.group(1) if vid_m else ""

        res = self._fetch(target_url)
        html_text = res.get("text", "")
        if not html_text:
            return {"list": []}

        title_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html_text, re.I)
        vod_name = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ""
        if not vod_name:
            t_m = re.search(r'<title>(.*?)</title>', html_text, re.I)
            vod_name = t_m.group(1).split("-")[0].strip() if t_m else "精彩视频"

        pic_m = re.search(r'poster\s*:\s*[\'"]([^\'"]+)[\'"]', html_text, re.I)
        if not pic_m:
            pic_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html_text, re.I)
        vod_pic = pic_m.group(1).strip() if pic_m else ""

        intro_desc = (
            "【📺官方交流群: %s】\n"
            "【当前发布域名: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "温馨提示：若播放卡顿或加载较慢，请尝试切换代理节点。\n"
            "影片标题：%s"
        ) % (self.tgGroup, self.baseHost, vod_name)
        escaped_desc = intro_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        if vid:
            embed_play_url = "%s/embed/%s" % (self.baseHost, vid)
        else:
            embed_play_url = target_url

        play_str = "正片高清$%s" % embed_play_url

        return {
            "list": [{
                "vod_id": target_token,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": "HD高清",
                "vod_content": escaped_desc,
                "vod_play_from": "Zaka专线",
                "vod_play_url": play_str
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        headers = {
            "User-Agent": self._ua,
            "Referer": self.baseHost + "/",
            "Accept": "*/*"
        }
        return {
            "parse": 1,
            "jx": 0,
            "url": str(id).strip(),
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page_int = int(pg) if str(pg).isdigit() else 1
        encoded_key = urllib.parse.quote(key)
        
        if page_int > 1:
            search_url = "%s/search/%s/%d/" % (self.baseHost, encoded_key, page_int)
        else:
            search_url = "%s/search/%s/" % (self.baseHost, encoded_key)

        res = self._fetch(search_url)
        html_text = res.get("text", "")
        if not html_text:
            return {"page": page_int, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        blocks = html_text.split('class="thumb thumb_rel item')
        vod_list = []

        for blk in blocks[1:]:
            href_m = re.search(r'href=["\']([^"\']+/video/(\d+)/[^"\']*)["\']', blk, re.I)
            title_m = re.search(r'title=["\']([^"\']+)["\']', blk, re.I)
            img_m = re.search(r'(?:data-webp|data-original)=["\']([^"\']+)["\']', blk, re.I)
            duration_m = re.search(r'class=["\']item-time[^"\']*["\'][^>]*>([\s\S]*?)</div>', blk, re.I)

            if href_m and title_m:
                vod_url = href_m.group(1).strip()
                vid = href_m.group(2).strip()
                title = title_m.group(1).strip()
                pic = img_m.group(1).strip() if img_m else ""
                
                remarks = ""
                if duration_m:
                    remarks = re.sub(r'<[^>]+>', '', duration_m.group(1)).strip()

                v_identifier = "%s|%s" % (vod_url, vid)

                vod_list.append({
                    "vod_id": v_identifier,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return {
            "page": page_int,
            "pagecount": page_int + 1 if len(vod_list) >= 20 else page_int,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    def action(self, action):
        if action == "toast":
            return {"msg": "当前有效主站: %s" % self.baseHost}
        return {"msg": "YesPorn生产蜘蛛运行正常"}

    def liveContent(self):
        return ""
