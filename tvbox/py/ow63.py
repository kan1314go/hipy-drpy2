# -*- coding: utf-8 -*-

import re
import json
import ssl
import gzip
import zlib
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

def decode_page(raw):
    if not raw:
        return raw or ""
    if "videoData" in raw or "/zh/screen/" in raw:
        return raw
    m = re.search(r'"([0-9a-fA-F]{500,})"', raw)
    if m:
        try:
            dec = bytes.fromhex(m.group(1)).decode("utf-8")
            if len(dec) > 1000:
                return dec
        except Exception:
            pass
    return raw

def extract_video_data(text):
    i = text.find("videoData")
    if i < 0:
        return None
    j = text.find("{", i)
    if j < 0:
        return None
    depth = 0
    k = j
    in_str = False
    esc = False
    n = len(text)
    while k < n:
        c = text[k]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == '"':
            in_str = not in_str
        elif not in_str:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[j:k + 1])
                    except Exception:
                        return None
        k += 1
    return None

def first_img(v):
    if isinstance(v, list):
        if not v:
            return ""
        v = v[0]
    if isinstance(v, dict):
        v = v.get("img") or v.get("src") or ""
    return v if isinstance(v, str) else ""

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteName = "ow63"
        self.siteUrl = "https://ow63.com"
        self.hosts = ["https://ow63.com", "https://fagjil.asia", "https://www.izo440.sbs"]
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        self._pass_cookie = "_slide_passed=1"
        self.timeout = 8
        self.options = {}

        self.cats = [
            ("new-release", "最近更新"),
            ("trending", "热门"),
            ("browse/44041", "日本无码"),
            ("browse/44050", "日本有码"),
            ("browse/44002", "中文字幕"),
            ("browse/44006", "三级伦理"),
            ("browse/44090", "国产"),
            ("browse/44011", "麻豆传媒"),
            ("browse/44091", "主播视讯"),
            ("browse/44092", "蜜桃影像传媒"),
            ("browse/44093", "其他传媒"),
            ("browse/44094", "欧美性爱"),
            ("browse/44095", "黑料事件"),
            ("browse/44096", "91制片厂"),
            ("browse/44097", "台湾swag"),
            ("browse/44098", "精东影业"),
            ("browse/44099", "天美传媒"),
            ("browse/44100", "美女写真"),
            ("browse/44101", "糖心Vlog"),
            ("browse/44102", "星空无限传媒"),
            ("browse/44103", "葫芦影业"),
            ("browse/44104", "中字无码"),
            ("browse/44106", "中字有码"),
            ("browse/44107", "女同系列"),
            ("browse/44015", "SM调教"),
            ("browse/43997", "卡通动漫"),
            ("browse/44300", "水果派解说"),
            ("browse/44315", "国产厂商"),
        ]

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        try:
            self.ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except Exception:
            pass

        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def getName(self):
        return self.siteName

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        return True

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "native-ad")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".ts", "index.png"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _fetch(self, url, referer=None, timeout=None, limit=None):
        if timeout is None:
            timeout = self.timeout
        if url.startswith("http"):
            candidates = [url]
            ref = referer if referer else (self.siteUrl + "/")
        else:
            candidates = [h + url for h in self.hosts]
            ref = referer if referer else (self.hosts[0] + "/zh/")

        last_err = ""
        for u in candidates:
            try:
                req = urllib.request.Request(u, headers={
                    "User-Agent": self._ua,
                    "Referer": ref,
                    "Cookie": self._pass_cookie,
                    "Accept": "text/html,application/json,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive"
                })
                with self.opener.open(req, timeout=timeout) as r:
                    raw = r.read(limit) if limit else r.read()
                    ctype = (r.headers.get("Content-Encoding") or "").lower()
                    if "gzip" in ctype or raw[:2] == b"\x1f\x8b":
                        raw = gzip.decompress(raw)
                    elif "deflate" in ctype or raw[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    charset = "utf-8"
                    ct = r.headers.get("Content-Type") or ""
                    m = re.search(r"charset=([\w-]+)", ct, re.I)
                    if m:
                        charset = m.group(1).lower()
                    if charset in ("iso-8859-1", "ascii", "latin-1"):
                        charset = "utf-8"
                    try:
                        return r.status, raw.decode(charset, errors="replace")
                    except Exception:
                        return r.status, raw.decode("utf-8", errors="replace")
            except Exception as e:
                last_err = str(e)
        return None, last_err

    def _get_page(self, path):
        code, text = self._fetch(path)
        if code is None:
            return ""
        return decode_page(text)

    def _probe_playlist(self, vurl):
        try:
            code, text = self._fetch(vurl, limit=4096)
        except Exception:
            return None, ""
        return code, text

    def _parse_cards(self, text):
        vods = []
        if not text:
            return vods
        pat = re.compile(r'<a href="(/zh/screen/[^"]+)"\s+title="([^"]*)">\s*<img src="([^"]+)"[^>]*>\s*</a>(.*?)</div>', re.S)
        dur_pat = re.compile(r'video-duration[^>]*>\s*([^<]+?)\s*<', re.S)
        for m in pat.finditer(text):
            href, title, pic, rest = m.groups()
            dur = dur_pat.search(rest)
            meta_str = html_lib.unescape(dur.group(1)).strip() if dur else ""
            clean_title = html_lib.unescape(title).strip()
            clean_title = re.sub(r"[\r\n\t]+", " ", clean_title).strip()
            vods.append({
                "vod_id": href,
                "vod_name": clean_title,
                "vod_pic": pic,
                "vod_remarks": format_remarks("ZakaTV", meta_str if meta_str else "高清"),
                "style": {"type": "rect", "ratio": 1.78}
            })
        return vods

    def homeContent(self, filter):
        classes = [{"type_id": t, "type_name": n} for t, n in self.cats]
        return {
            "class": classes,
            "filters": {}
        }

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        del filter, extend
        slug = str(tid).strip("/")
        try:
            target_page = int(pg)
        except Exception:
            target_page = 1
        if target_page < 1:
            target_page = 1

        if target_page <= 1:
            path = "/zh/%s?order=latest" % slug
        else:
            path = "/zh/%s/page/%d?order=latest" % (slug, target_page)

        vods = self._parse_cards(self._get_page(path))
        card_count = len(vods)
        page_count = target_page + 1 if card_count >= 15 else target_page
        total_count = int(target_page * card_count + 100) if card_count >= 15 else int(target_page * card_count)

        return {
            "list": vods,
            "page": int(target_page),
            "pagecount": int(page_count),
            "limit": 24,
            "total": int(total_count)
        }

    def searchContent(self, key, quick, pg="1"):
        del quick
        try:
            target_page = int(pg)
        except Exception:
            target_page = 1
        if target_page < 1:
            target_page = 1

        path = "/zh/lookup?keyword=%s" % quote(str(key))
        if target_page > 1:
            path = "/zh/lookup/page/%d?keyword=%s" % (target_page, quote(str(key)))

        vods = self._parse_cards(self._get_page(path))
        card_count = len(vods)
        page_count = target_page + 1 if card_count >= 15 else target_page
        total_count = int(target_page * card_count + 100) if card_count >= 15 else int(target_page * card_count)

        return {
            "list": vods,
            "page": int(target_page),
            "pagecount": int(page_count),
            "limit": 24,
            "total": int(total_count)
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else ids
        vid = str(raw_id).strip().lstrip("/")
        if vid.startswith("zh/screen/"):
            vid = vid[len("zh/screen/"):]
        page_path = "/zh/screen/" + vid
        text = self._get_page(page_path)
        d = extract_video_data(text) if text else None
        if not d:
            return {"list": []}

        title = (d.get("title") or vid).strip()
        title = html_lib.unescape(title)
        title = re.sub(r"[\r\n\t]+", " ", title).strip()

        pic = d.get("thumbnail_loc") or d.get("preview") or d.get("images") or ""
        pic = first_img(pic)
        duration = d.get("duration") or ""
        fanhao = d.get("fanhao") or ""
        stype = d.get("sourceType") or ""

        desc_lines = []
        if fanhao:
            desc_lines.append("番号：" + str(fanhao))
        actors = d.get("actor") or d.get("actors") or []
        if isinstance(actors, list) and actors:
            desc_lines.append("演员：" + "、".join(str(a) for a in actors[:6]))
        maker = d.get("makers") or d.get("maker") or d.get("studio") or ""
        if maker:
            desc_lines.append("厂商：" + str(maker))
        if d.get("faxing"):
            desc_lines.append("发行：" + str(d.get("faxing")))
        if d.get("release_date"):
            desc_lines.append("发布：" + str(d.get("release_date")))
        if d.get("rating"):
            desc_lines.append("评分：" + str(d.get("rating")))
        if d.get("view_count"):
            desc_lines.append("播放：" + str(d.get("view_count")))
        tags = d.get("genres") or d.get("tag") or d.get("tags") or []
        if isinstance(tags, list) and tags:
            desc_lines.append("标签：" + "、".join(str(t) for t in tags[:10]))
        sdesc = d.get("s_description") or ""
        if sdesc:
            desc_lines.append("简介：" + str(sdesc))

        raw_desc = " | ".join(desc_lines)
        if raw_desc:
            vod_content = "📺ZakaTV专线直连 | %s | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl" % raw_desc
        else:
            vod_content = "📺ZakaTV专线加速播放 | 官方TG交流群：https://t.me/+3t5XRPPo9mlkZDRl | 4K高清原生极速画质"

        vurl = d.get("video_url") or ""
        play_url = ""
        remark_tag = "在线"
        if vurl:
            if "playergo.top" in vurl or stype == "missav":
                code, txt = self._probe_playlist(vurl)
                if code == 200 and "#EXT-X-STREAM-INF" in txt:
                    play_url = page_path
                    remark_tag = "在线"
                elif code == 200:
                    remark_tag = "仅预览"
                else:
                    play_url = page_path
                    remark_tag = "在线"
            else:
                play_url = page_path
                remark_tag = "在线"

        meta_parts = [x for x in [duration, fanhao, remark_tag] if x]
        meta_info = " / ".join(meta_parts) if meta_parts else "正片"

        vod = {
            "vod_id": page_path,
            "vod_name": title,
            "vod_pic": pic,
            "vod_bg": pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("ZakaTV", meta_info),
            "vod_content": vod_content,
            "vod_play_from": "Zaka专线",
            "vod_play_url": "正片$%s" % play_url
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        raw_val = id[0] if isinstance(id, (list, tuple)) else id
        url = str(raw_val or "").strip()
        vurl = ""
        if "/zh/screen/" in url:
            path = url[url.find("/zh/screen/"):]
            text = self._get_page(path)
            d = extract_video_data(text) if text else None
            if d:
                vurl = d.get("video_url") or ""
        elif url:
            vurl = url

        if not vurl:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}

        if "playergo.top" in vurl:
            code, txt = self._probe_playlist(vurl)
            if code == 200 and "#EXT-X-STREAM-INF" not in txt:
                return {"parse": 0, "playUrl": "", "url": "", "header": {}}

        if ".m3u8" not in vurl.lower() and "?" not in vurl:
            vurl = vurl + "?format=.m3u8"
        elif ".m3u8" not in vurl.lower() and "?" in vurl:
            vurl = vurl + "&format=.m3u8"

        return {
            "parse": 0,
            "playUrl": "",
            "url": vurl,
            "header": {
                "User-Agent": self._ua,
                "Referer": "https://ow63.com/"
            }
        }

    def liveContent(self):
        return ""

    def action(self, action):
        return {"msg": "ok"}

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]