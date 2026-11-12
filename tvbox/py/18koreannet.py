# -*- coding: utf-8 -*-
# 18korean.net — TVBox / biecuile Python 爬虫
# 接口链路：/watch/{slug} -> .epbtn[data-ep] -> GET /api/v1/episodes/{ep}/sources -> HLS token -> /index.m3u8
# 自测： python 18korean.py
import json
import re
import html as htmllib
import requests

try:                                  # biecuile / 标准 py-spider 运行时
    from base.spider import Spider as _Base
except Exception:
    _Base = object

BASE = "https://18korean.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

CATS = [
    ("movie",    "电影",     "/movies"),
    ("tv",       "剧集",     "/tv-series"),
    ("top_week", "周榜",     "/top/week"),
    ("top_all",  "总榜",     "/top"),
    ("top_imdb", "IMDb榜",   "/top/imdb"),
    ("top_tmdb", "TMDB榜",   "/top/tmdb"),
]

CARD_RE = re.compile(r'<a class="card" href="([^"]+)"(.*?)</a>', re.S)
EP_RE   = re.compile(r'<button class="epbtn[^"]*"([^>]*)>')
SV_RE   = re.compile(
    r'<div class="wserver" data-sv="(\d+)">\s*<div class="wserver-head">\s*'
    r'<span class="wserver-name">([^<]*)</span>', re.S)


class Spider(_Base):

    def __init__(self):
        self.extend = ""
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Referer": BASE + "/",
        })

    # ---------------- 基础 ----------------
    def getNameSpace(self):
        return ""

    def getDependency(self):
        return []

    def init(self, extend=""):
        self.extend = extend or ""

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|mpd)(\?|$)', url or "", re.I))

    def _abs(self, u):
        u = htmllib.unescape((u or "").strip())
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        return BASE + (u if u.startswith("/") else "/" + u)

    def _slug(self, u):
        u = (u or "").split("?")[0].split("#")[0].rstrip("/")
        return u.split("/")[-1] if u else ""

    def _get(self, url, referer=None, timeout=20):
        try:
            r = self.s.get(url, headers={"Referer": referer or BASE + "/"}, timeout=timeout)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
        except Exception:
            pass
        return ""

    # ---------------- 解析 ----------------
    def _cards(self, html):
        out, seen = [], set()
        for href, blk in CARD_RE.findall(html or ""):
            slug = self._slug(href)
            if not slug or slug in seen or slug in ("movies", "tv-series", "top"):
                continue
            m = re.search(r'class="card-title"[^>]*>([^<]*)<', blk) or re.search(r'alt="([^"]*)"', blk)
            name = htmllib.unescape(m.group(1)).strip() if m else ""
            if not name:
                continue
            seen.add(slug)
            m = re.search(r'<img[^>]+src="([^"]+)"', blk) or re.search(r'data-src="([^"]+)"', blk)
            pic = self._abs(m.group(1)) if m else ""
            m = re.search(r'class="card-sub">([^<]*)<', blk)
            rem = htmllib.unescape(m.group(1)).strip() if m else ""
            out.append({"vod_id": slug, "vod_name": name, "vod_pic": pic, "vod_remarks": rem})
        return out

    def _page_urls(self, path, pg):
        if pg <= 1:
            return [BASE + path]
        # 站点翻页参数未知，按可能性依次探测
        return ["%s%s?page=%d" % (BASE, path, pg),
                "%s%s/page/%d" % (BASE, path, pg),
                "%s%s?p=%d" % (BASE, path, pg)]

    def _list(self, path, pg):
        for u in self._page_urls(path, pg):
            html = self._get(u)
            if html and (self._cards(html) or pg == 1):
                return self._cards(html)
        return []

    # ---------------- 接口 ----------------
    def homeContent(self, filter):
        data = {"class": [{"type_id": t, "type_name": n} for t, n, _ in CATS], "filters": {}}
        home = self._get(BASE + "/")
        vlist = self._cards(home)
        if vlist:
            data["list"] = vlist
        return json.dumps(data, ensure_ascii=False)

    def homeVideoContent(self):
        return json.dumps({"list": self._cards(self._get(BASE + "/"))}, ensure_ascii=False)

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        path = dict((t, p) for t, _, p in CATS).get(tid, "/movies")
        vlist = self._list(path, pg)
        pagecount = pg + 1 if vlist else max(1, pg - 1)
        return json.dumps({"list": vlist, "page": pg, "pagecount": pagecount,
                           "limit": len(vlist) or 24, "total": 999999}, ensure_ascii=False)

    def _episodes(self, slug):
        """返回 [(线路名, [(集名, epId)])]"""
        routes = []
        first = self._get("%s/watch/%s?sv=1&part=1" % (BASE, slug), referer="%s/%s" % (BASE, slug))
        if not first:
            return routes
        svs = SV_RE.findall(first) or [("1", "线路1")]
        for sv, name in svs:
            html = first if sv == "1" else self._get(
                "%s/watch/%s?sv=%s&part=1" % (BASE, slug, sv), referer="%s/%s" % (BASE, slug))
            eps = []
            for attrs in EP_RE.findall(html):
                m = re.search(r'data-ep="(\d+)"', attrs)
                if not m:
                    continue
                n = re.search(r'data-name="([^"]*)"', attrs)
                ss = re.search(r'data-ss="(\d+)"', attrs)
                label = htmllib.unescape(n.group(1)).strip() if n else m.group(1)
                if ss and len(svs) > 1 and ss.group(1) != "1":
                    label = "S%s %s" % (ss.group(1), label)
                eps.append((label or m.group(1), m.group(1)))
            if eps:
                routes.append((htmllib.unescape(name).strip() or ("线路" + sv), eps))
        return routes

    def detailContent(self, ids):
        slug = self._slug(ids[0] if isinstance(ids, (list, tuple)) else ids)
        html = self._get("%s/%s" % (BASE, slug))
        if not html:
            return json.dumps({"list": []}, ensure_ascii=False)

        def one(pat, default=""):
            m = re.search(pat, html, re.S)
            return htmllib.unescape(m.group(1)).strip() if m else default

        name = one(r'<h1 class="info-title">([^<]+)</h1>') or slug
        pic = one(r'property="og:image" content="([^"]+)"')
        year = one(r'/year/(\d{4})')
        area = one(r'/country/[^"]*">([^<]+)</a>')
        note = one(r'<div class="info-orig">([^<]+)</div>')
        dur = one(r'<span class="badge">(\d+h[^<]*)</span>')
        genre = ", ".join(htmllib.unescape(x) for x in re.findall(r'/genre/[^"]*">([^<]+)</a>', html))
        actor = ", ".join(htmllib.unescape(x) for x in re.findall(r'/actor/[^"]*">([^<]+)</a>', html))
        director = ", ".join(htmllib.unescape(x) for x in re.findall(r'/director/[^"]*">([^<]+)</a>', html))
        content = one(r'id="tab-overview">\s*<p>(.*?)</p>')
        content = re.sub(r'<[^>]+>', '', content).strip()

        routes = self._episodes(slug)
        froms, urls = [], []
        for i, (rname, eps) in enumerate(routes):
            froms.append(rname or ("线路%d" % (i + 1)))
            urls.append("$$$".join("%s$%s|%s" % (n, e, slug) for n, e in eps))

        vod = {
            "vod_id": slug, "vod_name": name, "vod_pic": pic, "vod_year": year,
            "vod_area": area, "vod_remarks": dur or note, "vod_actor": actor,
            "vod_director": director, "type_name": genre,
            "vod_content": content, "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        return json.dumps({"list": [vod]}, ensure_ascii=False)

    def searchContent(self, key, quick, pg="1"):
        html = self._get("%s/_ajax/search?q=%s" % (BASE, requests.utils.quote(key)))
        out = []
        try:
            for it in (json.loads(html).get("results") or []):
                slug = self._slug(it.get("slug"))
                if not slug:
                    continue
                out.append({"vod_id": slug, "vod_name": it.get("title") or slug,
                            "vod_pic": self._abs(it.get("thumb")),
                            "vod_remarks": " · ".join(x for x in (it.get("year"), it.get("format")) if x)})
        except Exception:
            out = self._cards(html)
        return json.dumps({"list": out, "page": 1, "pagecount": 1,
                           "limit": len(out), "total": len(out)}, ensure_ascii=False)

    def _norm(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            u = "https:" + u
        if not u.startswith("http"):
            u = BASE + (u if u.startswith("/") else "/" + u)
        if not re.search(r'\.(m3u8|mpd|json|mp4)(\?|$)', u, re.I):
            u = u.rstrip("/") + "/index.m3u8"
        return u

    def playerContent(self, flag, id, vipFlags):
        ep, slug = (id.split("|") + [""])[:2]
        watch = "%s/watch/%s?sv=1&part=1" % (BASE, slug)
        hdr = json.dumps({"Referer": watch, "User-Agent": UA})

        api = "%s/api/v1/episodes/%s/sources" % (BASE, ep)
        body = self._get(api, referer=watch)
        files, backup = [], ""
        try:
            d = json.loads(body)
            for src in (d.get("sources") or []):
                u = self._norm(src.get("file") or src.get("url") or "")
                if u:
                    files.append(u)
            backup = d.get("backup") or d.get("backup_url") or ""
        except Exception:
            pass

        if not files and not backup:                       # 兜底：从播放页直接捞
            files = [self._abs(u) for u in re.findall(r'https?://[^"\'\s]+\.m3u8[^"\'\s]*', self._get(watch, referer=watch))]

        if files:
            return json.dumps({"parse": 0, "playUrl": "", "url": files[0], "header": hdr}, ensure_ascii=False)

        if backup:                                         # 备份线路是第三方 embed，交给嗅探
            page = self._get(backup, referer=watch)
            m = re.search(r'https?://[^"\'\s\\]+\.m3u8[^"\'\s\\]*', page)
            if m:
                return json.dumps({"parse": 0, "playUrl": "", "url": m.group(0), "header": hdr}, ensure_ascii=False)
            return json.dumps({"parse": 1, "playUrl": backup, "url": backup, "header": hdr}, ensure_ascii=False)

        return json.dumps({"parse": 0, "playUrl": "", "url": "", "header": hdr}, ensure_ascii=False)


# ==================== 自测：首页 → 分类 → 详情 → 播放 ====================
if __name__ == "__main__":
    sp = Spider()
    sp.init("")

    home = json.loads(sp.homeContent(True))
    print("分类:", [c["type_name"] for c in home["class"]])
    print("首页条目:", len(home.get("list") or []))

    cat = json.loads(sp.categoryContent("movie", "1", False, {}))
    print("分类页条目:", len(cat["list"]))
    if not cat["list"]:
        raise SystemExit("分类页为空，检查站点结构")

    slug = cat["list"][0]["vod_id"]
    det = json.loads(sp.detailContent([slug]))["list"][0]
    print("详情:", det["vod_name"], "| 线路:", det["vod_play_from"])
    if not det["vod_play_url"]:
        raise SystemExit("详情页无分集")

    ep_id = det["vod_play_url"].split("$$$")[0].split("$")[1]
    play = json.loads(sp.playerContent(det["vod_play_from"].split("$$$")[0], ep_id, []))
    print("播放:", play)

    url = play.get("url") or ""
    if url.endswith(".m3u8"):
        r = sp.s.get(url, headers={"Referer": "%s/watch/%s?sv=1&part=1" % (BASE, slug),
                                   "User-Agent": UA}, timeout=20)
        print("m3u8 状态:", r.status_code, "| 内容:", r.text[:120].replace("\n", " "))
        if r.status_code == 200 and "#EXTM3U" in r.text:
            seg = [l for l in r.text.splitlines() if l and not l.startswith("#")][:1]
            if seg:
                su = seg[0] if seg[0].startswith("http") else requests.compat.urljoin(url, seg[0])
                print("首分片状态:", sp.s.get(su, headers={"Referer": BASE + "/", "User-Agent": UA}, timeout=20).status_code)
    print("搜索:", len(json.loads(sp.searchContent("wife", True))["list"]))
    print("OK")