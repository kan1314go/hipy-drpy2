#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
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

def dump_to_shared_folder(filename, content):
    target_paths = [
        "/sdcard/Pictures/" + filename,
        "/storage/emulated/0/Pictures/" + filename,
        "/sdcard/Download/" + filename,
        "/storage/emulated/0/Download/" + filename,
        filename
    ]
    for path in target_paths:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return path
        except Exception:
            continue
    return None

def format_remarks(brand="📺ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

def clean_label(text):
    clean = re.sub(r"[\$#\r\n\t]+", "", str(text or "")).strip()
    return clean[:24] if len(clean) > 24 else clean

def clean_stream_url(raw_str):
    if not raw_str:
        return ""
    clean = str(raw_str).replace("\\u002F", "/").replace("\\/", "/").strip()
    m = re.search(r'(https?://[^\s"\'\$<>]+\.m3u8[^\s"\'\$<>]*)', clean)
    if m:
        return m.group(1).strip()
    m_mp4 = re.search(r'(https?://[^\s"\'\$<>]+\.mp4[^\s"\'\$<>]*)', clean)
    if m_mp4:
        return m_mp4.group(1).strip()
    return clean

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://wbpe0dni.tiankongxkxk1.sbs"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.gate_token = ""

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
        return "星空中文影院"

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "native-ad", "stat.php")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", "streamhls", "master.m3u8", ".flv", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _ensure_gate(self):
        if self.gate_token:
            return True
        res = self._raw_fetch(self.siteUrl)
        html = res.get("text", "")
        token_m = re.search(r"var\s+token\s*=\s*['\"]([^'\"]+)['\"]", html)
        if token_m:
            self.gate_token = token_m.group(1).strip()
            return True
        return False

    def _raw_fetch(self, target_url, referer=""):
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
        if self.gate_token:
            headers["Cookie"] = "xk_gate=" + quote(self.gate_token)

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with urllib.request.urlopen(req, timeout=8, context=self.ctx) as resp:
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

    def _fetch(self, target_url, referer=""):
        self._ensure_gate()
        return self._raw_fetch(target_url, referer=referer)

    def homeContent(self, filter):
        classes = [
            {"type_id": "1", "type_name": "国产"},
            {"type_id": "6", "type_name": "自拍"},
            {"type_id": "7", "type_name": "三观尽毁"},
            {"type_id": "24", "type_name": "无码"},
            {"type_id": "60", "type_name": "情色短剧"},
            {"type_id": "50", "type_name": "有码"},
            {"type_id": "25", "type_name": "中字"},
            {"type_id": "26", "type_name": "欧美"},
            {"type_id": "27", "type_name": "动漫"},
            {"type_id": "28", "type_name": "三级片"},
            {"type_id": "10", "type_name": "反差婊"},
            {"type_id": "11", "type_name": "网爆门"},
            {"type_id": "29", "type_name": "AV解说"},
            {"type_id": "9", "type_name": "传媒"},
            {"type_id": "8", "type_name": "迷奸强奸"},
            {"type_id": "12", "type_name": "偷拍"},
            {"type_id": "30", "type_name": "兄妹"},
            {"type_id": "31", "type_name": "母子"},
            {"type_id": "32", "type_name": "小姨"},
            {"type_id": "33", "type_name": "嫂子"},
            {"type_id": "34", "type_name": "野外"},
            {"type_id": "35", "type_name": "换妻"},
            {"type_id": "36", "type_name": "儿媳"},
            {"type_id": "37", "type_name": "下海"},
            {"type_id": "2", "type_name": "网红"},
            {"type_id": "15", "type_name": "学生妹"},
            {"type_id": "3", "type_name": "萝莉"},
            {"type_id": "51", "type_name": "黑料"},
            {"type_id": "13", "type_name": "福利姬"},
            {"type_id": "14", "type_name": "吃瓜"},
            {"type_id": "16", "type_name": "人兽"},
            {"type_id": "5", "type_name": "探花"},
            {"type_id": "38", "type_name": "瑜伽裤"},
            {"type_id": "52", "type_name": "技师"},
            {"type_id": "53", "type_name": "绿帽"},
            {"type_id": "54", "type_name": "丝足"},
            {"type_id": "55", "type_name": "偷情"},
            {"type_id": "56", "type_name": "校园"},
            {"type_id": "57", "type_name": "撸管"},
            {"type_id": "4", "type_name": "大秀"},
            {"type_id": "58", "type_name": "制服"},
            {"type_id": "39", "type_name": "兽耳系列"},
            {"type_id": "20", "type_name": "喷水"},
            {"type_id": "40", "type_name": "多人群P"},
            {"type_id": "23", "type_name": "AI换脸"},
            {"type_id": "22", "type_name": "性虐"},
            {"type_id": "17", "type_name": "人妖"},
            {"type_id": "41", "type_name": "Cosplay"},
            {"type_id": "18", "type_name": "OnlyFans"},
            {"type_id": "59", "type_name": "黑巨炮"}
        ]
        filters = {}
        for c in classes:
            cid = c["type_id"]
            filters[cid] = [
                {
                    "key": "by",
                    "name": "排序",
                    "value": [
                        {"n": "最新", "v": "time"},
                        {"n": "浏览", "v": "hits"},
                        {"n": "评分", "v": "score"}
                    ]
                }
            ]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1

        sort_by = ""
        if isinstance(extend, dict):
            sort_by = str(extend.get("by", "")).strip()

        if sort_by in ("hits", "score", "time"):
            if page <= 1:
                target_url = "%s/show/%s-/by/%s.html" % (self.siteUrl, tid, sort_by)
            else:
                target_url = "%s/show/%s-%d/by/%s.html" % (self.siteUrl, tid, page, sort_by)
        else:
            if page <= 1:
                target_url = "%s/t/%s.html" % (self.siteUrl, tid)
            else:
                target_url = "%s/t/%s-%d.html" % (self.siteUrl, tid, page)

        res = self._fetch(target_url)
        html = res.get("text", "")

        vod_list = []
        seen_ids = set()

        # 方案 A: 严格 card 容器匹配
        card_blocks = re.findall(r'<div[^>]+class=["\'][^"\']*card[^"\']*["\'][\s\S]*?</div>\s*</div>', html, re.I)
        if not card_blocks:
            card_blocks = re.findall(r'<div[^>]+class=["\'][^"\']*card[^"\']*["\'][\s\S]*?</div>', html, re.I)

        for blk in card_blocks:
            href_m = re.search(r'href=["\'](/s/\d+\.html|/[^"\']*/\d+\.html)["\']', blk)
            if not href_m:
                continue
            vod_id = href_m.group(1).strip()
            if vod_id in seen_ids or vod_id.startswith("/t/") or vod_id.startswith("/tag/"):
                continue
            seen_ids.add(vod_id)

            pic = ""
            pic_m = re.search(r'background-image:\s*url\(([^)]+)\)', blk, re.I)
            if pic_m:
                pic = pic_m.group(1).strip('\'"')
            else:
                img_m = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+)["\']', blk)
                if img_m:
                    pic = img_m.group(1).strip()

            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = self.siteUrl + pic

            title = ""
            title_m = re.search(r'<a[^>]+class=["\'][^"\']*title[^"\']*["\'][^>]*>([\s\S]*?)</a>', blk, re.I)
            if title_m:
                title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            else:
                t_alt = re.search(r'title=["\']([^"\']+)["\']', blk)
                title = t_alt.group(1).strip() if t_alt else "精彩视频"

            score_m = re.search(r'<span[^>]+class=["\'][^"\']*badge-score[^"\']*["\'][^>]*>([\s\S]*?)</span>', blk)
            badge_m = re.search(r'<span[^>]+class=["\'][^"\']*badge[^"\']*["\'][^>]*>([\s\S]*?)</span>', blk)
            rem_parts = []
            if badge_m:
                rem_parts.append(re.sub(r'<[^>]+>', '', badge_m.group(1)).strip())
            if score_m:
                rem_parts.append(re.sub(r'<[^>]+>', '', score_m.group(1)).strip() + "分")
            remarks = " ".join(rem_parts) if rem_parts else "高清"

            vod_list.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": format_remarks("📺ZakaTV", remarks),
                "style": {"type": "rect", "ratio": 1.78}
            })

        # 方案 B: 若方案 A 匹配为空（短剧结构变异），全量提取 grid 内部的链接
        if not vod_list:
            grid_m = re.search(r'<div[^>]+class=["\'][^"\']*grid[^"\']*["\'][\s\S]*?</main>', html, re.I)
            cand_html = grid_m.group(0) if grid_m else html

            link_matches = re.findall(r'<a[^>]+href=["\'](/s/\d+\.html|/[^"\']*/\d+\.html)["\'][\s\S]*?</a>', cand_html, re.I)
            for raw_a in link_matches:
                href_sub = re.search(r'href=["\']([^"\']+)["\']', raw_a)
                if not href_sub:
                    continue
                cand_id = href_sub.group(1).strip()
                if cand_id in seen_ids or cand_id.startswith("/t/"):
                    continue
                seen_ids.add(cand_id)

                pic_b = ""
                bg_b = re.search(r'background-image:\s*url\(([^)]+)\)', raw_a, re.I)
                if bg_b:
                    pic_b = bg_b.group(1).strip('\'"')
                else:
                    src_b = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+)["\']', raw_a)
                    if src_b:
                        pic_b = src_b.group(1).strip()
                if pic_b.startswith("//"):
                    pic_b = "https:" + pic_b
                elif pic_b.startswith("/"):
                    pic_b = self.siteUrl + pic_b

                t_b = re.search(r'title=["\']([^"\']+)["\']', raw_a)
                title_b = t_b.group(1).strip() if t_b else re.sub(r'<[^>]+>', '', raw_a).strip()
                if not title_b:
                    title_b = "精彩短剧"

                vod_list.append({
                    "vod_id": cand_id,
                    "vod_name": title_b,
                    "vod_pic": pic_b,
                    "vod_remarks": format_remarks("📺ZakaTV", "短剧"),
                    "style": {"type": "rect", "ratio": 1.78}
                })

        # 若依然为空，且当前正在请求短剧分类，落盘原始报文供研判
        if not vod_list and str(tid) == "60":
            dump_to_shared_folder("phase2_short_drama_dump.json", json.dumps({
                "tid": tid,
                "url": target_url,
                "html_len": len(html),
                "html_slice": html[:10000]
            }, ensure_ascii=False, indent=2))

        pagecount = page + 1
        total_m = re.search(r'data-total=["\'](\d+)["\']', html)
        if total_m:
            try:
                pagecount = int(total_m.group(1))
            except Exception:
                pass

        if not vod_list:
            pagecount = 1

        return {
            "page": page,
            "pagecount": pagecount if pagecount > 0 else 1,
            "limit": 20,
            "total": pagecount * 20 if vod_list else 0,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_url = self.siteUrl + raw_id if raw_id.startswith("/") else raw_id

        res = self._fetch(target_url)
        html = res.get("text", "")

        title_m = re.search(r'<title>([\s\S]*?)</title>', html, re.I)
        title = title_m.group(1).replace("-星空中文影院", "").replace("_星空中文影院", "").strip() if title_m else "超清正片"

        pic_m = re.search(r'class=["\']poster["\'][^>]*<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
        pic = ""
        if pic_m:
            pic = pic_m.group(1).strip()
            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = self.siteUrl + pic

        main_play_url = ""
        play_matches = re.findall(r'<a[^>]+href=["\'](/s-p/\d+-\d+-\d+\.html)["\'][^>]*>', html, re.I)
        if play_matches:
            main_play_url = play_matches[0]
        else:
            num_match = re.search(r'\d+', raw_id)
            if num_match:
                main_play_url = "/s-p/%s-1-1.html" % num_match.group(0)

        episodes = ["正片$%s@@@%s" % (main_play_url, quote(title))]

        if main_play_url:
            p_res = self._fetch(self.siteUrl + main_play_url)
            p_html = p_res.get("text", "")

            side_matches = re.findall(r'<a[^>]+class=["\']play-side-item["\'][^>]+href=["\'](/s-p/\d+-\d+-\d+\.html)["\'][^>]+title=["\']([^"\']+)["\']', p_html, re.I)
            if not side_matches:
                side_matches = re.findall(r'<a[^>]+href=["\'](/s-p/\d+-\d+-\d+\.html)["\'][^>]+class=["\']play-side-item["\'][^>]+title=["\']([^"\']+)["\']', p_html, re.I)

            seen_p_urls = set([main_play_url])
            r_idx = 1
            for p_href, p_title in side_matches:
                if p_href in seen_p_urls:
                    continue
                seen_p_urls.add(p_href)
                cl_t = clean_label(p_title)
                if not cl_t:
                    continue
                episodes.append("%02d·%s$%s@@@%s" % (r_idx, cl_t, p_href, quote(p_title)))
                r_idx += 1
                if r_idx > 24:
                    break

        content_desc = "📺ZakaTV专线直连 | 极速硬解 | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl"
        desc_m = re.search(r'<div[^>]+class=["\']article-content["\'][^>]*>([\s\S]*?)</div>', html, re.I)
        if desc_m:
            raw_c = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()
            if raw_c:
                content_desc = "📺ZakaTV专线直连 | %s | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl" % raw_c

        vod = {
            "vod_id": raw_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_bg": pic,
            "vod_background": pic,
            "vod_banner": pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("📺ZakaTV", "全%d部连播" % len(episodes)),
            "vod_content": content_desc,
            "vod_play_from": "Zaka专线",
            "vod_play_url": "#".join(episodes)
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw_val = str(id).strip()
        desc_title = ""
        if "@@@" in raw_val:
            target_entry, raw_title = raw_val.split("@@@", 1)
            try:
                desc_title = unquote(raw_title)
            except Exception:
                desc_title = raw_title
        else:
            target_entry = raw_val

        play_url_to_fetch = self.siteUrl + target_entry if target_entry.startswith("/") else target_entry

        res = self._fetch(play_url_to_fetch)
        html = res.get("text", "")

        real_url = ""
        p_match = re.search(r'player_data\s*=\s*({[\s\S]*?});', html)
        if not p_match:
            p_match = re.search(r'player_aaaa\s*=\s*({[\s\S]*?});', html)

        if p_match:
            try:
                p_obj = json.loads(p_match.group(1))
                real_url = clean_stream_url(p_obj.get("url", ""))
            except Exception:
                u_m = re.search(r'["\']url["\']\s*:\s*["\']([^"\']+)["\']', p_match.group(1))
                if u_m:
                    real_url = clean_stream_url(u_m.group(1))

        if not real_url:
            m_url = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
            if m_url:
                real_url = clean_stream_url(m_url.group(0))

        if not real_url:
            real_url = play_url_to_fetch

        is_direct = any(k in real_url.lower() for k in (".m3u8", ".mp4"))

        stream_headers = {
            "User-Agent": self._ua,
            "Origin": self.siteUrl,
            "Referer": self.siteUrl + "/"
        }

        result = {
            "parse": 0 if is_direct else 1,
            "jx": 0,
            "playUrl": "",
            "url": real_url,
            "header": stream_headers
        }
        if desc_title:
            result["desc"] = desc_title
        return result

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1

        search_url = "%s/sou/%s-%d.html" % (self.siteUrl, quote(key), page)
        res = self._fetch(search_url)
        html = res.get("text", "")

        vod_list = []
        card_blocks = re.findall(r'<div[^>]+class=["\']card["\'][\s\S]*?</div>\s*</div>', html, re.I)
        if not card_blocks:
            card_blocks = re.findall(r'<div[^>]+class=["\']card["\'][\s\S]*?</div>', html, re.I)

        seen_ids = set()
        for blk in card_blocks:
            href_m = re.search(r'href=["\'](/s/\d+\.html)["\']', blk)
            if not href_m:
                continue
            vod_id = href_m.group(1).strip()
            if vod_id in seen_ids:
                continue
            seen_ids.add(vod_id)

            pic = ""
            pic_m = re.search(r'background-image:\s*url\(([^)]+)\)', blk, re.I)
            if pic_m:
                pic = pic_m.group(1).strip('\'"')
                if pic.startswith("//"):
                    pic = "https:" + pic
                elif pic.startswith("/"):
                    pic = self.siteUrl + pic

            title = ""
            title_m = re.search(r'<a[^>]+class=["\']title["\'][^>]*>([\s\S]*?)</a>', blk, re.I)
            if title_m:
                title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()

            vod_list.append({
                "vod_id": vod_id,
                "vod_name": title if title else key,
                "vod_pic": pic,
                "vod_remarks": format_remarks("📺ZakaTV", "搜索结果"),
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