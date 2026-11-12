# -*- coding: utf-8 -*-
import re
import json
import time
import base64
import urllib.parse
import urllib.request

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False
    requests = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    try:
        from spider import Spider as BaseSpider
    except Exception:
        class BaseSpider(object):
            pass


class Spider(BaseSpider):
    def init(self, extend=""):
        pass

    def __init__(self):
        super(Spider, self).__init__()
        self.site_name = "AVGC9"
        self.site_url = "https://avgc9.store"
        self.api_base = self.site_url + "/api"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.site_url + "/",
        }
        self.session = requests.Session() if _HAS_REQUESTS else None
        if self.session:
            self.session.headers.update(self.headers)

    # ---------- 通道 ----------
    def _http_get(self, url, timeout=15):
        """优先 self.fetch（壳网络栈），urllib 兜底；返回文本，失败返回 ''。"""
        try:
            f = getattr(self, "fetch", None)
            if callable(f):
                r = f(url, headers=self.headers)
                t = getattr(r, "text", r)
                if isinstance(t, bytes):
                    t = t.decode("utf-8", errors="ignore")
                if t:
                    return t
        except Exception:
            pass
        for _ in range(3):
            try:
                if self.session:
                    r = self.session.get(url, headers=self.headers, timeout=timeout)
                    if r.status_code == 200:
                        return r.text
            except Exception:
                pass
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    for cs in ("utf-8", "gbk", "gb2312"):
                        try:
                            return raw.decode(cs)
                        except Exception:
                            continue
                    return raw.decode("utf-8", errors="ignore")
            except Exception as e:
                # urllib chunked 断流：用 partial 续接
                partial = getattr(e, "partial", b"")
                if partial:
                    try:
                        return partial.decode("utf-8", errors="ignore")
                    except Exception:
                        pass
                time.sleep(0.5)
        return ""

    def _api(self, path):
        """调 API，解 base64(URL 编码 JSON) 信封；失败返回 None。"""
        raw = self._http_get(self.api_base + path)
        if not raw:
            return None
        try:
            env = json.loads(raw)
        except Exception:
            return None
        if env.get("code") != 200:
            return None
        data = env.get("data")
        if not isinstance(data, str) or not data:
            return None
        try:
            decoded = base64.b64decode(data).decode("utf-8", errors="ignore")
            text = urllib.parse.unquote(decoded)
            return json.loads(text)
        except Exception:
            return None

    @staticmethod
    def _clean(s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", str(s))
        for k, v in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " "), ("&quot;", '"'), ("&#039;", "'")):
            s = s.replace(k, v)
        return s.strip()

    @staticmethod
    def _mk_item(v):
        title = v.get("title_zh") or v.get("title") or ""
        title = title.strip()
        if not title:
            return None
        code = str(v.get("title_code") or v.get("id") or "")
        if not code:
            return None
        remark = ""
        if v.get("is_uncensored"):
            remark = "无码"
        elif v.get("is_hd"):
            remark = "高清"
        return {
            "vod_id": code,
            "vod_name": title,
            "vod_pic": v.get("cover") or "",
            "vod_remarks": remark,
            "vod_year": "",
        }

    def getName(self):
        return self.site_name

    # ---------- 首页 ----------
    def homeContent(self, filter):
        classes = [
            {"type_id": "latest", "type_name": "最新"},
            {"type_id": "home", "type_name": "热门播放"},
        ]
        # 35 个标签（/api/tags/collections：4 组），类名前加组名分组，
        # 避免 35 个标签平铺成一堵墙、也避免与“女优·AI短剧”撞名
        try:
            cols = self._api("/tags/collections")
            if isinstance(cols, list):
                for cat in cols:
                    gname = (cat.get("name_zh") or cat.get("name") or "").strip()
                    for t in cat.get("tags") or []:
                        code = t.get("name_code")
                        name = (t.get("name_zh") or t.get("name") or "").strip()
                        if code and name:
                            tname = (gname + "·" + name) if gname else name
                            classes.append({"type_id": "tag:" + code, "type_name": tname})
        except Exception:
            pass
        # 热门女优前 8（按片量排）
        try:
            d = self._api("/actresses?page_no=1&page_size=8")
            if isinstance(d, dict):
                for a in d.get("list") or []:
                    code = a.get("name_code")
                    name = (a.get("name_zh") or a.get("name") or "").strip()
                    if code and name:
                        classes.append({"type_id": "actress:" + code, "type_name": "女优·" + name})
        except Exception:
            pass
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        d = self._api("/movies?page_no=1&page_size=20&sort_by=updated_at&sort_order=desc")
        items = []
        if isinstance(d, dict):
            for v in d.get("list") or []:
                it = self._mk_item(v)
                if it:
                    items.append(it)
        return {"list": items[:20]}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        tid = str(tid or "latest")
        if tid == "latest":
            path = "/movies?page_no=%d&page_size=20&sort_by=updated_at&sort_order=desc" % pg
        elif tid == "home":
            path = "/movies?page_no=%d&page_size=20&is_home=1" % pg
        elif tid.startswith("tag:"):
            code = urllib.parse.quote(tid[4:], safe="")
            path = "/movies?page_no=%d&page_size=20&tag_code=%s" % (pg, code)
        elif tid.startswith("actress:"):
            code = urllib.parse.quote(tid[8:], safe="")
            path = "/movies?page_no=%d&page_size=20&actress_code=%s" % (pg, code)
        else:
            path = "/movies?page_no=%d&page_size=20&sort_by=updated_at&sort_order=desc" % pg

        d = self._api(path)
        items, total = [], 0
        if isinstance(d, dict):
            total = int(d.get("total") or 0)
            for v in d.get("list") or []:
                it = self._mk_item(v)
                if it:
                    items.append(it)
        pagecount = (total + 19) // 20 if total else pg
        return {"list": items, "page": pg, "pagecount": pagecount, "limit": len(items), "total": total}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        code = str(ids[0]) if ids else ""
        d = self._api("/movies/" + urllib.parse.quote(code, safe=""))
        if not isinstance(d, dict) or not d.get("title"):
            return {"list": []}
        title = (d.get("title_zh") or d.get("title") or "").strip()
        play_parts = []
        for v in d.get("videos") or []:
            url = (v.get("value") or "").strip()
            if not url:
                continue
            label = (v.get("label") or "").strip() or "正片"
            play_parts.append("%s$%s" % (label, url))
        vod = {
            "vod_id": code,
            "vod_name": title or "未知",
            "vod_pic": d.get("cover") or "",
            "vod_play_from": "在线播放",
            "vod_play_url": "#".join(play_parts) if play_parts else "",
            "vod_remarks": "无码" if d.get("is_uncensored") else ("高清" if d.get("is_hd") else ""),
            "vod_year": "",
        }
        return {"list": [vod]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        raw = str(id)
        url = raw.rsplit("$", 1)[-1] if "$" in raw else raw
        url = url.strip()
        if any(x in url.lower() for x in (".m3u8", ".mp4")):
            return {"parse": 0, "playUrl": "", "url": url, "header": self.headers}
        return {"parse": 1, "playUrl": "", "url": url, "header": self.headers}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        wd = urllib.parse.quote(str(key), safe="")
        d = self._api("/movies/search?keyword=%s&page_no=%d&page_size=20" % (wd, pg))
        items, total = [], 0
        if isinstance(d, dict):
            total = int(d.get("total") or 0)
            for v in d.get("list") or []:
                it = self._mk_item(v)
                if it:
                    items.append(it)
        pagecount = (total + 19) // 20 if total else pg
        return {"list": items, "page": pg, "pagecount": pagecount, "limit": len(items), "total": total}

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass
