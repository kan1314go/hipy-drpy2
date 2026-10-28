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
        self.targetSiteName = "好色TV"
        self.cacheKey = "haose_live_host"
        self.navUrls = ["https://x99dh.net", "https://x99dh.lat"]
        self.defaultHost = "https://pb365.top"
        self.siteUrl = self.defaultHost
        self.entryPath = "/enter"
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
        return "好色TV·动态发布自愈版"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".mpd"))

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
                    if "[" in unq and "{" in unq and (self.targetSiteName in unq or "好色" in unq):
                        site_list = json.loads(unq)
                        if isinstance(site_list, list):
                            for item in site_list:
                                item_name = str(item.get("name", "")).strip()
                                if item_name == self.targetSiteName or "好色" in item_name:
                                    direct_target_url = item.get("url", "").strip()
                                    if direct_target_url:
                                        parsed = urllib.parse.urlparse(direct_target_url)
                                        base_host = "%s://%s" % (parsed.scheme, parsed.netloc)
                                        self.siteUrl = base_host
                                        self.setCache(self.cacheKey, base_host)
                                        return True
                except Exception:
                    continue

        cached_host = self.getCache(self.cacheKey)
        if cached_host and str(cached_host).startswith("http"):
            self.siteUrl = str(cached_host).strip().rstrip("/")
            return True

        self.siteUrl = self.defaultHost
        return False

    def _fetch(self, target_url, referer="", check_host=True):
        if not target_url:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + self.entryPath),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        last_err = ""
        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=10) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    decomp = self._decompress(raw, enc)
                    try:
                        text = decomp.decode("utf-8")
                    except Exception:
                        text = decomp.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (404, 451, 500, 502, 503) and check_host and attempt == 0:
                    old_host = urllib.parse.urlparse(self.siteUrl).netloc
                    self.delCache(self.cacheKey)
                    if self._refresh_site_url_from_nav():
                        new_host = urllib.parse.urlparse(self.siteUrl).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if e.code in (451, 403, 429) and attempt == 0:
                    continue
                err_raw = ""
                try:
                    err_decomp = self._decompress(e.read(), getattr(e, "headers", {}).get("Content-Encoding", ""))
                    err_raw = err_decomp.decode("utf-8", errors="ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": err_raw, "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if check_host and attempt == 0:
                    old_host = urllib.parse.urlparse(self.siteUrl).netloc
                    self.delCache(self.cacheKey)
                    if self._refresh_site_url_from_nav():
                        new_host = urllib.parse.urlparse(self.siteUrl).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "err": last_err, "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_id": "list", "type_name": "最新"},
            {"type_id": "top7_list", "type_name": "周榜"},
            {"type_id": "top_list", "type_name": "月榜"},
            {"type_id": "5min_list", "type_name": "5分钟"},
            {"type_id": "long_list", "type_name": "10分钟"}
        ]

        sort_filter = {
            "key": "sort",
            "name": "排序",
            "value": [
                {"n": "全部/默认", "v": ""},
                {"n": "最新", "v": "new"},
                {"n": "最热", "v": "hot"}
            ]
        }

        filters = {}
        for c in classes:
            filters[c["type_id"]] = [sort_filter]

        return {
            "class": classes,
            "filters": filters
        }

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg and str(pg).isdigit() else 1
        sort_val = ""
        if extend and isinstance(extend, dict):
            sort_val = extend.get("sort", "")

        if sort_val:
            req_path = "/%s-%d.htm?sort=%s" % (tid, page, sort_val)
        else:
            req_path = "/%s-%d.htm" % (tid, page)

        res = self._fetch(req_path)
        html_text = res.get("text", "")

        vod_list = []
        card_blocks = re.findall(r'<div[^>]*class=["\'][^"\']*col-(?:xs|md)-\d+[^"\']*["\'][^>]*>([\s\S]*?</div>\s*</div>\s*</div>)', html_text, re.I)

        seen_ids = set()
        for inner_html in card_blocks:
            m_href = re.search(r'href=["\'](?:https?://[^/]+)?(/video-\d+\.htm|video-\d+\.htm)["\']', inner_html, re.I)
            if not m_href:
                continue
            href = m_href.group(1)
            if not href.startswith("/"):
                href = "/" + href

            v_id_match = re.search(r'video-(\d+)\.htm', href)
            vod_id = v_id_match.group(1) if v_id_match else href
            if vod_id in seen_ids:
                continue
            seen_ids.add(vod_id)

            t_match = re.search(r'title=["\']([^"\']+)["\']', inner_html, re.I)
            if not t_match:
                t_match = re.search(r'<div[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>[\s\S]*?<a[^>]*>(.*?)</a>', inner_html, re.I)

            raw_title = ""
            if t_match:
                raw_title = t_match.group(1)
                raw_title = re.sub(r'<[^>]+>', '', raw_title).strip()
                raw_title = html_lib.unescape(raw_title)

            img_match = re.search(r'background-image:\s*url\(["\']?([^"\'\)]+)["\']?\)', inner_html, re.I)
            if not img_match:
                img_match = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+)["\']', inner_html, re.I)

            vod_pic = img_match.group(1).strip() if img_match else ""
            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic
            elif vod_pic.startswith("/"):
                vod_pic = self.siteUrl + vod_pic

            duration_match = re.search(r'<var[^>]*class=["\'][^"\']*duration[^"\']*["\'][^>]*>(.*?)</var>', inner_html, re.I | re.S)
            raw_duration = re.sub(r'<[^>]+>', '', duration_match.group(1)).strip() if duration_match else ""

            vod_remarks = ("📺ZakaTV | %s" % raw_duration) if raw_duration else "📺ZakaTV"

            if raw_title:
                vod_list.append({
                    "vod_id": href,
                    "vod_name": raw_title,
                    "vod_pic": vod_pic,
                    "vod_remarks": vod_remarks
                })

        page_count = page
        max_page_matches = re.findall(r'%s-(\d+)\.htm' % tid, html_text)
        if max_page_matches:
            found_pages = [int(p) for p in max_page_matches]
            page_count = max(max(found_pages), page + 1)
        elif len(vod_list) >= 12:
            page_count = page + 1

        return {
            "page": page,
            "pagecount": page_count,
            "limit": len(vod_list) if vod_list else 20,
            "total": page_count * 20,
            "list": vod_list
        }

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else str(ids)
        target_path = vod_id.strip() if vod_id.startswith("/") else ("/video-%s.htm" % vod_id)

        res = self._fetch(target_path)
        html_text = res.get("text", "")

        title_m = re.search(r'<title>(.*?)</title>', html_text, re.I | re.S)
        vod_name = html_lib.unescape(title_m.group(1).split("-")[0].strip()) if title_m else "正片"

        pic_m = re.search(r'poster=["\']([^"\']+)["\']', html_text, re.I)
        if not pic_m:
            pic_m = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html_text, re.I)
        vod_pic = pic_m.group(1).strip() if pic_m else ""
        if vod_pic.startswith("//"):
            vod_pic = "https:" + vod_pic
        elif vod_pic.startswith("/"):
            vod_pic = self.siteUrl + vod_pic

        desc_m = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html_text, re.I)
        raw_desc = html_lib.unescape(desc_m.group(1).strip()) if desc_m else ""

        full_desc = (
            "【🔥 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl】\n"
            "【当前发布域名: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.siteUrl, raw_desc if raw_desc else "好色TV 精选自拍原画。")

        return {
            "list": [
                {
                    "vod_id": str(vod_id),
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "type_name": "成人视频",
                    "vod_year": "2026",
                    "vod_area": "国产",
                    "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                    "vod_director": "📺ZakaTV",
                    "vod_content": full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                    "vod_play_from": "📺ZakaTV",
                    "vod_play_url": "正片$%s" % target_path
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags):
        target_path = str(id).strip()
        res = self._fetch(target_path)
        html_text = res.get("text", "")

        play_stream_url = ""
        header = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }

        m_vurl = re.search(r'[?&]video_url=([^&"\'\s]+)', html_text, re.I)
        if m_vurl:
            play_stream_url = urllib.parse.unquote(m_vurl.group(1))

        if not play_stream_url:
            all_m3u8 = re.findall(r'["\'](https?:[^"\']+\.m3u8[^"\']*)["\']', html_text, re.I)
            for u in all_m3u8:
                if "video_url=" in u:
                    sub_m = re.search(r'[?&]video_url=([^&"\'\s]+)', u)
                    if sub_m:
                        play_stream_url = urllib.parse.unquote(sub_m.group(1))
                        break
                elif "/jmpres/" in u:
                    play_stream_url = u
                    break
            if not play_stream_url and all_m3u8:
                play_stream_url = all_m3u8[0]

        return {
            "parse": 0,
            "playUrl": "",
            "url": play_stream_url,
            "header": header
        }

    def searchContent(self, key, quick, pg="1"):
        if not key:
            return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        page = int(pg) if pg and str(pg).isdigit() else 1
        encoded_key = urllib.parse.quote(str(key).strip())
        req_path = "/search.htm?keyword=%s&page=%d" % (encoded_key, page)

        vod_list = []
        try:
            res = self._fetch(req_path)
            html_text = res.get("text", "")
            card_blocks = re.findall(r'<div[^>]*class=["\'][^"\']*col-(?:xs|md)-\d+[^"\']*["\'][^>]*>([\s\S]*?</div>\s*</div>\s*</div>)', html_text, re.I)

            seen_ids = set()
            for inner_html in card_blocks:
                m_href = re.search(r'href=["\'](?:https?://[^/]+)?(/video-\d+\.htm|video-\d+\.htm)["\']', inner_html, re.I)
                if not m_href:
                    continue
                href = m_href.group(1)
                if not href.startswith("/"):
                    href = "/" + href

                v_id_match = re.search(r'video-(\d+)\.htm', href)
                vod_id = v_id_match.group(1) if v_id_match else href
                if vod_id in seen_ids:
                    continue
                seen_ids.add(vod_id)

                t_match = re.search(r'title=["\']([^"\']+)["\']', inner_html, re.I)
                if not t_match:
                    t_match = re.search(r'<div[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>[\s\S]*?<a[^>]*>(.*?)</a>', inner_html, re.I)

                raw_title = ""
                if t_match:
                    raw_title = t_match.group(1)
                    raw_title = re.sub(r'<[^>]+>', '', raw_title).strip()
                    raw_title = html_lib.unescape(raw_title)

                img_match = re.search(r'background-image:\s*url\(["\']?([^"\'\)]+)["\']?\)', inner_html, re.I)
                if not img_match:
                    img_match = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+)["\']', inner_html, re.I)

                vod_pic = img_match.group(1).strip() if img_match else ""
                if vod_pic.startswith("//"):
                    vod_pic = "https:" + vod_pic
                elif vod_pic.startswith("/"):
                    vod_pic = self.siteUrl + vod_pic

                duration_match = re.search(r'<var[^>]*class=["\'][^"\']*duration[^"\']*["\'][^>]*>(.*?)</var>', inner_html, re.I | re.S)
                raw_duration = re.sub(r'<[^>]+>', '', duration_match.group(1)).strip() if duration_match else ""

                vod_remarks = ("📺ZakaTV | %s" % raw_duration) if raw_duration else "📺ZakaTV"

                if raw_title:
                    vod_list.append({
                        "vod_id": href,
                        "vod_name": raw_title,
                        "vod_pic": vod_pic,
                        "vod_remarks": vod_remarks
                    })
        except Exception:
            vod_list = []

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 12 else page,
            "limit": len(vod_list) if vod_list else 20,
            "total": 100,
            "list": vod_list
        }

    def action(self, action):
        if action == "toast":
            return {"msg": "当前有效发布域: %s" % self.siteUrl}
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}
