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

def fix_mojibake(text):
    if not text:
        return ""
    try:
        raw_b = text.encode("latin1")
        return raw_b.decode("utf-8")
    except Exception:
        return text

def clean_label(text):
    clean_t = re.sub(r"[\$#\r\n\t]+", " ", str(text or "")).strip()
    return clean_t[:24]

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://kkb1.sixnicepf.cc"
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

        self.typeMap = {
            "1": "必射精选", "6": "家庭乱伦", "7": "吃瓜黑料", "8": "酒店探花",
            "9": "欧美劲爆", "10": "中文字幕", "11": "熟女少妇", "12": "制服诱惑", "20": "AI换脸",
            "2": "特色仓库", "13": "野战车震", "14": "日韩无码", "15": "强奸乱伦",
            "16": "群P换妻", "21": "人妻系列", "22": "国产主播", "23": "AV明星", "24": "日韩精品",
            "3": "成人精选", "25": "SM重味", "26": "巨乳尤物", "27": "百合女同",
            "28": "直播裸聊", "29": "学生空姐", "30": "成人动漫", "31": "颜射系列", "32": "反差母狗",
            "4": "另类专区", "33": "撸管必看", "34": "自拍偷拍", "35": "口交视频",
            "36": "颜值正义", "37": "偷情少妇", "38": "伦理影片", "39": "自慰系列", "40": "教师学生",
            "5": "深夜福利", "41": "深夜福利", "42": "国产传媒", "43": "国产视频",
            "44": "日本有码", "45": "日本无码", "46": "欧美无码", "47": "激情动漫", "48": "明星换脸", "49": "女优明星",
            "17": "网曝黑料", "50": "网曝黑料", "51": "网曝黑料", "52": "伦理三级",
            "53": "萝莉少女", "54": "极品媚黑", "55": "女同性恋", "56": "网红头条", "57": "韩国主播", "58": "VR视角"
        }

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
        return "Zaka·泡芙AV"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

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
            except Exception as e:
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": "timeout", "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_id": "1", "type_name": "必射精选"},
            {"type_id": "2", "type_name": "特色仓库"},
            {"type_id": "3", "type_name": "成人精选"},
            {"type_id": "4", "type_name": "另类专区"},
            {"type_id": "5", "type_name": "深夜福利"},
            {"type_id": "17", "type_name": "网曝黑料"}
        ]

        filters = {
            "1": [
                {
                    "key": "sub",
                    "name": "分类",
                    "value": [
                        {"n": "全部", "v": "1"},
                        {"n": "家庭乱伦", "v": "6"},
                        {"n": "吃瓜黑料", "v": "7"},
                        {"n": "酒店探花", "v": "8"},
                        {"n": "欧美劲爆", "v": "9"},
                        {"n": "中文字幕", "v": "10"},
                        {"n": "熟女少妇", "v": "11"},
                        {"n": "制服诱惑", "v": "12"},
                        {"n": "AI换脸", "v": "20"}
                    ]
                },
                {
                    "key": "by",
                    "name": "排序",
                    "value": [
                        {"n": "最新上架", "v": "time"},
                        {"n": "最多观看", "v": "hits"}
                    ]
                }
            ],
            "2": [
                {
                    "key": "sub",
                    "name": "分类",
                    "value": [
                        {"n": "全部", "v": "2"},
                        {"n": "野战车震", "v": "13"},
                        {"n": "日韩无码", "v": "14"},
                        {"n": "强奸乱伦", "v": "15"},
                        {"n": "群P换妻", "v": "16"},
                        {"n": "人妻系列", "v": "21"},
                        {"n": "国产主播", "v": "22"},
                        {"n": "AV明星", "v": "23"},
                        {"n": "日韩精品", "v": "24"}
                    ]
                },
                {
                    "key": "by",
                    "name": "排序",
                    "value": [
                        {"n": "最新上架", "v": "time"},
                        {"n": "最多观看", "v": "hits"}
                    ]
                }
            ],
            "3": [
                {
                    "key": "sub",
                    "name": "分类",
                    "value": [
                        {"n": "全部", "v": "3"},
                        {"n": "SM重味", "v": "25"},
                        {"n": "巨乳尤物", "v": "26"},
                        {"n": "百合女同", "v": "27"},
                        {"n": "直播裸聊", "v": "28"},
                        {"n": "学生空姐", "v": "29"},
                        {"n": "成人动漫", "v": "30"},
                        {"n": "颜射系列", "v": "31"},
                        {"n": "反差母狗", "v": "32"}
                    ]
                },
                {
                    "key": "by",
                    "name": "排序",
                    "value": [
                        {"n": "最新上架", "v": "time"},
                        {"n": "最多观看", "v": "hits"}
                    ]
                }
            ],
            "4": [
                {
                    "key": "sub",
                    "name": "分类",
                    "value": [
                        {"n": "全部", "v": "4"},
                        {"n": "撸管必看", "v": "33"},
                        {"n": "自拍偷拍", "v": "34"},
                        {"n": "口交视频", "v": "35"},
                        {"n": "颜值正义", "v": "36"},
                        {"n": "偷情少妇", "v": "37"},
                        {"n": "伦理影片", "v": "38"},
                        {"n": "自慰系列", "v": "39"},
                        {"n": "教师学生", "v": "40"}
                    ]
                },
                {
                    "key": "by",
                    "name": "排序",
                    "value": [
                        {"n": "最新上架", "v": "time"},
                        {"n": "最多观看", "v": "hits"}
                    ]
                }
            ],
            "5": [
                {
                    "key": "sub",
                    "name": "分类",
                    "value": [
                        {"n": "全部", "v": "5"},
                        {"n": "国产传媒", "v": "42"},
                        {"n": "国产视频", "v": "43"},
                        {"n": "日本有码", "v": "44"},
                        {"n": "日本无码", "v": "45"},
                        {"n": "欧美无码", "v": "46"},
                        {"n": "激情动漫", "v": "47"},
                        {"n": "明星换脸", "v": "48"},
                        {"n": "女优明星", "v": "49"}
                    ]
                },
                {
                    "key": "by",
                    "name": "排序",
                    "value": [
                        {"n": "最新上架", "v": "time"},
                        {"n": "最多观看", "v": "hits"}
                    ]
                }
            ],
            "17": [
                {
                    "key": "sub",
                    "name": "分类",
                    "value": [
                        {"n": "全部", "v": "17"},
                        {"n": "网曝黑料", "v": "51"},
                        {"n": "伦理三级", "v": "52"},
                        {"n": "萝莉少女", "v": "53"},
                        {"n": "极品媚黑", "v": "54"},
                        {"n": "女同性恋", "v": "55"},
                        {"n": "网红头条", "v": "56"},
                        {"n": "韩国主播", "v": "57"},
                        {"n": "VR视角", "v": "58"}
                    ]
                },
                {
                    "key": "by",
                    "name": "排序",
                    "value": [
                        {"n": "最新上架", "v": "time"},
                        {"n": "最多观看", "v": "hits"}
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

    def _extract_best_pic(self, blk):
        for attr in ("data-original", "data-src", "src"):
            m = re.search(r'%s=["\']([^"\']+)["\']' % attr, blk, re.I)
            if m:
                u = m.group(1).strip()
                if u and "nopic.gif" not in u and not u.startswith("data:"):
                    if u.startswith("//"):
                        return "https:" + u
                    elif u.startswith("/") and not u.startswith("/static/"):
                        return self.siteUrl + u
                    return u
        return ""

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        try:
            page = int(pg)
        except Exception:
            page = 1

        ext = extend if isinstance(extend, dict) else {}
        target_id = ext.get("sub", tid)
        by_val = ext.get("by", "time")

        vod_list = []
        pagecount = page + 1

        ajax_url = "%s/index.php/ajax/data.html?mid=1&tid=%s&by=%s&limit=20&page=%d" % (self.siteUrl, target_id, by_val, page)
        res_api = self._fetch(ajax_url)
        if res_api.get("code") == 200 and res_api.get("text"):
            try:
                jdata = json.loads(res_api["text"])
                if jdata.get("code") == 1 and jdata.get("list"):
                    pagecount = int(jdata.get("pagecount", pagecount))
                    for item in jdata["list"]:
                        v_id = "/index.php/vod/detail/id/%s.html" % item.get("vod_id")
                        v_name = fix_mojibake(item.get("vod_name", ""))
                        v_pic = item.get("vod_pic", "")
                        if v_pic.startswith("//"):
                            v_pic = "https:" + v_pic
                        elif v_pic.startswith("/") and not v_pic.startswith("/static/"):
                            v_pic = self.siteUrl + v_pic

                        sub_cate = self.typeMap.get(str(item.get("type_id")), "")
                        vod_list.append({
                            "vod_id": v_id,
                            "vod_name": v_name,
                            "vod_pic": v_pic,
                            "vod_remarks": format_remarks("ZakaTV", sub_cate),
                            "style": {"type": "rect", "ratio": 1.78}
                        })
            except Exception:
                pass

        if not vod_list:
            if by_val == "hits":
                req_path = "/index.php/vod/show/by/hits/id/%s/page/%d.html" % (target_id, page) if page > 1 else "/index.php/vod/show/by/hits/id/%s.html" % target_id
            else:
                req_path = "/index.php/vod/show/id/%s/page/%d.html" % (target_id, page) if page > 1 else "/index.php/vod/type/id/%s.html" % target_id

            res_html = self._fetch(self.siteUrl + req_path)
            html = res_html.get("text", "")

            m_page = re.search(r'(\d+)\s*/\s*(\d+)\s*&#x9875;', html)
            if m_page:
                try:
                    pagecount = int(m_page.group(2))
                except Exception:
                    pass

            card_splits = re.split(r'<article[^>]+class=["\'][^"\']*dx-card[^"\']*["\']', html)
            if len(card_splits) <= 1:
                card_splits = re.split(r'<div[^>]+class=["\'][^"\']*(?:item|col|dx-card)[^"\']*["\']', html)

            for blk in card_splits[1:]:
                m_link = re.search(r'<a[^>]+href=["\'](/index\.php/vod/detail/id/\d+\.html)["\'][^>]*>', blk)
                if not m_link:
                    continue
                detail_href = m_link.group(1)

                pic_url = self._extract_best_pic(blk)

                m_title = re.search(r'alt=["\']([^"\']+)["\']', blk)
                if not m_title:
                    m_title = re.search(r'title=["\']([^"\']+)["\']', blk)
                raw_t = m_title.group(1).strip() if m_title else "未知视频"
                title = fix_mojibake(raw_t)

                m_meta = re.search(r'class=["\']dx-card__cate["\']>([^<]+)<', blk)
                meta_str = fix_mojibake(m_meta.group(1).strip()) if m_meta else ""

                vod_list.append({
                    "vod_id": detail_href,
                    "vod_name": title,
                    "vod_pic": pic_url,
                    "vod_remarks": format_remarks("ZakaTV", meta_str),
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return {
            "page": page,
            "pagecount": max(pagecount, 1),
            "limit": 20,
            "total": max(pagecount, 1) * 20,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        detail_url = self.siteUrl + raw_id if raw_id.startswith("/") else raw_id

        res = self._fetch(detail_url)
        html = res.get("text", "")

        title_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html)
        raw_title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else "正片"
        main_title = fix_mojibake(raw_title)

        pic = ""
        pic_m = re.search(r'<div class="dx-detail__pic"[^>]*>([\s\S]*?)</div>', html)
        if pic_m:
            pic = self._extract_best_pic(pic_m.group(1))
        if not pic:
            m_og = re.search(r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
            if m_og:
                pic = m_og.group(1).strip()
        if pic.startswith("//"):
            pic = "https:" + pic
        elif pic.startswith("/") and not pic.startswith("/static/"):
            pic = self.siteUrl + pic

        m_play_url = re.search(r'href=["\'](/index\.php/vod/play/id/\d+/sid/\d+/nid/\d+\.html)["\']', html)
        main_play_path = m_play_url.group(1) if m_play_url else ""

        episodes = ["正片$%s@@@%s" % (main_play_path, quote(main_title))]

        seen_links = set([raw_id, main_play_path])
        rec_matches = re.findall(r'<a[^>]+class=["\']dx-card["\'][^>]+href=["\'](/index\.php/vod/detail/id/\d+\.html)["\'][^>]*title=["\']([^"\']+)["\']', html)
        if not rec_matches:
            rec_matches = re.findall(r'<a[^>]+href=["\'](/index\.php/vod/detail/id/\d+\.html)["\'][^>]*title=["\']([^"\']+)["\']', html)

        rec_idx = 1
        for href, r_title in rec_matches:
            if href in seen_links:
                continue
            seen_links.add(href)
            fixed_rec_t = fix_mojibake(r_title)
            c_label = clean_label(fixed_rec_t)
            episodes.append("%02d·%s$%s@@@%s" % (rec_idx, c_label, href, quote(fixed_rec_t)))
            rec_idx += 1
            if rec_idx > 30:
                break

        cate_m = re.search(r'<a href="/index\.php/vod/type/id/\d+\.html">([^<]+)</a>', html)
        cate_str = fix_mojibake(cate_m.group(1).strip()) if cate_m else "专线高清"

        full_desc = "📺ZakaTV专线直连 | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl | 4K高清原生画质 | 全%d集连播" % len(episodes)

        vod = {
            "vod_id": raw_id,
            "vod_name": main_title,
            "vod_pic": pic,
            "vod_bg": pic,
            "vod_background": pic,
            "vod_banner": pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("ZakaTV", cate_str),
            "vod_content": full_desc,
            "vod_play_from": "Zaka专线",
            "vod_play_url": "#".join(episodes)
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw_val = str(id).strip()
        desc_title = ""
        if "@@@" in raw_val:
            target_path, enc_title = raw_val.split("@@@", 1)
            desc_title = unquote(enc_title)
        else:
            target_path = raw_val

        play_url = ""
        if "/vod/play/" in target_path:
            play_url = self.siteUrl + target_path if target_path.startswith("/") else target_path
        elif "/vod/detail/" in target_path:
            detail_target = self.siteUrl + target_path if target_path.startswith("/") else target_path
            res_d = self._fetch(detail_target)
            d_html = res_d.get("text", "")
            m_p = re.search(r'href=["\'](/index\.php/vod/play/id/\d+/sid/\d+/nid/\d+\.html)["\']', d_html)
            if m_p:
                play_url = self.siteUrl + m_p.group(1)
            else:
                play_url = detail_target

        real_m3u8 = ""
        if play_url:
            res = self._fetch(play_url)
            html = res.get("text", "")

            m_json = re.search(r'var\s+player_data\s*=\s*(\{[\s\S]*?\})\s*</script>', html)
            if m_json:
                try:
                    pdata = json.loads(m_json.group(1))
                    real_m3u8 = pdata.get("url", "")
                except Exception:
                    pass

            if not real_m3u8:
                m_direct = re.search(r'(https?:\\/\\/[^"\'\s<>]+\.m3u8[^"\'\s<>]*)', html)
                if m_direct:
                    real_m3u8 = m_direct.group(1).replace("\\/", "/")

        result = {
            "header": {
                "User-Agent": self._ua,
                "Referer": self.siteUrl + "/"
            }
        }

        if desc_title:
            result["desc"] = desc_title

        if real_m3u8:
            result["parse"] = 0
            result["playUrl"] = ""
            result["url"] = real_m3u8
        else:
            result["parse"] = 1
            result["playUrl"] = ""
            result["url"] = play_url if play_url else (self.siteUrl + target_path)

        return result

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1

        search_url = "%s/index.php/vod/search/page/%d/wd/%s.html" % (self.siteUrl, page, quote(key))
        res = self._fetch(search_url)
        html = res.get("text", "")

        card_splits = re.split(r'<article[^>]+class=["\'][^"\']*dx-card[^"\']*["\']', html)
        if len(card_splits) <= 1:
            card_splits = re.split(r'<div[^>]+class=["\'][^"\']*(?:item|col|dx-card)[^"\']*["\']', html)

        vod_list = []
        for blk in card_splits[1:]:
            m_link = re.search(r'<a[^>]+href=["\'](/index\.php/vod/detail/id/\d+\.html)["\'][^>]*>', blk)
            if not m_link:
                continue
            detail_href = m_link.group(1)

            pic_url = self._extract_best_pic(blk)

            m_title = re.search(r'alt=["\']([^"\']+)["\']', blk)
            if not m_title:
                m_title = re.search(r'title=["\']([^"\']+)["\']', blk)
            raw_t = m_title.group(1).strip() if m_title else key
            title = fix_mojibake(raw_t)

            vod_list.append({
                "vod_id": detail_href,
                "vod_name": title,
                "vod_pic": pic_url,
                "vod_remarks": format_remarks("ZakaTV", "搜索结果"),
                "style": {"type": "rect", "ratio": 1.78}
            })

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 20 else page,
            "limit": 20,
            "total": max(page, 1) * 20,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]