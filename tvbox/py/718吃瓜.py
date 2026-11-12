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

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

def clean_title_text(raw_title):
    if not raw_title:
        return ""
    t = re.sub(r"<[^>]+>", "", raw_title)
    t = html_lib.unescape(t)
    t = re.sub(r"[\r\n\t]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    noise_tags = [
        r"热搜\s*HOT", r"HOT", r"置顶", r"独家", r"NEW",
        r"吃瓜\s*HOT", r"爆料\s*HOT", r"\|\s*吃瓜718"
    ]
    for tag in noise_tags:
        t = re.sub(r"\s*" + tag + r"\s*$", "", t, flags=re.I)
    return t.strip()

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://www.718yule.com"
        self.workerCdn = "https://718haibao.peiqi192192.workers.dev/img"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self.brandLine = "蝴蝶专线"
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
        return "718娱乐"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _fetch(self, target_url, referer=""):
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

        last_err = ""
        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
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

    def _resolve_pic(self, rel_pic):
        if not rel_pic:
            return ""
        clean_p = rel_pic.strip().strip("'\"")
        clean_p = re.sub(r"^https?://[^/]+/", "", clean_p).lstrip("/")
        return "%s/%s" % (self.workerCdn, clean_p)

    def homeContent(self, filter):
        classes = [
            {"type_name": "吃瓜首页", "type_id": "home_feed"},
            {"type_name": "每日吃瓜", "type_id": "daily-gossip"},
            {"type_name": "热门吃瓜", "type_id": "top-stories"},
            {"type_name": "反差婊曝光", "type_id": "contrast-reveal"},
            {"type_name": "吃瓜TOP榜", "type_id": "week-top"},
            {"type_name": "网黄合集", "type_id": "sexbook"},
            {"type_name": "AI成人短剧", "type_id": "AINSFW"},
            {"type_name": "抖音网红瓜", "type_id": "internet-celebrities"},
            {"type_name": "社会热瓜", "type_id": "trending-news"},
            {"type_name": "微密圈", "type_id": "model-photos"},
            {"type_name": "福利姬", "type_id": "fuli"},
            {"type_name": "娱乐吃瓜", "type_id": "celebrity-scandals"},
            {"type_name": "娱乐圈爆料", "type_id": "entertainment-news"}
        ]
        result = {"class": classes}
        if filter:
            result["filters"] = {}
        return result

    def homeVideoContent(self):
        res = self.categoryContent("home_feed", 1, False, {})
        return {"list": res.get("list", [])[:12]}

    def _extract_card_pic(self, block):
        m_bg = re.search(r'class=["\'][^"\']*blog-background[^"\']*["\'][^>]+data-pic=["\']([^"\']+)["\']', block, re.I)
        if not m_bg:
            m_bg = re.search(r'data-pic=["\']([^"\']+)["\']', block, re.I)
        if m_bg:
            cand = m_bg.group(1).strip()
            if "listzw" not in cand and "placeholder" not in cand:
                return cand

        m_meta = re.search(r'<meta[^>]+itemprop=["\']image["\'][^>]+content=["\']([^"\']+)["\']', block, re.I)
        if m_meta:
            cand = m_meta.group(1).strip()
            if "listzw" not in cand and "placeholder" not in cand:
                return cand

        m_any = re.search(r'["\'](/(?:5202|718yule|upload)/[^"\']+\.(?:webp|jpg|png|jpeg)[^"\']*)["\']', block, re.I)
        if m_any:
            cand = m_any.group(1).strip()
            if "listzw" not in cand and "placeholder" not in cand:
                return cand

        return ""

    def _parse_card_list(self, html_text):
        vod_list = []
        seen_ids = set()

        ad_id_blacklist = {"14", "22245", "22877", "22747", "20261"}
        strict_ad_keywords = ("约炮", "成人直播", "欲女的高潮", "欲女", "交友", "同城", "兼职", "商务合作", "重金求稿", "变现", "高价收购", "吃瓜导航")

        clean_html = re.sub(r'<aside[\s\S]*?</aside>', '', html_text)
        clean_html = re.sub(r'<div[^>]+class=["\'][^"\']*(?:widget|sidebar)[^"\']*["\'][\s\S]*?</div>', '', clean_html)

        articles = re.findall(r'<article[^>]*>([\s\S]*?)</article>', clean_html)
        if not articles:
            articles = re.findall(r'(<div[^>]+class=["\'][^"\']*post-card[^"\']*["\'][^>]*>[\s\S]*?</div>\s*</div>)', clean_html)

        for block in articles:
            if "rel=\"sponsored nofollow\"" in block or "itemprop=\"sponsor\"" in block or "_czc.push" in block:
                continue

            if "sticky" in block or "post-sticky" in block:
                continue

            id_m = re.search(r'/archives/(\d+)/?', block)
            if not id_m:
                continue

            aid = id_m.group(1).strip()
            if aid in seen_ids or aid in ad_id_blacklist:
                continue

            m_t = re.search(r'<h[234][^>]*class=["\'][^"\']*post-card-title[^"\']*["\'][^>]*>([\s\S]*?)</h[234]>', block)
            if not m_t:
                m_t = re.search(r'<h[234][^>]*>([\s\S]*?)</h[234]>', block)

            raw_extracted_title = ""
            if m_t:
                raw_extracted_title = m_t.group(1)
                raw_extracted_title = re.split(r'<div|<span|<p', raw_extracted_title)[0]

            if any(k in raw_extracted_title for k in ("HOT", "热搜", "置顶", "广告", "推广")):
                continue

            name = clean_title_text(raw_extracted_title) if raw_extracted_title else ""
            if not name:
                raw_txt = re.sub(r'<[^>]+>', ' ', block).strip()
                name = clean_title_text(raw_txt[:60]) if raw_txt else ("热点爆料 %s" % aid)

            if not name or any(k in name for k in strict_ad_keywords):
                continue

            seen_ids.add(aid)

            post_date = ""
            m_dt_attr = re.search(r'itemprop=["\']dateModified["\'][^>]+content=["\'](\d{4}-\d{2}-\d{2})', block)
            if not m_dt_attr:
                m_dt_attr = re.search(r'itemprop=["\']datePublished["\'][^>]+content=["\'](\d{4}-\d{2}-\d{2})', block)

            if m_dt_attr:
                post_date = m_dt_attr.group(1).strip()
            else:
                m_dash_dt = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', block)
                if m_dash_dt:
                    post_date = m_dash_dt.group(1).strip()

            pic = self._extract_card_pic(block)
            resolved_pic = self._resolve_pic(pic) if pic else ""

            remark_text = post_date if post_date else "现场实录"

            vod_list.append({
                "vod_id": aid,
                "vod_name": name,
                "vod_pic": resolved_pic,
                "vod_remarks": format_remarks("蝴蝶影视", remark_text),
                "style": {"type": "rect", "ratio": 1.78}
            })

        return vod_list

    def categoryContent(self, tid, pg, filter, extend):
        del filter, extend
        page = 1
        try:
            page = int(pg)
        except Exception:
            page = 1

        slug = str(tid).strip("/")

        target_urls = []
        if slug in ("home_feed", "index", "", "home"):
            if page > 1:
                target_urls.append("%s/page/%d/" % (self.siteUrl, page))
                target_urls.append("%s/index.php/page/%d/" % (self.siteUrl, page))
                target_urls.append("%s/?page=%d" % (self.siteUrl, page))
            else:
                target_urls.append(self.siteUrl + "/")
                target_urls.append(self.siteUrl)
        else:
            if page > 1:
                target_urls.append("%s/category/%s/%d/" % (self.siteUrl, slug, page))
                target_urls.append("%s/category/%s/?page=%d" % (self.siteUrl, slug, page))
            else:
                target_urls.append("%s/category/%s/" % (self.siteUrl, slug))
                target_urls.append("%s/category/%s" % (self.siteUrl, slug))

        vod_list = []
        for u in target_urls:
            res = self._fetch(u)
            if res.get("code") == 200:
                vod_list = self._parse_card_list(res.get("text", ""))
                if vod_list:
                    break

        pagecount = page + 1 if len(vod_list) >= 10 else page
        if pagecount <= 0:
            pagecount = 1

        return {
            "page": page,
            "pagecount": pagecount,
            "limit": len(vod_list),
            "total": int(page * len(vod_list) + 100) if len(vod_list) >= 10 else len(vod_list),
            "list": vod_list
        }

    def _clean_stream_url(self, raw_url):
        if not raw_url:
            return ""
        clean = raw_url.replace(r"\u0068ttps", "https").replace(r"\u0068ttp", "http")
        clean = clean.replace(r"\/", "/").strip()
        clean = clean.replace(r"\u0026", "&")
        clean = clean.replace("&quot;", "").replace('"', '').replace("'", "")
        clean = re.sub(r'[\s\]\}]+$', '', clean)
        if clean.startswith("//"):
            clean = "https:" + clean
        return clean

    def _extract_episodes_from_html(self, html_content, default_name_prefix="片段"):
        episodes_https = []
        episodes_http = []
        seen_urls = set()

        video_list = []

        dp_configs = re.findall(r'data-config=(["\'])([\s\S]*?)\1', html_content)
        for quote_char, raw_cfg in dp_configs:
            raw_cfg = html_lib.unescape(raw_cfg)
            u_m2 = re.search(r'["\']url2["\']\s*:\s*["\']([^"\']+)["\']', raw_cfg)
            if u_m2:
                video_list.append(u_m2.group(1))
            u_m = re.search(r'["\']url["\']\s*:\s*["\']([^"\']+)["\']', raw_cfg)
            if u_m and u_m.group(1) != "null":
                video_list.append(u_m.group(1))

        if not video_list:
            m_container = re.search(r'id=["\']article-videos["\'][^>]+data-url=(["\'])([\s\S]*?)\1', html_content, re.I)
            if not m_container:
                m_container = re.search(r'data-url=(["\'])([\s\S]*?)\1', html_content, re.I)

            if m_container:
                raw_val = html_lib.unescape(m_container.group(2)).strip()
                if raw_val.startswith("["):
                    try:
                        video_list = json.loads(raw_val)
                    except Exception:
                        video_list = re.findall(r'https?://[^\s"\'<>]+', raw_val)
                else:
                    if raw_val:
                        video_list = [raw_val]

        if not video_list:
            video_matches = re.findall(r'<video[^>]+>', html_content)
            for v_tag in video_matches:
                m_src = re.search(r'(?:data-hls-src|data-src|src)=["\']([^"\']+)["\']', v_tag)
                if m_src:
                    video_list.append(m_src.group(1))

        if not video_list:
            stream_matches = re.findall(r'["\'](https?:[\\/]+[^"\'\s]+\.(?:m3u8|mp4)[^"\'\s]*)["\']', html_content)
            for raw_stream in stream_matches:
                video_list.append(raw_stream)

        for v in video_list:
            v_clean = self._clean_stream_url(str(v))
            if v_clean and v_clean not in seen_urls and "logo" not in v_clean:
                seen_urls.add(v_clean)
                ep_name = "%s %02d" % (default_name_prefix, len(episodes_https) + 1)
                episodes_https.append("%s$%s" % (ep_name, v_clean))
                episodes_http.append("%s$%s" % (ep_name, v_clean.replace("https://", "http://")))

        return episodes_https, episodes_http

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        aid = raw_id.strip("/")

        target_url = "%s/archives/%s/" % (self.siteUrl, aid)
        res = self._fetch(target_url)
        detail_html = res.get("text", "")

        title = "热点爆料 %s" % aid
        cover = ""
        desc = ""

        m_title = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', detail_html)
        if m_title:
            title = clean_title_text(m_title.group(1))

        m_desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', detail_html)
        if not m_desc:
            m_desc = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)["\']', detail_html)
        if m_desc:
            desc = m_desc.group(1).strip()

        for m in re.finditer(r'["\'](/(?:5202|718yule|upload)/[^"\']+\.(?:webp|jpg|png|jpeg)[^"\']*)["\']', detail_html, re.I):
            cand = m.group(1).strip()
            if "listzw" not in cand and "placeholder" not in cand:
                cover = cand
                break

        if not cover:
            for attr in ("data-pic", "data-src", "data-original", "content"):
                for m in re.finditer(r'%s=["\']([^"\']+\.(?:webp|jpg|png|jpeg)[^"\']*)["\']' % attr, detail_html, re.I):
                    cand = m.group(1).strip()
                    if "listzw" not in cand and "placeholder" not in cand:
                        cover = cand
                        break
                if cover:
                    break

        resolved_cover = self._resolve_pic(cover) if cover else ""

        eps_https, eps_http = self._extract_episodes_from_html(detail_html, default_name_prefix="正片")

        if not eps_https:
            content_m = re.search(r'<div[^>]+class=["\'][^"\']*(?:post-content|content)[^"\']*["\'][^>]*>([\s\S]*?)(?:<div[^>]+class=["\'][^"\']*(?:post-footer|post-tags|comments)[^"\']*["\']|</article>)', detail_html)
            post_body = content_m.group(1) if content_m else detail_html

            sub_article_links = re.findall(r'<a[^>]+href=["\'](?:https?://[^/]+)?/archives/(\d+)/?["\'][^>]*>([\s\S]*?)</a>', post_body)
            seen_sub_ids = set()

            for sub_id, link_inner in sub_article_links:
                if sub_id == aid or sub_id in seen_sub_ids or sub_id in {"14", "22245", "22877", "22747", "20261"}:
                    continue
                seen_sub_ids.add(sub_id)

                sub_t = re.sub(r'<[^>]+>', '', link_inner).strip()
                sub_label = re.sub(r'[\$#\r\n\t]', '', sub_t)[:22].strip() if sub_t else ("TOP %02d" % len(seen_sub_ids))

                sub_url = "%s/archives/%s/" % (self.siteUrl, sub_id)
                sub_res = self._fetch(sub_url)
                sub_html = sub_res.get("text", "")

                sub_eps_https, sub_eps_http = self._extract_episodes_from_html(sub_html, default_name_prefix=sub_label)
                for s_ep in sub_eps_https:
                    parts = s_ep.split("$")
                    if len(parts) == 2:
                        ep_name = sub_label if len(sub_eps_https) == 1 else ("%s·%s" % (sub_label, parts[0]))
                        eps_https.append("%s$%s" % (ep_name, parts[1]))
                    else:
                        eps_https.append(s_ep)

                for s_ep in sub_eps_http:
                    parts = s_ep.split("$")
                    if len(parts) == 2:
                        ep_name = sub_label if len(sub_eps_http) == 1 else ("%s·%s" % (sub_label, parts[0]))
                        eps_http.append("%s$%s" % (ep_name, parts[1]))
                    else:
                        eps_http.append(s_ep)

                if len(seen_sub_ids) >= 12:
                    break

        full_desc = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🦋 蝴蝶影视专线直连 | 解析到【%d】个媒体切片 | %s"
        ) % (self.tgGroup, len(eps_https), desc)

        play_from_list = ["蝴蝶专线", "备用直链"]
        play_url_list = [
            "#".join(eps_https) if eps_https else "暂无可用视频流$http://127.0.0.1",
            "#".join(eps_http) if eps_http else "暂无可用视频流$http://127.0.0.1"
        ]

        return {
            "list": [{
                "vod_id": aid,
                "vod_name": title,
                "vod_pic": resolved_cover,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": format_remarks("蝴蝶影视", "共%d个片段" % len(eps_https) if len(eps_https) > 1 else "现场实录"),
                "vod_content": full_desc,
                "vod_play_from": "$$$".join(play_from_list),
                "vod_play_url": "$$$".join(play_url_list)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        raw_url = str(id).strip()
        return {
            "parse": 0,
            "playUrl": "",
            "url": raw_url,
            "header": {
                "User-Agent": self._ua,
                "Referer": self.siteUrl + "/"
            }
        }

    def searchContent(self, key, quick, pg="1"):
        del quick
        page = 1
        try:
            page = int(pg)
        except Exception:
            page = 1

        search_url = "%s/search/%s/" % (self.siteUrl, quote(key))
        if page > 1:
            search_url = "%s/search/%s/%d/" % (self.siteUrl, quote(key), page)

        res = self._fetch(search_url)
        vod_list = self._parse_card_list(res.get("text", ""))

        pagecount = page + 1 if len(vod_list) >= 10 else page
        if pagecount <= 0:
            pagecount = 1

        return {
            "page": page,
            "pagecount": pagecount,
            "limit": len(vod_list),
            "total": int(page * len(vod_list) + 100) if len(vod_list) >= 10 else len(vod_list),
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]