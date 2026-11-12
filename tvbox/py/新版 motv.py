import re
import json
import urllib.request
import urllib.error
from urllib.parse import urljoin, quote, urlparse

try:
    import requests
except ImportError:
    requests = None

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        pass

LANGS = ("cn", "hk", "en", "th", "vi", "ja", "id", "ms", "tl", "bn", "es", "pt")

VC_CLASS = {
    "20": "日本,有码",
    "50": "日本,无码",
    "25": "欧美",
    "41": "中国",
    "29": "动漫",
}

# tid 50: try these vc values in order. Site has no dedicated
# JP-uncensored link, but the pattern is JP,<attr> and uncensored
# is a known attr (data-classnot, video tag). Fall back to JP (all).
VC_CLASS_ALT = {
    "50": ["日本,無碼", "日本"],
}

VC_CLASS_VALUES = {
    "日本,有码", "日本", "日本,无码", "日本,無碼", "欧美", "中国", "动漫",
    "日本HD", "欧美HD", "Onlyfan", "香港", "亞洲",
    "其他", "@ai",
}

# /cn/ may use simplified forms; try both when fetching
VC_SIMPLIFIED = {
    "亞洲": "亚洲",
}

FILTER_DIMS = [
    ("116", "国家", ["日本", "中国", "欧美", "韩国", "台湾", "香港", "亚洲", "其他"]),
    ("127", "内容类型", []),
    ("131", "人物", []),
    ("191", "对象", []),
    ("198", "情节", []),
    ("266", "拍摄", []),
    ("285", "服装", []),
    ("301", "场所", []),
    ("343", "发行商", []),
]


class Spider(BaseSpider):
    def __init__(self):
        self.base_url = "https://motv.app/cn"
        self.host = "https://motv.app/cn"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": "https://motv.app/cn/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.extend = {}
        self.session = None
        self.s = None
        self.sess = None
        if requests is not None:
            try:
                self.session = requests.Session()
                self.session.headers.update(self.headers)
                self.s = self.session
                self.sess = self.session
            except Exception:
                self.session = None
                self.s = None
                self.sess = None

    def getName(self):
        return "MOTV"

    def getDependence(self):
        return []

    def init(self, extend=""):
        ext = extend
        if isinstance(ext, str) and ext.strip().startswith("{"):
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}
        if isinstance(ext, dict):
            self.extend = ext
            base = ext.get("base_url") or ext.get("host") or ext.get("url") or ""
            if isinstance(base, str) and base.startswith("http"):
                self.base_url = base.rstrip("/")
                self.host = self.base_url
                self.headers["Referer"] = self.base_url + "/"
        return None

    def setExtendInfo(self, extend):
        return self.init(extend)

    def destroy(self):
        return None

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def homeContent(self, filter=None):
        cates = self._cates()
        groups = self._filter_groups()
        filters = {}
        for c in cates:
            filters[c["type_id"]] = groups
        return {"class": cates, "filters": filters}

    def homeVideoContent(self):
        return {"list": self._fetch_home()}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        pg = self._to_int(pg, 1)
        if pg < 1:
            pg = 1
        fvals = self._filter_values(filter, extend)
        items, pagecount, total = self._fetch_category(str(tid or "20"), pg, fvals)
        return {
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": 12,
            "total": total,
        }

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ""
        else:
            vid = str(ids or "")
        url = self._play_url(vid)
        html = self._get(url)
        name = self._match(html, r"<h1[^>]*>(.*?)</h1>")
        if not name:
            name = self._match(html, r"<title>(.*?)</title>")
        pic = self._match(html, r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)')
        if not pic:
            pic = self._match(html, r'data-original=["\']([^"\']+)')
        desc = self._clean(self._match(html, r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)'))
        actor = self._clean(self._match(html, r"vod_actor\s*=\s*['\"]([^'\"]+)"))
        year = self._clean(self._match(html, r"vod_year\s*=\s*['\"]([^'\"]+)"))
        area = self._clean(self._match(html, r"vod_area\s*=\s*['\"]([^'\"]+)"))
        remarks = self._clean(self._match(html, r"vod_remarks\s*=\s*['\"]([^'\"]+)"))
        play_urls = self._play_urls(html, vid)
        vod = {
            "vod_id": vid,
            "vod_name": self._clean(name) or vid,
            "vod_pic": self._abs_url(pic),
            "type_name": "",
            "vod_year": year,
            "vod_area": area,
            "vod_remarks": remarks,
            "vod_actor": actor,
            "vod_director": "",
            "vod_content": desc,
            "vod_play_from": "MOTV",
            "vod_play_url": play_urls,
        }
        return {"list": [vod], "parse": 0, "jx": 0}

    def searchContent(self, key, quick=False, pg="1"):
        pg = self._to_int(pg, 1)
        if pg < 1:
            pg = 1
        wd = quote(str(key or ""))
        url = "%s/vod/search.html?wd=%s" % (self.base_url, wd)
        if pg > 1:
            url = "%s/vod/search/page/%d/wd/%s.html" % (self.base_url, pg, wd)
        html = self._get(url, {"Referer": self.base_url + "/"})
        items = self._html_list(html)
        return {"list": items, "page": pg, "pagecount": 999 if items else 1}

    def playerContent(self, flag, ids, vipFlags=None):
        if isinstance(ids, (list, tuple)):
            pid = str(ids[0]) if ids else ""
        else:
            pid = str(ids or "")
        if pid.startswith("http"):
            play_url = pid
        elif "/vod/play/" in pid:
            play_url = urljoin(self.base_url + "/", pid.lstrip("/"))
        else:
            play_url = self._play_url(pid)
        play_url = self._norm_lang(play_url)
        page = self._get(play_url)
        watch = self._player_url(page)
        ua = self.headers["User-Agent"]
        if watch:
            watch_html = self._get(
                watch,
                {"Referer": play_url, "Origin": self.base_url, "Accept": "*/*"},
            )
            m3u8 = self._match(watch_html, r"var\s+src\s*=\s*['\"]([^'\"]+\.m3u8[^'\"]*)")
            if not m3u8:
                m3u8 = self._match(watch_html, r"['\"]([^'\"]+\.m3u8[^'\"]*)")
            if m3u8:
                real = urljoin(watch, m3u8.replace("\\/", "/"))
                u = urlparse(watch)
                return {
                    "parse": 0,
                    "jx": 0,
                    "playUrl": "",
                    "url": real,
                    "header": {
                        "User-Agent": ua,
                        "Referer": watch,
                        "Origin": u.scheme + "://" + u.netloc,
                    },
                    "format": "application/x-mpegURL",
                }
            m3u8 = self._match(page, r"['\"]([^'\"]+\.m3u8[^'\"]*)")
            if m3u8:
                real = urljoin(play_url, m3u8.replace("\\/", "/"))
                return {
                    "parse": 0,
                    "jx": 0,
                    "playUrl": "",
                    "url": real,
                    "header": {"User-Agent": ua, "Referer": play_url, "Origin": self.base_url},
                    "format": "application/x-mpegURL",
                }
            return {
                "parse": 0,
                "jx": 0,
                "playUrl": "",
                "url": watch,
                "header": {"User-Agent": ua, "Referer": play_url, "Origin": self.base_url},
            }
        return {
            "parse": 1,
            "jx": 0,
            "playUrl": "",
            "url": play_url,
            "header": {"User-Agent": ua, "Referer": self.base_url + "/"},
        }

    def localProxy(self, param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        if not isinstance(param, dict):
            param = {}
        return [404, "text/plain", b"Not Found", {}]

    def _cates(self):
        return [
            {"type_name": "日本有碼", "type_id": "20"},
            {"type_name": "日本無碼", "type_id": "50"},
            {"type_name": "歐美风情", "type_id": "25"},
            {"type_name": "國產原創", "type_id": "41"},
            {"type_name": "動畫", "type_id": "29"},
            {"type_name": "日本HD", "type_id": "日本HD"},
            {"type_name": "歐美HD", "type_id": "欧美HD"},
            {"type_name": "Onlyfan", "type_id": "Onlyfan"},
            {"type_name": "香港", "type_id": "香港"},
            {"type_name": "亞洲", "type_id": "亞洲"},
            {"type_name": "其他", "type_id": "其他"},
            {"type_name": "AI劇場", "type_id": "@ai"},
        ]

    def _filter_groups(self):
        groups = []
        for key, name, opts in FILTER_DIMS:
            vals = [{"n": "全部", "v": ""}]
            for o in opts:
                vals.append({"n": o, "v": o})
            groups.append({"key": key, "name": name, "value": vals})
        return groups

    def _filter_values(self, filter=None, extend=None):
        data = None
        if isinstance(filter, dict):
            data = filter
        elif isinstance(filter, str) and filter.strip().startswith("{"):
            try:
                data = json.loads(filter)
            except Exception:
                data = None
        if not isinstance(data, dict) and isinstance(extend, dict):
            data = extend.get("filter") or extend.get("filters")
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    data = None
        vals = []
        if isinstance(data, dict):
            for _k, v in data.items():
                if isinstance(v, str) and v.strip():
                    vals.append(v.strip())
                elif isinstance(v, (list, tuple)):
                    for x in v:
                        if isinstance(x, str) and x.strip():
                            vals.append(x.strip())
        return vals

    def _play_url(self, vid):
        return "%s/vod/play/id/%s/sid/1/nid/1.html" % (self.base_url, str(vid))

    def _norm_lang(self, url):
        if not url:
            return ""
        m = re.match(r"^(https?://[^/]+)/([a-z]{2}(?:-[A-Za-z]+)?)(/.*)$", url)
        if m and m.group(2).lower() in LANGS:
            return m.group(1) + "/cn" + m.group(3)
        return url

    def _fetch_home(self):
        candidates = [
            "%s/" % self.base_url,
            "%s/index.php/ajax/data?mid=1&page=1&limit=20" % self.base_url,
        ]
        items, _pc, _total = self._fetch_candidates(candidates, "%s/" % self.base_url)
        return items

    def _vc_urls(self, vc, pg):
        urls = []
        vals = [vc]
        vc_s = VC_SIMPLIFIED.get(vc, "")
        if vc_s and vc_s != vc:
            vals.append(vc_s)
        for v in vals:
            enc = quote(v, safe="")
            if pg > 1:
                urls.append("%s/label/vodclass/by/time/order/desc/page/%d/vc_class/%s.html" % (self.base_url, pg, enc))
            else:
                urls.append("%s/label/vodclass/by/time/order/desc/vc_class/%s.html" % (self.base_url, enc))
        return urls

    def _fetch_category(self, tid, pg, fvals=None):
        tid = str(tid or "20")
        pg = self._to_int(pg, 1)
        if pg < 1:
            pg = 1
        candidates = []
        vc_tries = []
        if fvals:
            vcs = [v for v in fvals if isinstance(v, str) and v.strip()]
            if vcs:
                vc_tries = [[v for v in vcs]]
        if not vc_tries:
            vc = VC_CLASS.get(tid, "")
            if not vc and tid in VC_CLASS_VALUES:
                vc = tid
            if vc:
                vc_tries = [[vc]]
                for alt in VC_CLASS_ALT.get(tid, []):
                    if alt not in vc_tries[0]:
                        vc_tries.append([alt])
        for vcs in vc_tries:
            combined = ",".join(vcs)
            enc = quote(combined, safe=",")
            if pg > 1:
                candidates.append("%s/label/vodclass/by/time/order/desc/page/%d/vc_class/%s.html" % (self.base_url, pg, enc))
            else:
                candidates.append("%s/label/vodclass/by/time/order/desc/vc_class/%s.html" % (self.base_url, enc))
            combined_s = ",".join(VC_SIMPLIFIED.get(v, v) for v in vcs)
            if combined_s != combined:
                enc_s = quote(combined_s, safe=",")
                if pg > 1:
                    candidates.append("%s/label/vodclass/by/time/order/desc/page/%d/vc_class/%s.html" % (self.base_url, pg, enc_s))
                else:
                    candidates.append("%s/label/vodclass/by/time/order/desc/vc_class/%s.html" % (self.base_url, enc_s))
            for v in vcs:
                candidates.extend(self._vc_urls(v, pg))
            for v in vcs:
                enc_q = quote(v, safe="")
                if pg > 1:
                    candidates.append("%s/label/vodclass.html?vc_class=%s&page=%d" % (self.base_url, enc_q, pg))
                else:
                    candidates.append("%s/label/vodclass.html?vc_class=%s" % (self.base_url, enc_q))
                vc_s = VC_SIMPLIFIED.get(v, "")
                if vc_s and vc_s != v:
                    enc_qs = quote(vc_s, safe="")
                    if pg > 1:
                        candidates.append("%s/label/vodclass.html?vc_class=%s&page=%d" % (self.base_url, enc_qs, pg))
                    else:
                        candidates.append("%s/label/vodclass.html?vc_class=%s" % (self.base_url, enc_qs))
        candidates.append("%s/vodtype/%s/" % (self.base_url, quote(tid)))
        if pg > 1:
            candidates.append("%s/vodtype/%s-%d.html" % (self.base_url, quote(tid), pg))
        candidates.append("%s/index.php/vod/show/id/%s/page/%d" % (self.base_url, quote(tid), pg))
        candidates.append("%s/index.php/ajax/data?mid=1&tid=%s&page=%d&limit=20" % (self.base_url, quote(tid), pg))
        ref_vc = vc_tries[0][0] if vc_tries and vc_tries[0] else ""
        return self._fetch_candidates(
            candidates, "%s/label/vodclass/by/time/order/desc/vc_class/%s.html" % (self.base_url, quote(ref_vc, safe="") if ref_vc else "")
        )

    def _fetch_candidates(self, candidates, referer):
        for url in candidates:
            html = self._get(url, {"Referer": referer})
            if not html:
                continue
            if html.lstrip().startswith("{"):
                items = self._json_list(self._safe_json(html))
                if items:
                    return items, 999, 0
                continue
            items = self._html_list(html)
            if items:
                return items, self._page_count(html), self._total_count(html)
        return [], 1, 0

    def _page_count(self, html):
        if not html:
            return 999
        m = re.search(r'class="[^"]*hl-total[^"]*"[^>]*>(\d+)<', html)
        if m:
            try:
                total = int(m.group(1))
                if total > 0:
                    per = 12
                    return (total + per - 1) // per
            except Exception:
                pass
        pages = re.findall(r'/page/(\d+)/vc_class/', html)
        if pages:
            try:
                return max(int(p) for p in pages)
            except Exception:
                pass
        pages = re.findall(r'page=(\d+)', html)
        if pages:
            try:
                return max(int(p) for p in pages)
            except Exception:
                pass
        return 999

    def _total_count(self, html):
        if not html:
            return 0
        m = re.search(r'class="[^"]*hl-total[^"]*"[^>]*>(\d+)<', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return 0

    def _json_list(self, data):
        if not isinstance(data, dict):
            return []
        arr = data.get("list") or data.get("data") or data.get("rows") or data.get("items") or []
        if isinstance(arr, dict):
            arr = arr.get("list") or arr.get("data") or arr.get("rows") or arr.get("items") or []
        result = []
        seen = set()
        for item in arr:
            if not isinstance(item, dict):
                continue
            vid = str(item.get("vod_id") or item.get("id") or item.get("vodid") or "")
            name = item.get("vod_name") or item.get("vod_title") or item.get("name") or item.get("title") or ""
            pic = item.get("vod_pic") or item.get("vod_pic_slide") or item.get("vod_img") or item.get("pic") or item.get("cover") or item.get("vod_pic_thumb") or ""
            remarks = item.get("vod_remarks") or item.get("vod_blurb") or item.get("vod_version") or item.get("remarks") or item.get("note") or item.get("vod_time") or ""
            if vid and vid not in seen:
                seen.add(vid)
                result.append(
                    {
                        "vod_id": vid,
                        "vod_name": self._clean(name) or vid,
                        "vod_pic": self._abs_url(pic),
                        "vod_remarks": self._clean(remarks),
                    }
                )
        return result

    def _html_list(self, html):
        result = []
        seen = set()
        if not html:
            return result
        anchors = re.finditer(
            r'<a[^>]*class="[^"]*hl-item-thumb[^"]*"[^>]*>',
            html,
            re.S,
        )
        for m in anchors:
            tag = m.group(0)
            item = self._parse_thumb(tag)
            if item and item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                result.append(item)
        if result:
            self._attach_remarks(html, result)
            return result
        anchors = re.finditer(
            r'<a[^>]*class="[^"]*hl-br-thumb[^"]*"[^>]*>',
            html,
            re.S,
        )
        for m in anchors:
            tag = m.group(0)
            item = self._parse_thumb(tag)
            if item and item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                result.append(item)
        if result:
            return result
        for m in re.finditer(
            r'<a[^>]*href=["\']([^"\']*?/vod/play/id/(\d+)/sid/\d+/nid/\d+\.html)["\'][^>]*>',
            html,
            re.S,
        ):
            tag = m.group(0)
            item = self._parse_thumb(tag)
            if item and item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                result.append(item)
        if result:
            self._attach_remarks(html, result)
        return result

    def _parse_thumb(self, tag):
        if not tag:
            return None
        href = self._match(tag, r'href=["\']([^"\']+)')
        vid = ""
        m = re.search(r'/vod/play/id/(\d+)/', href)
        if m:
            vid = m.group(1)
        if not vid:
            vid = self._match(tag, r'data-popedom-id=["\'](\d+)')
        if not vid:
            return None
        name = self._match(tag, r'title=["\']([^"\']+)')
        pic = self._match(tag, r'data-original=["\']([^"\']+)')
        if not pic:
            pic = self._match(tag, r'data-src=["\']([^"\']+)')
        if not pic:
            pic = self._match(tag, r'data-lazy-src=["\']([^"\']+)')
        if not pic:
            pic = self._match(tag, r'src=["\']([^"\']+)')
        return {
            "vod_id": vid,
            "vod_name": self._clean(name) or vid,
            "vod_pic": self._abs_url(pic),
            "vod_remarks": "",
        }

    def _attach_remarks(self, html, result):
        if not html or not result:
            return
        by_id = {}
        for m in re.finditer(
            r'href=["\'][^"\']*?/vod/play/id/(\d+)/sid/\d+/nid/\d+\.html["\'][^>]*>(?:(?!</a>).)*?<span class="hl-lc-1 remarks">([^<]*)</span>',
            html,
            re.S,
        ):
            by_id.setdefault(m.group(1), self._clean(m.group(2)))
        for item in result:
            if not item.get("vod_remarks") and item["vod_id"] in by_id:
                item["vod_remarks"] = by_id[item["vod_id"]]

    def _play_urls(self, html, vid):
        rows = re.findall(
            r'href=["\']([^"\']*/vod/play/%s-\d+-\d+/?)["\'][^>]*>(.*?)<' % re.escape(str(vid)),
            html,
            re.S,
        )
        if not rows:
            rows = re.findall(
                r'href=["\']([^"\']*/vod/play/id/%s/sid/\d+/nid/\d+\.html)["\'][^>]*>(.*?)<' % re.escape(str(vid)),
                html,
                re.S,
            )
        if not rows:
            return "第1集$%s" % self._play_url(vid)
        result = []
        seen = set()
        for url, name in rows:
            full = self._norm_lang(urljoin(self.base_url + "/", url))
            if full not in seen:
                seen.add(full)
                label = self._clean(name) or ("第%s集" % (len(result) + 1))
                result.append("%s$%s" % (label, full))
        return "#".join(result) or "第1集$%s" % self._play_url(vid)

    def _player_url(self, html):
        raw = ""
        for key in ("player_aaaa", "player_data"):
            raw = self._balanced_json(html, key)
            if raw:
                break
        if raw:
            try:
                obj = json.loads(raw)
                url = obj.get("url") or obj.get("url_next") or obj.get("src") or ""
                if url:
                    return self._norm_lang(url.replace("\\/", "/"))
            except Exception:
                url = self._match(raw, r'"url"\s*:\s*"([^"]+)"') or self._match(raw, r"'url'\s*:\s*'([^']+)'")
                if url:
                    return self._norm_lang(url.replace("\\/", "/"))
        iframe = self._match(html, r'<iframe[^>]+src=["\']([^"\']+)')
        if iframe:
            return self._norm_lang(urljoin(self.base_url + "/", iframe))
        return ""

    def _balanced_json(self, text, key):
        idx = (text or "").find(key)
        if idx < 0:
            return ""
        start = text.find("{", idx)
        if start < 0:
            return ""
        depth = 0
        instr = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if instr:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    instr = False
                continue
            if ch == '"':
                instr = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return ""

    def _abs_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        return urljoin(self.base_url.rstrip("/") + "/", url)

    def _safe_json(self, text):
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _json(self, url, headers=None):
        try:
            return json.loads(self._get(url, headers))
        except Exception:
            return {}

    def _get(self, url, headers=None):
        h = dict(self.headers)
        if headers:
            h.update(headers)
        text = ""
        if self.session is not None:
            try:
                r = self.session.get(url, headers=h, timeout=20)
                r.encoding = "utf-8"
                text = r.text
            except Exception:
                text = ""
        if not text:
            try:
                req = urllib.request.Request(url, headers=h)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read()
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("utf-8", "ignore")
            except Exception:
                text = ""
        if "Prohibited Entry" in text or "forbidden.1083.city" in text:
            return ""
        return text

    def _match(self, text, pattern):
        m = re.search(pattern, text or "", re.S)
        return m.group(1).strip() if m else ""

    def _clean(self, text):
        text = re.sub(r"<[^>]+>", " ", text or "")
        text = (
            text.replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
        )
        return re.sub(r"\s+", " ", text).strip()

    def _to_int(self, value, default=0):
        try:
            return int(value)
        except Exception:
            return default
