#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
import json
import base64
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote
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

def clean_label(text):
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", "", str(text))
    t = re.sub(r"[\r\n\t]+", " ", t)
    t = t.replace("$", "").replace("#", "")
    return t.strip()

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = clean_label(meta)
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteName = "B里B里"
        self.siteUrl = "https://bli.nbpss.cfd"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}
        self._session_warmed = False

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
        try:
            self._warmup_session()
        except Exception:
            pass
        return True

    def _warmup_session(self):
        if self._session_warmed:
            return
        res = self._fetch(self.siteUrl + "/", timeout=4)
        if res.get("code") == 200:
            self._session_warmed = True

    def getName(self):
        return self.siteName

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "top_banner", "native-ad")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".ts", "index.png"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _fetch(self, target_url, referer="", timeout=8):
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

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=timeout) as resp:
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
                    return {"code": resp.getcode(), "text": text, "bytes": raw, "err": "", "final_url": resp.geturl()}
            except Exception as e:
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": "timeout", "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_id": "1", "type_name": "国产视频"},
            {"type_id": "2", "type_name": "传媒精品"},
            {"type_id": "3", "type_name": "特殊嗜好"},
            {"type_id": "4", "type_name": "三级伦理"},
            {"type_id": "41", "type_name": "女优精选"}
        ]
        filters = {
            "1": [
                {
                    "key": "sub",
                    "name": "分类",
                    "init": "1",
                    "value": [
                        {"n": "全部", "v": "1"},
                        {"n": "国产自拍", "v": "6"},
                        {"n": "国产偷拍", "v": "7"},
                        {"n": "国产探花", "v": "8"},
                        {"n": "国产主播", "v": "9"},
                        {"n": "国产户外", "v": "10"},
                        {"n": "黑料吃瓜", "v": "11"},
                        {"n": "国产伦理", "v": "12"},
                        {"n": "黑料视频", "v": "20"}
                    ]
                }
            ],
            "2": [
                {
                    "key": "sub",
                    "name": "分类",
                    "init": "2",
                    "value": [
                        {"n": "全部", "v": "2"},
                        {"n": "精东影业", "v": "13"},
                        {"n": "蜜桃传媒", "v": "14"},
                        {"n": "果冻传媒", "v": "15"},
                        {"n": "天美传媒", "v": "16"},
                        {"n": "星空传媒", "v": "21"},
                        {"n": "大象传媒", "v": "22"},
                        {"n": "香蕉传媒", "v": "23"},
                        {"n": "爱神传媒", "v": "24"}
                    ]
                }
            ],
            "3": [
                {
                    "key": "sub",
                    "name": "分类",
                    "init": "3",
                    "value": [
                        {"n": "全部", "v": "3"},
                        {"n": "绿帽换妻", "v": "25"},
                        {"n": "SM调教", "v": "26"},
                        {"n": "男同系列", "v": "27"},
                        {"n": "女同系列", "v": "28"},
                        {"n": "乱伦系列", "v": "29"},
                        {"n": "特殊嗜好", "v": "30"},
                        {"n": "网黄自制", "v": "31"},
                        {"n": "欧美AV", "v": "32"}
                    ]
                }
            ],
            "4": [
                {
                    "key": "sub",
                    "name": "分类",
                    "init": "4",
                    "value": [
                        {"n": "全部", "v": "4"},
                        {"n": "国产伦理", "v": "33"},
                        {"n": "香港伦理", "v": "34"},
                        {"n": "台湾伦理", "v": "35"},
                        {"n": "韩国伦理", "v": "36"},
                        {"n": "日本伦理", "v": "37"},
                        {"n": "西方伦理", "v": "38"},
                        {"n": "成人动漫", "v": "39"},
                        {"n": "糖心Vlog", "v": "40"}
                    ]
                }
            ],
            "41": [
                {
                    "key": "sub",
                    "name": "分类",
                    "init": "41",
                    "value": [
                        {"n": "全部", "v": "41"},
                        {"n": "日本无码", "v": "42"},
                        {"n": "日本有码", "v": "43"},
                        {"n": "中字无码", "v": "44"},
                        {"n": "中字有码", "v": "45"},
                        {"n": "红斯灯影像", "v": "46"},
                        {"n": "冉冉学姐", "v": "48"},
                        {"n": "小水水", "v": "47"},
                        {"n": "柚子猫", "v": "49"}
                    ]
                }
            ]
        }
        result = {"class": classes}
        if filter:
            result["filters"] = filters
        return result

    def homeVideoContent(self):
        return {"list": []}

    def _extract_card_title(self, block_text):
        m = re.search(r'class=["\'][^"\']*(?:title|name|heading)[^"\']*["\'][^>]*>([\s\S]*?)<', block_text, re.I)
        if m:
            t = clean_label(m.group(1))
            if t and not t.isdigit() and len(t) > 1:
                return t
        m = re.search(r'<h[23456][^>]*>([\s\S]*?)</h[23456]>', block_text, re.I)
        if m:
            t = clean_label(m.group(1))
            if t and not t.isdigit() and len(t) > 1:
                return t
        m = re.search(r'title=["\']([^"\']+)["\']', block_text, re.I)
        if m:
            t = clean_label(m.group(1))
            if t and not t.isdigit() and len(t) > 1:
                return t
        m = re.search(r'alt=["\']([^"\']+)["\']', block_text, re.I)
        if m:
            t = clean_label(m.group(1))
            if t and not t.isdigit() and len(t) > 1:
                return t
        return ""

    def _is_invalid_card(self, v_name, v_pic):
        low_n = (v_name or "").lower()
        low_p = (v_pic or "").lower()
        if any(bad in low_n for bad in ("广告", "导航", "备忘录", "下载app", "防走丢", "神秘入口", "加群", "交流群", "看b里b里")):
            return True
        if any(bad in low_p for bad in ("tg.png", "banner", "notice", "ad.jpg", "app.png", "logo")):
            return True
        return False

    def _parse_cards_from_html(self, html):
        cards = []
        seen_ids = set()

        blocks = re.split(r'(?=<li[^>]+class=|<div[^>]+class=["\'][^"\']*(?:item|col-|vodlist_item|card|swiper-slide)[^"\']*)', html)
        for b in blocks:
            id_m = re.search(r'/index\.php/vod/detail/id/(\d+)\.html', b)
            if not id_m:
                continue
            v_id = id_m.group(1).strip()
            if v_id in seen_ids:
                continue

            v_name = self._extract_card_title(b)
            if not v_name:
                v_name = "在线视频·%s" % v_id

            pic_m = re.search(r'(?:data-original|data-src|src)=["\']([^"\']*(?:upload|\.jpg|\.png|\.jpeg|\.webp)[^"\']*)["\']', b, re.I)
            if not pic_m:
                pic_m = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+)["\']', b, re.I)
            v_pic = pic_m.group(1).strip() if pic_m else ""
            if v_pic.startswith("//"):
                v_pic = "https:" + v_pic
            elif v_pic.startswith("/"):
                v_pic = self.siteUrl + v_pic

            if self._is_invalid_card(v_name, v_pic):
                continue

            remarks_m = re.search(r'class=["\'][^"\']*(?:pic-text|remarks|note|duration|text-right|tag)[^"\']*["\'][^>]*>([^<]+)<', b, re.I)
            v_remarks = remarks_m.group(1).strip() if remarks_m else ""

            seen_ids.add(v_id)
            cards.append({
                "vod_id": v_id,
                "vod_name": v_name,
                "vod_pic": v_pic,
                "vod_remarks": format_remarks(self.brandDirector.replace("🦋 ", ""), v_remarks),
                "style": {"type": "rect", "ratio": 1.78}
            })

        if not cards:
            for m in re.finditer(r'<a[^>]+href=["\'](?:/index\.php)?/vod/detail/id/(\d+)\.html["\'][^>]*>([\s\S]*?)</a>', html, re.I):
                v_id = m.group(1).strip()
                if v_id in seen_ids:
                    continue

                full_a = m.group(0)
                inner = m.group(2)
                v_name = self._extract_card_title(full_a) or self._extract_card_title(inner) or clean_label(inner)
                if not v_name:
                    v_name = "在线视频·%s" % v_id

                p_m = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+)["\']', inner, re.I)
                v_pic = p_m.group(1).strip() if p_m else ""
                if v_pic.startswith("//"):
                    v_pic = "https:" + v_pic
                elif v_pic.startswith("/"):
                    v_pic = self.siteUrl + v_pic

                if self._is_invalid_card(v_name, v_pic):
                    continue

                seen_ids.add(v_id)
                cards.append({
                    "vod_id": v_id,
                    "vod_name": v_name,
                    "vod_pic": v_pic,
                    "vod_remarks": format_remarks(self.brandDirector.replace("🦋 ", ""), ""),
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return cards

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        page = 1
        try:
            page = int(pg)
        except Exception:
            page = 1

        target_id = str(tid).strip("/")
        if isinstance(extend, dict) and extend.get("sub"):
            target_id = str(extend.get("sub")).strip("/")

        if page <= 1:
            req_url = "%s/index.php/vod/type/id/%s.html" % (self.siteUrl, target_id)
        else:
            req_url = "%s/index.php/vod/type/id/%s/page/%s.html" % (self.siteUrl, target_id, page)

        res = self._fetch(req_url)
        html = res.get("text", "")
        cards = self._parse_cards_from_html(html)

        if not cards:
            self._warmup_session()
            res_retry = self._fetch(req_url)
            cards = self._parse_cards_from_html(res_retry.get("text", ""))

        if page == 1 and len(cards) > 1:
            cards = cards[1:]

        has_next = len(cards) >= 10
        total_count = int(page * len(cards) + 100) if has_next else int(page * len(cards))
        page_count = int(page + 1) if has_next else int(page)

        return {
            "list": cards,
            "page": int(page),
            "pagecount": page_count,
            "limit": len(cards) if cards else 20,
            "total": total_count
        }

    def _extract_stream_from_page(self, page_html):
        m_raw = re.search(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\});', page_html)
        if m_raw:
            m_url = re.search(r'["\']url["\']\s*:\s*["\']([^"\']*)["\']', m_raw.group(1))
            if m_url:
                cand = m_url.group(1).replace("\\/", "/")
                if cand:
                    return cand

        m_m3u8 = re.findall(r'(https?://[^\s"\'\$<>]+\.m3u8[^\s"\'\$<>]*)', page_html, re.I)
        if m_m3u8:
            return m_m3u8[0].replace("\\/", "/")
        return ""

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_id = str(raw_id).strip()

        detail_url = "%s/index.php/vod/detail/id/%s.html" % (self.siteUrl, target_id)
        res = self._fetch(detail_url)
        html = res.get("text", "")

        t_m = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
        raw_title = t_m.group(1).split("-")[0].replace("在线播放", "").strip() if t_m else ""
        v_title = clean_label(raw_title) if raw_title else ("在线视频·%s" % target_id)

        pic_m = re.search(r'(?:data-original|data-src|src)=["\']([^"\']*(?:upload|\.jpg|\.png|\.jpeg|\.webp)[^"\']*)["\']', html, re.I)
        v_pic = pic_m.group(1).strip() if pic_m else ""
        if v_pic.startswith("//"):
            v_pic = "https:" + v_pic
        elif v_pic.startswith("/"):
            v_pic = self.siteUrl + v_pic

        desc_m = re.search(r'class=["\'][^"\']*(?:content|desc|summary|text)[^"\']*["\'][^>]*>([\s\S]*?)<', html, re.I)
        raw_desc = clean_label(desc_m.group(1)) if desc_m else ""
        if raw_desc:
            v_content = "🦋 蝴蝶影视专线直连 | %s | 官方交流群: @tvshare23" % raw_desc
        else:
            v_content = "🦋 蝴蝶影视专线加速播放 | 官方TG交流群：@tvshare23 | 4K高清原生极速画质"

        episodes = []
        default_play_url = "/index.php/vod/play/id/%s/sid/1/nid/1.html" % target_id
        episodes.append("正片$%s" % default_play_url)

        seen_rec_ids = set([target_id])
        rec_blocks = re.findall(r'<div[^>]+class=["\']vod-list["\'][\s\S]*?<a[^>]+href=["\'](?:/index\.php)?/vod/detail/id/(\d+)\.html["\'][\s\S]*?<p[^>]+class=["\']vod-name["\']>([\s\S]*?)</p>', html, re.I)

        rec_idx = 1
        for r_id, r_name in rec_blocks:
            clean_rid = str(r_id).strip()
            if clean_rid in seen_rec_ids:
                continue
            seen_rec_ids.add(clean_rid)

            clean_rtitle = clean_label(r_name)
            if not clean_rtitle:
                clean_rtitle = "推荐·%s" % clean_rid

            short_title = clean_rtitle[:16]
            rec_play_path = "/index.php/vod/play/id/%s/sid/1/nid/1.html" % clean_rid
            payload = "%s@@@%s" % (rec_play_path, quote(clean_rtitle))

            episodes.append("%02d·%s$%s" % (rec_idx, short_title, payload))
            rec_idx += 1
            if rec_idx > 24:
                break

        vod = {
            "vod_id": target_id,
            "vod_name": v_title,
            "vod_pic": v_pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks(self.brandDirector.replace("🦋 ", ""), "全%s部连播" % len(episodes)),
            "vod_content": v_content,
            "vod_play_from": "蝴蝶专线",
            "vod_play_url": "#".join(episodes)
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        raw_val = str(id).strip()
        desc_title = ""

        if "@@@" in raw_val:
            target_path, raw_title = raw_val.split("@@@", 1)
            desc_title = unquote(raw_title)
        else:
            target_path = raw_val

        target_url = self.siteUrl + target_path if target_path.startswith("/") else target_path

        res_p = self._fetch(target_url, referer=self.siteUrl + "/")
        html_p = res_p.get("text", "")

        final_play_url = self._extract_stream_from_page(html_p)

        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }

        is_direct = bool(".m3u8" in final_play_url or ".mp4" in final_play_url)

        res_dict = {
            "parse": 0 if is_direct else 1,
            "playUrl": "",
            "url": final_play_url if final_play_url else target_url,
            "header": headers
        }
        if desc_title:
            res_dict["desc"] = desc_title

        return res_dict

    def searchContent(self, key, quick, pg="1"):
        del quick
        page = 1
        try:
            page = int(pg)
        except Exception:
            page = 1

        search_url = "%s/index.php/vod/search/page/%s/wd/%s.html" % (self.siteUrl, page, quote(str(key)))
        res = self._fetch(search_url)
        html = res.get("text", "")

        cards = self._parse_cards_from_html(html)

        has_next = len(cards) >= 10
        total_count = int(page * len(cards) + 100) if has_next else int(page * len(cards))
        page_count = int(page + 1) if has_next else int(page)

        return {
            "list": cards,
            "page": int(page),
            "pagecount": page_count,
            "limit": len(cards) if cards else 20,
            "total": total_count
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]