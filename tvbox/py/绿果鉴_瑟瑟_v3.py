# -*- coding: utf-8 -*-
"""
绿果鉴 · 瑟瑟线 · TVBox/FongMi py 源  v3.0.0
=================================================
纯标准库实现（urllib / json / re / html / base64 / hashlib），零第三方依赖。
文件名随意，类名必须是 Spider（末尾带别名兼容）。

本站源覆盖：
    校园性事 / 唯美精品 / TOPTV / 国产会所 / 榴莲视频 / 夜色A片 / 超短剧 /
    好色TV / 黄色仓库 / JavBobo / 91热爆 / PornHub / 撸鸡鸡 / JavDB / JavBus

设计要点（都是实测出来的，不是拍脑袋）：
  1. 列表"自适应"：标题不在 <a> 文本里（在 title= / alt= / <h4> / <h5> 里），
     所以按 id 聚簇，前后窗口多路兜底取字段。
  2. 播放"多路兜底"：
       - maccms 的 player_aaaa JSON（直链被写成 https:\\/\\/... 转义串，必须反转义）
       - 详情页/播放页裸 m3u8、mp4
       - 海报/缩略图同目录反推 m3u8（hsm3 那套 CDN 通用）
       - 站内专用接口（黄色仓库 count.php、超短剧 /api/play、PornHub flashvars…）
  3. 每个请求都带 Referer/UA，缺了就 403；统一 15s 超时，绝不无限等。
  4. 出错不崩：单站异常只影响该站，返回空列表 + 说明，壳里不会一片空白。
"""

import base64
import gzip
import html as _html
import http.cookiejar
import io
import json
import random
import re
import socket
import ssl
import string
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


UA_MOB = ("Mozilla/5.0 (Linux; Android 12; SM-G981B) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 15


# ---------------------------------------------------------------------------
# HTTP 层
# ---------------------------------------------------------------------------
class _Sess(object):
    """带 cookie 的会话。同一个站复用，跨站不污染。"""

    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx),
            urllib.request.HTTPRedirectHandler(),
        )

    def cookie_str(self):
        out = []
        try:
            for c in self.cj:
                out.append("%s=%s" % (c.name, c.value))
        except Exception:
            pass
        return "; ".join(out)

    def req(self, url, data=None, referer=None, headers=None, timeout=TIMEOUT):
        h = {
            "User-Agent": UA_MOB,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        if referer:
            h["Referer"] = referer
        if headers:
            h.update(headers)
        r = urllib.request.Request(url, data=data, headers=h)
        resp = self.op.open(r, timeout=timeout)
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if "gzip" in enc:
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        elif "deflate" in enc:
            try:
                raw = zlib.decompress(raw, -15)
            except Exception:
                try:
                    raw = zlib.decompress(raw)
                except Exception:
                    pass
        ctype = (resp.headers.get("Content-Type") or "")
        charset = ""
        m = re.search(r"charset=([\w-]+)", ctype, re.I)
        if m:
            charset = m.group(1).lower()
        else:
            m = re.search(br'charset=["\']?([\w-]+)', raw[:2000], re.I)
            if m:
                charset = m.group(1).decode("ascii", "ignore").lower()
        for cs in [charset, "utf-8", "gbk", "gb18030", "big5"]:
            if not cs:
                continue
            try:
                return raw.decode(cs)
            except Exception:
                continue
        return raw.decode("utf-8", "ignore")

    def get(self, url, referer=None, headers=None, timeout=TIMEOUT):
        return self.req(url, None, referer, headers, timeout)

    def post(self, url, body, referer=None, headers=None, timeout=TIMEOUT):
        if isinstance(body, dict):
            body = urllib.parse.urlencode(body)
        if isinstance(body, str):
            body = body.encode("utf-8")
        h = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        if headers:
            h.update(headers)
        return self.req(url, body, referer, h, timeout)

    def post_json(self, url, obj, referer=None, headers=None, timeout=TIMEOUT):
        body = json.dumps(obj).encode("utf-8")
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        return self.req(url, body, referer, h, timeout)


_SESS = {}
_CACHE = {}          # "siteid@vid" -> 列表里已拿到的条目，详情页被拦时兜底


def sess(key):
    s = _SESS.get(key)
    if s is None:
        s = _Sess()
        _SESS[key] = s
    return s


def log(*a):
    try:
        print("[grj]", *a)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------
def _abs(base, u):
    if not u:
        return ""
    u = _html.unescape(u.strip())
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http"):
        return u
    if u.startswith("/"):
        p = urllib.parse.urlparse(base)
        return "%s://%s%s" % (p.scheme, p.netloc, u)
    return urllib.parse.urljoin(base + "/", u)


def _clean(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _unesc(s):
    """把 https:\\/\\/a.com\\/x.m3u8 这种 JSON 转义还原。"""
    if not s:
        return ""
    return s.replace("\\/", "/").replace("\\u0026", "&").replace("\\u003d", "=").replace("\\u003f", "?")


def _dedup(items, key="vod_id"):
    seen = set()
    out = []
    for it in items:
        k = str(it.get(key, ""))
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _vod(vid, name, pic="", remarks="", content="", year="", area="", cate="", actor="", director=""):
    return {
        "vod_id": vid,
        "vod_name": name or "无标题",
        "vod_pic": pic or "",
        "vod_remarks": remarks or "",
        "vod_content": content or "",
        "vod_year": str(year or ""),
        "vod_area": area or "",
        "vod_actor": actor or "",
        "vod_director": director or "",
        "type_name": cate or "",
    }


# ---------------------------------------------------------------------------
# 通用 maccms 解析
# ---------------------------------------------------------------------------
_RE_ID = re.compile(r"id[/=](\d+)")
_RE_PLAYER = re.compile(r"player_[A-Za-z0-9]+\s*=\s*(\{.*?\})\s*</script>", re.S)
_RE_M3U8 = re.compile(r"(?:https?:)?(?:\\?/\\?/)?[^\s\"'<>()\\]{6,}\.(?:m3u8|mp4)(?:\?[^\s\"'<>()\\]*)?")


def mac_cats(html_text, base, prefix=""):
    """从首页提取分类 (名称, 值)。"""
    cats, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="([^"]*(?:vod/type/id/|vodtype/|vod/show/id/|type/id/)(\d+)[^"]*)"[^>]*>(.*?)</a>',
                         html_text, re.S):
        href, cid, name = m.group(1), m.group(2), _clean(m.group(3))
        if not name or len(name) > 14 or cid in seen:
            continue
        if any(x in name for x in ("首页", "更多", "上一", "下一", "尾页")):
            continue
        seen.add(cid)
        cats.append({"n": name, "v": cid})
    return cats


def mac_list(html_text, base, is_play_detail=False):
    """自适应取列表。返回 vod 列表。"""
    items = []
    # 找出所有"内容链接"的位置
    if is_play_detail:
        pat = re.compile(r'href="([^"]*vodplay/(\d+)-\d+-\d+\.html[^"]*)"', re.I)
    else:
        pat = re.compile(r'href="([^"]*(?:vod/detail|voddetail|/detail/id/)[^"]*?(\d+)[^"]*\.html[^"]*)"', re.I)
    hits = list(pat.finditer(html_text))
    if not hits:
        return items
    for m in hits:
        href, vid = m.group(1), m.group(2)
        start = max(0, m.start() - 600)
        end = min(len(html_text), m.end() + 900)
        win = html_text[start:end]
        a_tag = html_text[max(0, m.start() - 400):m.start()]
        # 标题：title= > alt= > a 内文本 > h4/h5 > img 后的文本
        title = ""
        mm = re.search(r'title="([^"]{2,90})"', html_text[m.start():m.start() + 300])
        if mm:
            title = mm.group(1)
        if not title:
            mm = re.search(r'alt="([^"]{2,90})"', win)
            if mm:
                title = mm.group(1)
        if not title:
            mm = re.search(r"<h[3-6][^>]*>(.*?)</h[3-6]>", win, re.S)
            if mm:
                title = _clean(mm.group(1))
        if not title:
            mm = re.search(r'title="([^"]{2,90})"', win)
            if mm:
                title = mm.group(1)
        title = _clean(title)
        title = re.sub(r"^(?:\d+\.\d+-->|\[[^\]]{1,6}\])\s*", "", title)
        if not title or len(title) < 2:
            continue
        pic = ""
        mm = re.search(r'(?:data-original|data-src|data-echo|src)="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', win, re.I)
        if mm:
            pic = _abs(base, mm.group(1))
        rem = ""
        mm = re.search(r'(?:pic-text[^>]*>|remarks?[^>]*>|class="[^"]*text-right[^"]*"[^>]*>)([^<]{1,12})<', win)
        if mm:
            rem = _clean(mm.group(1))
        items.append({
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": rem,
        })
    return _dedup(items)


def mac_pages(html_text, pg):
    """翻页数推断。"""
    mx = 1
    for m in re.finditer(r"共\s*(\d+)\s*页|pagecount[\"']?\s*[:=]\s*(\d+)", html_text):
        try:
            v = int(m.group(1) or m.group(2))
            mx = max(mx, v)
        except Exception:
            pass
    for m in re.finditer(r"[\?&/]page[/=](\d+)", html_text):
        try:
            mx = max(mx, int(m.group(1)))
        except Exception:
            pass
    if mx <= 1:
        mx = pg + 1 if (pg == 1 and len(html_text) > 20000) else pg
    return min(mx, 9999)


def find_play_url(sess_obj, base, detail_url, detail_html, referer=None):
    """从详情页/播放页里挖直链。返回 (url, headers) 或 None。"""
    ref = referer or detail_url or (base + "/")
    # 1) 详情页里直接就有
    cands = []
    for m in _RE_PLAYER.finditer(detail_html or ""):
        try:
            obj = json.loads(_unesc(m.group(1)))
            u = obj.get("url") or ""
            if u:
                cands.append(u)
        except Exception:
            pass
    for m in re.finditer(r'"(?:url|videoUrl|playUrl|src)"\s*:\s*"([^"]+\.(?:m3u8|mp4)[^"]*)"', detail_html or ""):
        cands.append(_unesc(m.group(1)))
    for m in re.finditer(r'<source[^>]+src="([^"]+\.(?:m3u8|mp4)[^"]*)"', detail_html or ""):
        cands.append(_unesc(m.group(1)))
    cands = [c for c in cands if c and c.startswith("http")]
    if cands:
        return cands[0], {"User-Agent": UA_MOB, "Referer": ref}

    # 2) 找播放页
    plays = re.findall(r'href="([^"]*(?:vod/play/|vodplay/)[^"]*)"', detail_html or "")
    plays = [_abs(base, p) for p in plays]
    seen = set()
    for pu in plays:
        if pu in seen:
            continue
        seen.add(pu)
        try:
            ph = sess_obj.get(pu, referer=ref)
        except Exception:
            continue
        # player_aaaa
        for m in _RE_PLAYER.finditer(ph):
            try:
                obj = json.loads(_unesc(m.group(1)))
                u = obj.get("url") or ""
                if u.startswith("http"):
                    return u, {"User-Agent": UA_MOB, "Referer": pu}
            except Exception:
                pass
        for m in re.finditer(r'"url"\s*:\s*"([^"]+\.(?:m3u8|mp4)[^"]*)"', ph):
            u = _unesc(m.group(1))
            if u.startswith("http"):
                return u, {"User-Agent": UA_MOB, "Referer": pu}
        for m in re.finditer(r'<source[^>]+src="([^"]+\.(?:m3u8|mp4)[^"]*)"', ph):
            u = _unesc(m.group(1))
            if u.startswith("http"):
                return u, {"User-Agent": UA_MOB, "Referer": pu}
        for m in re.finditer(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)', ph):
            return _unesc(m.group(1)), {"User-Agent": UA_MOB, "Referer": pu}
        if len(seen) >= 3:
            break
    return None


def pic_to_m3u8(pic):
    """海报/缩略图同目录反推 m3u8（hsm3 那套 CDN 的通用规律）。"""
    if not pic:
        return ""
    m = re.match(r"(https?://[^/]+/.*)/([^/]+)\.(?:jpg|jpeg|png|webp)$", pic, re.I)
    if not m:
        return ""
    return m.group(1) + "/index.m3u8"


# ---------------------------------------------------------------------------
# 站点定义
# ---------------------------------------------------------------------------
class Site(object):
    id = ""
    name = ""
    base = ""
    kind = "maccms"
    prefix = ""
    need_ua = UA_MOB
    note = ""

    def cats(self, s):
        return []

    def listing(self, s, cat, page):
        return [], 1

    def detail(self, s, vid):
        return None

    def play(self, s, vid, flag):
        return None

    # 通用
    def search(self, s, kw, page=1):
        return []


class MacSite(Site):
    """标准 maccms 站（列表/详情/播放都能自适应）。"""
    kind = "maccms"
    list_tpl = "/index.php/vod/type/id/%s.html"
    list_tpl_paged = "/index.php/vod/type/id/%s/page/%s.html"
    detail_tpl = "/index.php/vod/detail/id/%s.html"
    search_tpl = "/index.php/vod/search.html?wd=%s"

    def _u(self, path):
        return self.base + self.prefix + path

    def cats(self, s):
        try:
            h = s.get(self._u("/"))
            cs = mac_cats(h, self.base + self.prefix)
            if cs:
                return cs
        except Exception:
            pass
        return [{"n": "全部", "v": "1"}]

    def listing(self, s, cat, page):
        cat = str(cat or "1")
        if page and page > 1:
            url = self._u(self.list_tpl_paged % (cat, page))
        else:
            url = self._u(self.list_tpl % cat)
        try:
            h = s.get(url)
        except Exception:
            return [], 1
        items = mac_list(h, self.base + self.prefix)
        if not items and page == 1:
            # 有些站首页就是列表
            try:
                h2 = s.get(self._u("/"))
                items = mac_list(h2, self.base + self.prefix)
            except Exception:
                pass
        return items, mac_pages(h, page)

    def detail(self, s, vid):
        url = self._u(self.detail_tpl % vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        name = _clean((re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S) or [None, ""])[1])
        if not name:
            name = _clean((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]).split("-")[0]
        pic = ""
        m = re.search(r'(?:data-original|data-src|src)="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', h)
        if m:
            pic = _abs(self.base + self.prefix, m.group(1))
        desc = ""
        m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', h)
        if m:
            desc = _clean(m.group(1))
        # 播放集数
        eps = re.findall(r'>([^<>]{1,12})</a>', "".join(
            re.findall(r'<a[^>]+href="[^"]*vod/play/[^"]*"[^>]*>.*?</a>', h, re.S)))
        play_urls = []
        for m in re.finditer(r'href="([^"]*vod/play/[^"]*)"[^>]*>\s*([^<]{0,20})', h):
            pu = _abs(self.base + self.prefix, m.group(1))
            nm = _clean(m.group(2)) or ("第%d集" % (len(play_urls) + 1))
            if pu not in [p[0] for p in play_urls]:
                play_urls.append((pu, nm))
        if play_urls:
            play_from = "线路1"
            play_list = "#".join("%s$%s" % (nm, vid) for pu, nm in play_urls[:300])
        else:
            play_from, play_list = "", ""
        v = _vod(vid, name, pic, "", desc)
        v["vod_play_from"] = play_from
        v["vod_play_url"] = play_list
        v["_detail_url"] = url
        return v

    def search(self, s, kw, page=1):
        kw = (kw or "").strip()
        if not kw:
            return []
        q = urllib.parse.quote(kw)
        urls = [
            self._u("/index.php/vod/search.html?wd=" + q),
            self._u("/index.php/vod/search/wd/%s.html" % q),
            self._u("/vodsearch/%s-.html" % q),
            self._u("/index.php/vod/search/page/%s/wd/%s.html" % (page, q)),
        ]
        for u in urls:
            try:
                h = s.get(u, referer=self.base + "/")
            except Exception:
                continue
            items = mac_search_simple(h, kw, self.base + self.prefix)
            if items:
                return items
        return []

    def play(self, s, vid, flag=""):
        # vid 可能是 detail id，也可能是 maccms 的 "detailid$playid"
        did = str(vid).split("$")[0]
        det = self.detail(s, did)
        if not det:
            return None
        durl = det.get("_detail_url") or self._u(self.detail_tpl % did)
        # 优先用 detail 里带的播放页
        r = find_play_url(s, self.base + self.prefix, durl, "")
        if r:
            return r
        try:
            h = s.get(durl)
        except Exception:
            return None
        r = find_play_url(s, self.base + self.prefix, durl, h)
        if r:
            return r
        # 兜底：海报反推
        pm = pic_to_m3u8(det.get("vod_pic"))
        if pm:
            return pm, {"User-Agent": UA_MOB, "Referer": self.base + "/"}
        return None


# ---------------------------------------------------------------------------
# 各站适配器
# ---------------------------------------------------------------------------
class XyxssSite(MacSite):
    id = "xyxss"
    name = "校园性事"
    base = "https://48m.xyxss.cyou"


class WeimeiSite(MacSite):
    id = "weimei"
    name = "唯美精品"
    base = "https://shiresm.lol"


class ToptvSite(MacSite):
    id = "toptv"
    name = "TOPTV"
    base = "https://toptv15.cyou"

    def play(self, s, vid, flag=""):
        r = MacSite.play(self, s, vid, flag)
        if r:
            return r
        try:
            h = s.get(self._u(self.detail_tpl % str(vid).split("$")[0]))
            m = re.search(r'(?:data-original|src)="([^"]+/a3/[^"]+\.jpg)"', h)
            if m:
                u = pic_to_m3u8(_abs(self.base, m.group(1)))
                if u:
                    return u, {"User-Agent": UA_MOB, "Referer": self.base + "/"}
        except Exception:
            pass
        return None


class GuochangSite(MacSite):
    """国产会所（黄果短剧）：站点带 /huangguo 前缀，且会跳域名。"""
    id = "guochan"
    name = "国产会所"
    base = "https://hg.huanghuo.sbs"
    prefix = "/huangguo"


class YeseSite(MacSite):
    """夜色A片：分类页 /vod/show/class/<名>/id/N.html，列表卡片直接链到播放页。"""
    id = "yese"
    name = "夜色A片"
    base = "https://yese.co"
    list_tpl = "/vod/show/id/%s.html"
    list_tpl_paged = "/vod/show/id/%s.html?page=%s"
    detail_tpl = "/vod/show/id/%s.html"
    search_tpl = "/vod/search.html?wd=%s"

    def cats(self, s):
        try:
            h = s.get(self.base + "/")
            cs = [{"n": "最新上傳", "v": "/vod/show/id/1.html"}]
            seen = set(["最新上傳"])
            for m in re.finditer(r'href="(/vod/show/class/([^/"]+)/id/1\.html)"[^>]*>([^<]{1,12})<', h):
                nm = _clean(m.group(3)) or m.group(2)
                if nm in seen:
                    continue
                seen.add(nm)
                cs.append({"n": nm, "v": m.group(1)})
            return cs
        except Exception:
            return [{"n": "最新上傳", "v": "/vod/show/id/1.html"}]

    def listing(self, s, cat, page):
        cat = str(cat or "/vod/show/id/1.html")
        if not cat.startswith("/"):
            cat = "/vod/show/id/%s.html" % cat
        if page > 1:
            cat = cat + ("&" if "?" in cat else "?") + "page=%s" % page
        try:
            h = s.get(_abs(self.base, cat))
        except Exception:
            return [], 1
        items = []
        for m in re.finditer(r'<a[^>]+href="(/vod/play/id/(\d+)/[^"]*)"[^>]*>(.*?)</a>', h, re.S):
            vid = m.group(2)
            win = h[m.start():min(len(h), m.end() + 700)]
            title = ""
            mm = re.search(r'title="([^"]{2,90})"', win)
            if mm:
                title = _clean(mm.group(1))
            if not title:
                mm = re.search(r'<h[3-6][^>]*>\s*<a[^>]*>([^<]{2,90})</a>', win)
                title = _clean(mm.group(1)) if mm else ""
            if not title:
                mm = re.search(r'alt="([^"]{2,90})"', win)
                title = _clean(mm.group(1)) if mm else ""
            if not title:
                continue
            pic = ""
            mm = re.search(r'(?:data-original|data-src|src)="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', win)
            if mm:
                pic = _abs(self.base, mm.group(1))
            items.append({"vod_id": vid, "vod_name": title, "vod_pic": pic, "vod_remarks": ""})
        return _dedup(items), (page + 1 if len(items) >= 12 else page)

    def detail(self, s, vid):
        # 列表给的是播放页 id，详情走 show 页
        url = "%s/vod/show/id/%s.html" % (self.base, vid)
        try:
            h = s.get(url)
            name = _clean((re.search(r'<meta property="og:title" content="([^"]*)"', h) or [None, ""])[1])
            if not name or "夜色A片網" in name:
                pp = "%s/vod/play/id/%s/sid/1/nid/1/" % (self.base, vid)
                h2 = s.get(pp, referer=url)
                name = _clean((re.search(r'<meta property="og:title" content="([^"]*)"', h2) or
                               re.search(r"<title>(.*?)</title>", h2, re.S) or [None, ""])[1]).split("-")[0]
                h = h2
            name = re.sub(r"^(在线播放|正在播放)[:：]?\s*", "", name)
            m = re.search(r'(?:data-original|data-src|src|og:image" content)="?([^"\s>]+\.(?:jpg|jpeg|png|webp)[^"\s>]*)', h)
            pic = _abs(self.base, m.group(1)) if m else ""
            v = _vod(vid, name, pic, "", "")
            v["vod_play_from"] = "夜色A片"
            v["vod_play_url"] = "正片$%s" % vid
            v["_detail_url"] = url
            return v
        except Exception:
            return None

    def play(self, s, vid, flag=""):
        vid = str(vid).split("$")[0]
        page = "%s/vod/play/id/%s/sid/1/nid/1/" % (self.base, vid)
        try:
            h = s.get(page)
        except Exception:
            return None
        for m in _RE_PLAYER.finditer(h):
            try:
                obj = json.loads(_unesc(m.group(1)))
                u = obj.get("url") or ""
                if u.startswith("http"):
                    return u, {"User-Agent": UA_MOB, "Referer": page}
            except Exception:
                pass
        m = re.search(r'"url"\s*:\s*"([^"]+\.(?:m3u8|mp4)[^"]*)"', h)
        if m:
            return _unesc(m.group(1)), {"User-Agent": UA_MOB, "Referer": page}
        # 夜色把地址塞在 var uul = 'https://.../index.m3u8'+'m3u8文件' 里
        m = re.search(r"['\"](https?://[^'\"]+?\.(?:m3u8|mp4))", h)
        if m:
            return _unesc(m.group(1)), {"User-Agent": UA_MOB, "Referer": page}
        return None


class LlspSite(MacSite):
    """榴莲视频：列表直接给播放页 /vodplay/935309-1-1.html（详情即播放页）。"""
    id = "llsp"
    name = "榴莲视频"
    base = "https://www.llsp.me"
    list_tpl = "/vodtype/%s.html"
    list_tpl_paged = "/vodtype/%s-%s.html"
    detail_tpl = "/vodplay/%s-1-1.html"

    def cats(self, s):
        try:
            h = s.get(self.base + "/")
            cs = []
            for m in re.finditer(r'href="/vodtype/(\d+)(?:-\d+)?\.html"[^>]*>([^<]{1,14})<', h):
                cid, nm = m.group(1), _clean(m.group(2))
                if nm and {"n": nm, "v": cid} not in cs:
                    cs.append({"n": nm, "v": cid})
            if cs:
                return cs
        except Exception:
            pass
        return [{"n": "全部", "v": "3"}]

    def listing(self, s, cat, page):
        url = self.base + (self.list_tpl_paged % (cat, page) if page > 1 else self.list_tpl % cat)
        try:
            h = s.get(url)
        except Exception:
            return [], 1
        items = mac_list(h, self.base, is_play_detail=True)
        return items, mac_pages(h, page)

    def detail(self, s, vid):
        vid = str(vid).split("-")[0]
        url = self.base + self.detail_tpl % vid
        try:
            h = s.get(url)
        except Exception:
            return None
        name = _clean((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]).split("_")[0]
        m = re.search(r'(?:data-original|src)="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', h)
        pic = _abs(self.base, m.group(1)) if m else ""
        v = _vod(vid, name, pic, "", "")
        v["vod_play_from"] = "线路1"
        v["vod_play_url"] = "%s$%s" % (name[:10] or "正片", vid)
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        vid = str(vid).split("-")[0].split("$")[0]
        url = self.base + self.detail_tpl % vid
        try:
            h = s.get(url)
        except Exception:
            return None
        for m in _RE_PLAYER.finditer(h):
            try:
                obj = json.loads(_unesc(m.group(1)))
                u = obj.get("url") or ""
                if u.startswith("http"):
                    return u, {"User-Agent": UA_MOB, "Referer": url}
            except Exception:
                pass
        m = re.search(r'"url"\s*:\s*"([^"]+\.(?:m3u8|mp4)[^"]*)"', h)
        if m:
            return _unesc(m.group(1)), {"User-Agent": UA_MOB, "Referer": url}
        return None


class LujjSite(MacSite):
    """撸鸡鸡：网页播放页被广告脚本劫持，改走 maccms 的 JSON 接口 + 海报反推直链。"""
    id = "lujj"
    name = "撸鸡鸡"
    base = "https://lujj31.buzz"

    def __init__(self):
        self._waf_ok = False

    def _warm(self, s):
        """宝塔 WAF：先拿 cookie，再带 btwaf 参数走一次。"""
        if self._waf_ok:
            return
        try:
            h = s.get(self.base + "/")
            m = re.search(r"btwaf=(\d+)", h)
            if m:
                s.get(self.base + "/?btwaf=" + m.group(1), referer=self.base + "/")
            self._waf_ok = True
        except Exception:
            pass

    def cats(self, s):
        self._warm(s)
        try:
            h = s.get(self.base + "/")
            cs = mac_cats(h, self.base)
            if cs:
                return cs
        except Exception:
            pass
        return [{"n": "全部", "v": "1"}]

    def listing(self, s, cat, page):
        self._warm(s)
        cat = str(cat or "9")
        try:
            u = "%s/index.php/ajax/data?mid=1&tid=%s&limit=20&page=%s" % (self.base, cat, page)
            txt = s.get(u, referer=self.base + "/")
            data = json.loads(txt)
            items = []
            for it in data.get("list") or []:
                items.append({
                    "vod_id": str(it.get("vod_id")),
                    "vod_name": _clean(it.get("vod_name")),
                    "vod_pic": it.get("vod_pic_thumb") or it.get("vod_pic") or "",
                    "vod_remarks": _clean(it.get("vod_remarks")),
                })
            total = int(data.get("total") or 0)
            limit = 20
            pc = max(1, (total + limit - 1) // limit) if total else int(data.get("pagecount") or 1)
            return _dedup(items), min(pc, 9999)
        except Exception:
            return MacSite.listing(self, s, cat, page)

    def detail(self, s, vid):
        self._warm(s)
        try:
            u = "%s/index.php/ajax/data?mid=1&ac=detail&ids=%s" % (self.base, vid)
            data = json.loads(s.get(u, referer=self.base + "/"))
            lst = data.get("list") or []
            if lst:
                it = lst[0]
                v = _vod(vid, _clean(it.get("vod_name")), it.get("vod_pic") or "",
                         _clean(it.get("vod_remarks")), _clean(it.get("vod_content") or it.get("vod_blurb")))
                v["vod_play_from"] = "线路1"
                v["vod_play_url"] = "正片$%s" % vid
                v["vod_pic_thumb"] = it.get("vod_pic_thumb") or ""
                v["_detail_url"] = "%s/index.php/vod/detail/id/%s.html" % (self.base, vid)
                return v
        except Exception:
            pass
        return MacSite.detail(self, s, vid)

    def play(self, s, vid, flag=""):
        self._warm(s)
        did = str(vid).split("$")[0]
        # 1) JSON 里拿缩略图，反推同目录 m3u8
        try:
            u = "%s/index.php/ajax/data?mid=1&ac=detail&ids=%s" % (self.base, did)
            data = json.loads(s.get(u, referer=self.base + "/"))
            for it in (data.get("list") or []):
                for key in ("vod_pic_thumb", "vod_pic"):
                    pm = pic_to_m3u8(it.get(key) or "")
                    if pm:
                        return pm, {"User-Agent": UA_MOB, "Referer": self.base + "/"}
        except Exception:
            pass
        # 2) 退回标准流程
        return MacSite.play(self, s, did, flag)


class ChaoduanjuSite(Site):
    """超短剧：纯前端站，播放走 POST /api/play，需要同一会话 cookie。"""
    id = "cdj"
    name = "超短剧"
    base = "https://cdj6.com"

    def cats(self, s):
        try:
            h = s.get(self.base + "/")
            cs = [{"n": "全部", "v": "all"}]
            for m in re.finditer(r'href="[^"]*?(?:category|tag|cate)[^"]*?[?/]([^"/?]+)"[^>]*>([^<]{1,12})<', h):
                nm = _clean(m.group(2))
                if nm and len(nm) < 10 and {"n": nm, "v": m.group(1)} not in cs:
                    cs.append({"n": nm, "v": m.group(1)})
            return cs if len(cs) > 1 else [{"n": "全部", "v": "all"}]
        except Exception:
            return [{"n": "全部", "v": "all"}]

    def listing(self, s, cat, page):
        items = []
        url = self.base + ("/?page=%s" % page if page > 1 else "/")
        try:
            h = s.get(url)
        except Exception:
            return [], 1
        seen = set()
        for m in re.finditer(r'href="(/drama/([a-z0-9]{6,12}))"[^>]*>(.*?)</a>', h, re.S):
            path, did = m.group(1), m.group(2)
            if did in seen:
                continue
            seen.add(did)
            win = h[max(0, m.start() - 400):m.end() + 400]
            title = ""
            mm = re.search(r'<div class="card-title">([^<]{2,60})<', win)
            if mm:
                title = _clean(mm.group(1))
            if not title:
                mm = re.search(r'alt="([^"]{2,60})"', win)
                title = _clean(mm.group(1)) if mm else ""
            pic = ""
            mm = re.search(r'src="(https://stream\.[^"]+\.(?:webp|jpg|png))"', win)
            if mm:
                pic = mm.group(1)
            eps = ""
            mm = re.search(r'(\d+)\s*集', win)
            if mm:
                eps = mm.group(1) + "集"
            items.append({"vod_id": did, "vod_name": title or did, "vod_pic": pic, "vod_remarks": eps})
        return _dedup(items), (page + 1 if items else page)

    def detail(self, s, vid):
        url = self.base + "/drama/" + str(vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        name = _clean((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]).split("-")[0]
        pic = ""
        m = re.search(r'src="(https://stream\.[^"]+\.(?:webp|jpg|png))"', h)
        if m:
            pic = m.group(1)
        desc = _clean((re.search(r'<meta name="description" content="([^"]*)"', h) or [None, ""])[1])
        seqs = re.findall(r'"seq"\s*:\s*"?(\d+)"?', h)
        eps = len(set(seqs)) or 1
        v = _vod(vid, name, pic, "%d集" % eps, desc)
        v["vod_play_from"] = "超短剧"
        v["vod_play_url"] = "#".join("第%s集$%s|%s" % (i, vid, i) for i in range(1, eps + 1))
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        did, seq = str(vid), "1"
        if "|" in did:
            did, seq = did.split("|", 1)
        page = self.base + "/drama/" + did
        num = did
        try:
            h = s.get(page)  # 建立会话，同时取数字 drama_id
            m = re.search(r'data-drama-id="(\d+)"', h)
            if m:
                num = m.group(1)
        except Exception:
            pass
        if not str(num).isdigit():
            return None
        view = "".join(random.choice("0123456789abcdef") for _ in range(32))
        try:
            txt = s.post_json(self.base + "/api/play",
                              {"drama_id": int(num), "seq": int(seq), "view": view},
                              referer=page, headers={"Origin": self.base})
            j = json.loads(txt)
            src = j.get("src") or ""
            if src:
                u = src if src.startswith("http") else self.base + src
                return u, {"User-Agent": UA_MOB, "Referer": page, "Cookie": s.cookie_str()}
        except Exception:
            pass
        return None

    def search(self, s, kw, page=1):
        try:
            h = s.get(self.base + "/search?q=" + urllib.parse.quote(kw))
        except Exception:
            return []
        items = []
        for m in re.finditer(r'href="(/drama/([a-z0-9]{6,12}))"[^>]*>(.*?)</a>', h, re.S):
            win = h[max(0, m.start() - 300):m.end() + 300]
            mm = re.search(r'<div class="card-title">([^<]{2,60})<', win) or re.search(r'alt="([^"]{2,60})"', win)
            title = _clean(mm.group(1)) if mm else ""
            if kw not in title:
                continue
            pic = ""
            p = re.search(r'src="(https://stream\.[^"]+\.(?:webp|jpg))"', win)
            if p:
                pic = p.group(1)
            items.append({"vod_id": m.group(2), "vod_name": title, "vod_pic": pic, "vod_remarks": ""})
        return _dedup(items)


class HsexSite(Site):
    """好色TV：video-N.htm 结构，详情页 <source src= m3u8>。"""
    id = "hsex"
    name = "好色TV"
    base = "https://hsex.men"

    def cats(self, s):
        base_cats = [{"n": "最新", "v": "list"}, {"n": "周榜", "v": "top7_list"}, {"n": "月榜", "v": "top_list"}]
        try:
            h = s.get(self.base + "/list-1.htm")
            for m in re.finditer(r'href="((?:list|top7_list|top_list|5min_list)-\d+\.htm)"[^>]*>([^<]{1,12})<', h):
                pass
        except Exception:
            pass
        return base_cats

    def listing(self, s, cat, page):
        cat = cat or "list"
        url = "%s/%s-%s.htm" % (self.base, cat, page)
        try:
            h = s.get(url, referer=self.base + "/")
        except Exception:
            return [], 1
        items = []
        for m in re.finditer(r'<a[^>]+href="(video-(\d+)\.htm)"[^>]*>(.*?)</a>', h, re.S):
            vid = m.group(2)
            win = h[max(0, m.start() - 300):m.end() + 700]
            title = ""
            mm = re.search(r'<h5>\s*<a[^>]*>([^<]{2,80})</a>', win)
            if mm:
                title = _clean(mm.group(1))
            if not title:
                mm = re.search(r'title=\s*"([^"]{2,80})"', win)
                title = _clean(mm.group(1)) if mm else ""
            pic = ""
            mm = re.search(r"background-image:\s*url\('([^']+)'\)", win)
            if mm:
                pic = mm.group(1)
            dur = ""
            mm = re.search(r'<var class="duration">\s*([\d:]+)', win)
            if mm:
                dur = mm.group(1)
            items.append({"vod_id": vid, "vod_name": title or vid, "vod_pic": pic, "vod_remarks": dur})
        return _dedup(items), (page + 1 if len(items) >= 10 else page)

    def detail(self, s, vid):
        url = "%s/video-%s.htm" % (self.base, vid)
        try:
            h = s.get(url, referer=self.base + "/list-1.htm")
        except Exception:
            return None
        name = _clean((re.search(r'<meta property="og:title" content="([^"]*)"', h) or [None, ""])[1])
        if not name:
            name = _clean((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1])
        pic = ""
        m = re.search(r'<meta property="og:image" content="([^"]+)"', h)
        if m:
            pic = m.group(1)
        desc = _clean((re.search(r'<meta property="og:description" content="([^"]*)"', h) or [None, ""])[1])
        v = _vod(vid, name, pic, "", desc)
        v["vod_play_from"] = "好色TV"
        v["vod_play_url"] = "正片$%s" % vid
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        url = "%s/video-%s.htm" % (self.base, vid)
        try:
            h = s.get(url, referer=self.base + "/list-1.htm")
        except Exception:
            return None
        m = re.search(r'<source[^>]+src="([^"]+\.(?:m3u8|mp4)[^"]*)"', h)
        if not m:
            m = re.search(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)', h)
        if m:
            return _html.unescape(m.group(1)), {"User-Agent": UA_MOB, "Referer": url}
        return None

    def search(self, s, kw, page=1):
        try:
            h = s.get(self.base + "/search.htm?search=" + urllib.parse.quote(kw),
                      referer=self.base + "/list-1.htm")
        except Exception:
            return mac_search_simple("", kw, self.base)
        items = []
        for m in re.finditer(r'<a[^>]+href="(video-(\d+)\.htm)"[^>]*>(.*?)</a>', h, re.S):
            win = h[m.start():min(len(h), m.end() + 500)]
            mm = re.search(r'<h5>\s*<a[^>]*>([^<]{2,80})</a>', win) or re.search(r'title=\s*"([^"]{2,80})"', win)
            items.append({"vod_id": m.group(2), "vod_name": _clean(mm.group(1)) if mm else m.group(2),
                          "vod_pic": "", "vod_remarks": ""})
        return _dedup(items)


class HsckSite(Site):
    """黄色仓库：播放地址要 POST /static/count.php（带手势 token），返回 base64。"""
    id = "hsck"
    name = "黄色仓库"
    base = "https://111.9963hsck.cc"

    def cats(self, s):
        try:
            h = s.get(self.base + "/")
            cs, seen = [], set()
            for m in re.finditer(r'href="(/v5/[^"]*?type[^"]*|/list/\d+[^"]*)"[^>]*>([^<]{1,12})<', h):
                pass
            # 站点导航
            for m in re.finditer(r'href="(/[a-z0-9_/]*?(?:type|list)[^"]*)"[^>]*>([^<]{1,12})<', h):
                nm = _clean(m.group(2))
                if nm and nm not in seen and len(nm) <= 10:
                    seen.add(nm)
                    cs.append({"n": nm, "v": _abs(self.base, m.group(1))})
            if cs:
                return cs
        except Exception:
            pass
        return [{"n": "最新", "v": self.base + "/"}]

    def listing(self, s, cat, page):
        url = cat if str(cat).startswith("http") else self.base + "/"
        if page > 1 and "?" not in url:
            url = url.rstrip("/") + ("/index-%s.html" % page)
        try:
            h = s.get(url)
        except Exception:
            return [], 1
        items = []
        for m in re.finditer(r'href="(/v5/(\d+)-\d+-\d+\.html)"[^>]*>', h):
            win = h[max(0, m.start() - 200):m.end() + 700]
            title = ""
            mm = re.search(r'<h4 class="title[^"]*">\s*<a[^>]*>([^<]{2,80})</a>', win)
            if mm:
                title = _clean(mm.group(1))
            if not title:
                mm = re.search(r'title="([^"]{2,80})"', win)
                title = _clean(mm.group(1)) if mm else ""
            pic = ""
            mm = re.search(r'data-original="([^"]+)"', win) or re.search(r'src="([^"]+\.(?:jpg|png|webp))"', win)
            if mm:
                pic = mm.group(1)
            items.append({"vod_id": m.group(2), "vod_name": title or m.group(2), "vod_pic": pic, "vod_remarks": ""})
        return _dedup(items), (page + 1 if len(items) >= 15 else page)

    def detail(self, s, vid):
        url = "%s/v5/%s-1-1.html" % (self.base, vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        name = _clean((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]).split("-")[0]
        pic = ""
        m = re.search(r'data-original="([^"]+\.(?:jpg|png|webp))"', h)
        if m:
            pic = m.group(1)
        v = _vod(vid, name, pic, "", "")
        v["vod_play_from"] = "黄色仓库"
        v["vod_play_url"] = "正片$%s" % vid
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        vid = str(vid).split("$")[0]
        page = "%s/v5/%s-1-1.html" % (self.base, vid)
        try:
            h = s.get(page)
        except Exception:
            return None
        ak = re.search(r"AK='([^']+)'", h)
        if not ak:
            m = re.search(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)', h)
            return (_html.unescape(m.group(1)), {"User-Agent": UA_MOB, "Referer": page}) if m else None
        body = ("id=%s&sid=1&nid=1&tk=%s&g=1&x=300&y=400&dt=900&sw=412&sh=915&tz=-480&t=%d"
                % (vid, ak.group(1), int(time.time() * 1000)))
        try:
            txt = s.post(self.base + "/static/count.php", body, referer=page,
                         headers={"X-Requested-With": "XMLHttpRequest"})
            j = json.loads(txt)
            if j.get("u"):
                u = base64.b64decode(j["u"]).decode("utf-8", "ignore")
                if u:
                    return u, {"User-Agent": UA_MOB, "Referer": page}
        except Exception:
            pass
        return None

    def search(self, s, kw, page=1):
        try:
            h = s.get(self.base + "/v5/search.html?wd=" + urllib.parse.quote(kw))
        except Exception:
            return []
        return mac_search_simple(h, kw, self.base)


class JavboboSite(Site):
    """JavBobo：播放页内嵌 temLineList，file 字段去掉前 3 位后 base64 = 直链。"""
    id = "javbobo"
    name = "JavBobo"
    base = "https://javbobo.com"

    def cats(self, s):
        try:
            h = s.get(self.base + "/")
            cs, seen = [], set()
            for m in re.finditer(r'href="/vod/player\.html\?cate_id=0&(?:amp;)?type_id=(\d+)"', h):
                pass
            for m in re.finditer(r'href="[^"]*(?:type_id|id)=(\d+)"[^>]*>([^<]{1,12})<', h):
                nm = _clean(m.group(2))
                if nm and nm not in seen and len(nm) <= 8:
                    seen.add(nm)
                    cs.append({"n": nm, "v": m.group(1)})
            if cs:
                return cs
        except Exception:
            pass
        return [{"n": "最新", "v": "0"}]

    def listing(self, s, cat, page):
        url = "%s/vod/index.html?type_id=%s&page=%s" % (self.base, cat or "47", page)
        try:
            h = s.get(url, referer=self.base + "/")
        except Exception:
            return [], 1
        items = []
        for m in re.finditer(r'<a[^>]+href="(/vod/player\.html\?cate_id=0&(?:amp;)?id=(\d+)[^"]*)"[^>]*>', h):
            atag = m.group(0)
            win = h[m.start():min(len(h), m.end() + 600)]
            title = ""
            mm = re.search(r'title="([^"]{2,90})"', atag) or re.search(r'alt="([^"]{2,90})"', win)
            if mm:
                title = _clean(mm.group(1))
            pic = ""
            mm = re.search(r'(?:data-src|data-original|src)="([^"]+\.(?:jpg|png|webp))"', win)
            if mm:
                pic = _abs(self.base, mm.group(1))
            items.append({"vod_id": m.group(2), "vod_name": title or m.group(2), "vod_pic": pic, "vod_remarks": ""})
        if not items:
            try:
                h = s.get(self.base + "/")
                for m in re.finditer(r'href="(/vod/player\.html\?cate_id=0&(?:amp;)?id=(\d+)[^"]*)"', h):
                    win = h[max(0, m.start() - 300):m.end() + 300]
                    mm = re.search(r'title="([^"]{2,80})"', win) or re.search(r'alt="([^"]{2,80})"', win)
                    items.append({"vod_id": m.group(2), "vod_name": _clean(mm.group(1)) if mm else m.group(2),
                                  "vod_pic": "", "vod_remarks": ""})
            except Exception:
                pass
        return _dedup(items), (page + 1 if len(items) >= 10 else page)

    def detail(self, s, vid):
        url = "%s/vod/player.html?cate_id=0&id=%s&type_id=49" % (self.base, vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        name = _clean((re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S) or [None, ""])[1])
        if not name:
            name = _clean((re.search(r'<meta property="og:title" content="([^"]*)"', h) or [None, ""])[1])
        if not name:
            name = _clean((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]).split("-")[0]
        name = re.sub(r"^JavBobo[.a-z]*\s*[-|]\s*", "", name)
        pic = ""
        m = re.search(r'(?:og:image" content="|data-src=")([^"]+\.(?:jpg|png|webp))', h)
        if m:
            pic = _abs(self.base, m.group(1))
        v = _vod(vid, name, pic, "", "")
        v["vod_play_from"] = "JavBobo"
        v["vod_play_url"] = "正片$%s" % vid
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        vid = str(vid).split("$")[0]
        url = "%s/vod/player.html?cate_id=0&id=%s&type_id=49" % (self.base, vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        m = re.search(r'"file"\s*:\s*"([A-Za-z0-9+/=]{20,})"', h)
        if m:
            f = m.group(1)
            try:
                raw = base64.b64decode(f[3:] + "=" * ((4 - len(f[3:]) % 4) % 4)).decode("utf-8", "ignore")
                u = urllib.parse.unquote(raw)
                if u.startswith("http"):
                    return u, {"User-Agent": UA_MOB, "Referer": url}
            except Exception:
                pass
        m = re.search(r"(https?://[^\s\"'<>]+\.(?:m3u8|mp4)[^\s\"'<>]*)", h)
        if m:
            return m.group(1), {"User-Agent": UA_MOB, "Referer": url}
        return None

    def search(self, s, kw, page=1):
        try:
            h = s.get(self.base + "/vod/search.html?wd=" + urllib.parse.quote(kw))
        except Exception:
            return []
        return mac_search_simple(h, kw, self.base)


class Rb91Site(Site):
    """91热爆：视频源在 /embed/<id> 的 JS 里（video_url）。"""
    id = "rb91"
    name = "91热爆"
    base = "https://www.91rb.net"

    def cats(self, s):
        return [{"n": "最新", "v": "latest-updates"}, {"n": "热门", "v": "most-popular"},
                {"n": "国产自拍", "v": "1"}, {"n": "日本", "v": "2"}]

    def listing(self, s, cat, page):
        url = "%s/%s/%s/" % (self.base, cat or "latest-updates", page)
        try:
            h = s.get(url, referer=self.base + "/")
        except Exception:
            return [], 1
        items = []
        for m in re.finditer(r'href="(https://www\.91rb\.net/videos/(\d+)/([a-z0-9]+)/)"', h):
            win = h[max(0, m.start() - 600):m.end() + 400]
            title = ""
            mm = re.search(r'title="([^"]{2,90})"', win)
            if mm:
                title = _clean(mm.group(1))
            if not title:
                mm = re.search(r'<img[^>]+alt="([^"]{2,90})"', win)
                title = _clean(mm.group(1)) if mm else ""
            pic = ""
            mm = re.search(r'(?:data-original|data-src|src)="([^"]+\.(?:jpg|jpeg|webp|png)[^"]*)"', win)
            if mm:
                pic = _abs(self.base, mm.group(1))
            items.append({"vod_id": "%s|%s" % (m.group(2), m.group(3)),
                          "vod_name": title or m.group(2), "vod_pic": pic, "vod_remarks": ""})
        return _dedup(items), (page + 1 if len(items) >= 10 else page)

    def _page_url(self, vid):
        if "|" in str(vid):
            a, b = str(vid).split("|", 1)
            return "%s/videos/%s/%s/" % (self.base, a, b), a
        return "%s/videos/%s/" % (self.base, vid), str(vid)

    def detail(self, s, vid):
        url, nid = self._page_url(vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        name = _clean((re.search(r'<meta property="og:title" content="([^"]*)"', h) or [None, ""])[1])
        if not name:
            name = _clean((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1])
        pic = ""
        m = re.search(r'<meta property="og:image" content="([^"]+)"', h)
        if m:
            pic = m.group(1)
        desc = _clean((re.search(r'<meta property="og:description" content="([^"]*)"', h) or [None, ""])[1])
        v = _vod(vid, name, pic, "", desc)
        v["vod_play_from"] = "91热爆"
        v["vod_play_url"] = "正片$%s" % vid
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        url, nid = self._page_url(vid)
        try:
            s.get(url)  # 建立会话
            e = s.get("%s/embed/%s" % (self.base, nid), referer=url)
        except Exception:
            return None
        m = re.search(r"video_url:\s*'([^']+)'", e) or re.search(r'video_url:\s*"([^"]+)"', e)
        if m:
            return _html.unescape(m.group(1)), {
                "User-Agent": UA_MOB,
                "Referer": "%s/embed/%s" % (self.base, nid),
                "Cookie": s.cookie_str(),
            }
        m = re.search(r'<source[^>]+src="([^"]+\.(?:mp4|m3u8)[^"]*)"', e)
        if m:
            return m.group(1), {"User-Agent": UA_MOB, "Referer": url}
        return None

    def search(self, s, kw, page=1):
        try:
            h = s.get(self.base + "/search/" + urllib.parse.quote(kw) + "/")
        except Exception:
            return []
        items = []
        skip = ("添加到收藏夹", "收藏", "加入收藏", "登录", "注册", "更多", "下一页", "上一页")
        for m in re.finditer(r'href="(https://www\.91rb\.net/videos/(\d+)/([a-z0-9]+)/)"', h):
            win = h[m.start():min(len(h), m.end() + 900)]
            mm = re.search(r'title="([^"]{2,90})"', win) or re.search(r'alt="([^"]{2,90})"', win)
            if not mm:
                mm = re.search(r'<img[^>]+title="([^"]{2,90})"', win)
            if not mm:
                continue
            title = _clean(mm.group(1))
            if not title or title in skip or len(title) < 4:
                continue
            items.append({"vod_id": "%s|%s" % (m.group(2), m.group(3)),
                          "vod_name": title, "vod_pic": "", "vod_remarks": ""})
        return _dedup(items)


class PornhubSite(Site):
    """PornHub：详情页 flashvars 里有 mediaDefinitions，取最高清晰度 m3u8。"""
    id = "pornhub"
    name = "PornHub"
    base = "https://www.pornhub.com"

    def cats(self, s):
        return [{"n": "热门", "v": "hot"}, {"n": "最新", "v": "new"}, {"n": "最佳", "v": "top"}]

    def listing(self, s, cat, page):
        cat = cat or "hot"
        url = "%s/video?o=%s&page=%s" % (self.base, {"hot": "ht", "new": "cm", "top": "tr"}.get(cat, "ht"), page)
        try:
            h = s.get(url)
        except Exception:
            return [], 1
        items = []
        for m in re.finditer(r'<a[^>]+href="(/view_video\.php\?viewkey=([a-z0-9]+)[^"]*)"[^>]*>', h):
            atag = m.group(0)
            win = h[m.start():min(len(h), m.end() + 700)]
            title = ""
            mm = re.search(r'title="([^"]{2,120})"', atag) or re.search(r'<img[^>]+alt="([^"]{2,120})"', win)
            if mm:
                title = _clean(mm.group(1))
            pic = ""
            mm = re.search(r'data-image="([^"]+)"', win) or re.search(r'src="(https://[^"]+\.(?:jpg|webp))"', win)
            if mm:
                pic = mm.group(1)
            items.append({"vod_id": m.group(2), "vod_name": title or m.group(2), "vod_pic": pic, "vod_remarks": ""})
        return _dedup(items), (page + 1 if len(items) >= 15 else page)

    def detail(self, s, vid):
        url = "%s/view_video.php?viewkey=%s" % (self.base, vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        name = _clean((re.search(r'<meta property="og:title" content="([^"]*)"', h) or [None, ""])[1])
        pic = ""
        m = re.search(r'<meta property="og:image" content="([^"]+)"', h)
        if m:
            pic = m.group(1)
        v = _vod(vid, name, pic, "", "")
        v["vod_play_from"] = "PornHub"
        v["vod_play_url"] = "正片$%s" % vid
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        vid = str(vid).split("$")[0]
        url = "%s/view_video.php?viewkey=%s" % (self.base, vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        urls = []
        for m in re.finditer(r'"videoUrl"\s*:\s*"([^"]+)"', h):
            u = _unesc(m.group(1))
            if "m3u8" in u or ".mp4" in u:
                urls.append(u)
        if urls:
            return urls[0], {"User-Agent": UA_PC, "Referer": self.base + "/"}
        m = re.search(r'(https?://[^\s"\'<>]+master\.m3u8[^\s"\'<>]*)', h)
        if m:
            return _unesc(m.group(1)), {"User-Agent": UA_PC, "Referer": self.base + "/"}
        return None

    def search(self, s, kw, page=1):
        try:
            h = s.get(self.base + "/video/search?search=" + urllib.parse.quote(kw) + "&page=%s" % page)
        except Exception:
            return []
        items = []
        for m in re.finditer(r'<a[^>]+href="(/view_video\.php\?viewkey=([a-z0-9]+)[^"]*)"[^>]*>', h):
            mm = re.search(r'title="([^"]{2,120})"', m.group(0))
            items.append({"vod_id": m.group(2), "vod_name": _clean(mm.group(1)) if mm else m.group(2),
                          "vod_pic": "", "vod_remarks": ""})
        return _dedup(items)


class JavdbSite(Site):
    """JavDB：只有磁力（magnet），没有 HTTP 直链。"""
    id = "javdb"
    name = "JavDB"
    base = "https://javdb.com"

    def cats(self, s):
        return [{"n": "有码", "v": "censored"}, {"n": "无码", "v": "uncensored"},
                {"n": "欧美", "v": "western"}, {"n": "动画", "v": "anime"}]

    def listing(self, s, cat, page):
        cat = cat or "censored"
        url = "%s/%s?page=%s" % (self.base, cat, page)
        try:
            h = s.get(url)
        except Exception:
            return [], 1
        items = []
        for m in re.finditer(r'<a[^>]+href="/v/([A-Za-z0-9]+)"[^>]*class="box"[^>]*>', h):
            atag = m.group(0)
            win = h[m.start():min(len(h), m.end() + 800)]
            title = ""
            mm = re.search(r'title="([^"]{2,90})"', atag)
            if mm:
                title = _clean(mm.group(1))
            if not title:
                mm = re.search(r'class="video-title"[^>]*>(.*?)</div>', win, re.S)
                title = _clean(mm.group(1)) if mm else ""
            pic = ""
            mm = re.search(r'(?:data-src|src)="([^"]+\.(?:jpg|webp|png)[^"]*)"', win)
            if mm:
                pic = _abs(self.base, mm.group(1))
            items.append({"vod_id": m.group(1), "vod_name": title or m.group(1), "vod_pic": pic,
                          "vod_remarks": ""})
        return _dedup(items), (page + 1 if len(items) >= 20 else page)

    def detail(self, s, vid):
        url = "%s/v/%s" % (self.base, vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        name = _clean((re.search(r'<h2[^>]*class="title[^"]*"[^>]*>\s*<strong>([^<]+)</strong>', h) or [None, ""])[1])
        if not name:
            name = _clean((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]).split("|")[0]
        pic = ""
        m = re.search(r'<meta property="og:image" content="([^"]+)"', h)
        if m:
            pic = m.group(1)
        mags = re.findall(r'href="(magnet:\?xt=[^"]+)"', h)
        mang = ""
        if mags:
            mang = "#".join("磁力%d$%s" % (i + 1, _html.unescape(u)) for i, u in enumerate(mags[:5]))
        v = _vod(vid, name, pic, "磁力" if mags else "", "")
        v["vod_play_from"] = "磁力" if mags else ""
        v["vod_play_url"] = mang
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        vid2 = str(vid).split("$")[0]
        if vid2.startswith("magnet:"):
            return vid2, {"User-Agent": UA_MOB}
        return None

    def search(self, s, kw, page=1):
        try:
            h = s.get(self.base + "/search?q=" + urllib.parse.quote(kw) + "&f=all")
        except Exception:
            return []
        items = []
        for m in re.finditer(r'href="(/v/([A-Za-z0-9]+))"[^>]*>(.*?)</a>', h, re.S):
            win = h[max(0, m.start() - 400):m.end() + 300]
            mm = re.search(r'class="video-title"[^>]*>\s*([^<]{2,90})<', win) or re.search(r'title="([^"]{2,90})"', win)
            items.append({"vod_id": m.group(2), "vod_name": _clean(mm.group(1)) if mm else m.group(2),
                          "vod_pic": "", "vod_remarks": ""})
        return _dedup(items)


class JavbusSite(Site):
    """JavBus：磁力站，页面有 driver-verify 反爬，需要重试刷 cookie。"""
    id = "javbus"
    name = "JavBus"
    base = "https://www.javbus.com"

    def _get(self, s, url, referer=None):
        for _ in range(3):
            try:
                h = s.get(url, referer=referer or self.base + "/", headers={"User-Agent": UA_PC})
                if "driver-verify" not in h:
                    return h
                s.get(self.base + "/", headers={"User-Agent": UA_PC})
            except Exception:
                time.sleep(0.5)
        return ""

    def cats(self, s):
        return [{"n": "有码", "v": "censored"}, {"n": "无码", "v": "uncensored"},
                {"n": "欧美", "v": "western"}]

    def listing(self, s, cat, page):
        cat = cat or ""
        url = "%s/page/%s" % (self.base, page) if not cat or cat == "censored" else "%s/%s/%s" % (self.base, cat, page)
        h = self._get(s, url)
        items = []
        for m in re.finditer(r'<a class="movie-box" href="([^"]+)"', h):
            url2 = m.group(1)
            win = h[m.start():min(len(h), m.start() + 1200)]
            title = ""
            mm = re.search(r'<img[^>]+title="([^"]{2,90})"', win)
            if mm:
                title = _clean(mm.group(1))
            if not title:
                mm = re.search(r'<div class="photo-info">\s*<span>([^<]{2,90})', win)
                title = _clean(mm.group(1)) if mm else ""
            pic = ""
            mm = re.search(r'<img[^>]+src="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', win)
            if mm:
                pic = _abs(self.base, mm.group(1))
            date = ""
            mm = re.search(r'<span class="date">([^<]*)</span>', win)
            if mm:
                date = _clean(mm.group(1))
            vid = url2.rstrip("/").split("/")[-1]
            items.append({"vod_id": vid, "vod_name": title or vid, "vod_pic": pic,
                          "vod_remarks": date})
        return _dedup(items), (page + 1 if len(items) >= 20 else page)

    def detail(self, s, vid):
        url = "%s/v/%s" % (self.base, vid)
        try:
            h = s.get(url)
        except Exception:
            return None
        name = _clean((re.search(r'<h2[^>]*class="title[^"]*"[^>]*>\s*<strong>([^<]+)</strong>', h) or [None, ""])[1])
        if not name:
            name = _clean((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]).split("|")[0]
        pic = ""
        m = re.search(r'<meta property="og:image" content="([^"]+)"', h)
        if m:
            pic = m.group(1)
        mags = re.findall(r'href="(magnet:\?xt=[^"]+)"', h)
        mang = ""
        if mags:
            mang = "#".join("磁力%d$%s" % (i + 1, _html.unescape(u)) for i, u in enumerate(mags[:5]))
        v = _vod(vid, name, pic, "磁力" if mags else "", "")
        v["vod_play_from"] = "磁力" if mags else ""
        v["vod_play_url"] = mang
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        vid2 = str(vid).split("$")[0]
        if vid2.startswith("magnet:"):
            return vid2, {"User-Agent": UA_MOB}
        return None

    def search(self, s, kw, page=1):
        try:
            h = s.get(self.base + "/search?q=" + urllib.parse.quote(kw) + "&f=all")
        except Exception:
            return []
        items = []
        for m in re.finditer(r'href="(/v/([A-Za-z0-9]+))"[^>]*>(.*?)</a>', h, re.S):
            win = h[max(0, m.start() - 400):m.end() + 300]
            mm = re.search(r'class="video-title"[^>]*>\s*([^<]{2,90})<', win) or re.search(r'title="([^"]{2,90})"', win)
            items.append({"vod_id": m.group(2), "vod_name": _clean(mm.group(1)) if mm else m.group(2),
                          "vod_pic": "", "vod_remarks": ""})
        return _dedup(items)

    def detail(self, s, vid):
        url = "%s/%s" % (self.base, vid)
        h = self._get(s, url)
        if not h:
            return None
        name = _clean((re.search(r'<h3>\s*([^<]+)</h3>', h) or [None, ""])[1])
        pic = ""
        m = re.search(r'<a class="bigImage" href="([^"]+)"', h)
        if m:
            pic = m.group(1)
        mags = re.findall(r'href="(magnet:\?xt=[^"]+)"', h)
        mang = "#".join("磁力%d$%s" % (i + 1, _html.unescape(u)) for i, u in enumerate(mags[:5]))
        v = _vod(vid, name or vid, pic, "磁力%d" % len(mags) if mags else "", "")
        v["vod_play_from"] = "磁力" if mags else ""
        v["vod_play_url"] = mang
        v["_detail_url"] = url
        return v

    def play(self, s, vid, flag=""):
        v = str(vid)
        if v.startswith("magnet:"):
            return v, {"User-Agent": UA_PC}
        return None

    def search(self, s, kw, page=1):
        h = self._get(s, "%s/search/%s/%s" % (self.base, urllib.parse.quote(kw), page))
        items = []
        for m in re.finditer(r'<a class="movie-box" href="([^"]+)"', h):
            vid = m.group(1).rstrip("/").split("/")[-1]
            items.append({"vod_id": vid, "vod_name": vid, "vod_pic": "", "vod_remarks": ""})
        return _dedup(items)


def mac_search_simple(h, kw, base):
    items = []
    for m in re.finditer(r'href="([^"]*(?:vod/detail|voddetail|vodplay)[^"]*?(\d+)[^"]*\.html[^"]*)"[^>]*>(.*?)</a>', h, re.S):
        win = h[max(0, m.start() - 300):m.end() + 400]
        title = ""
        mm = re.search(r'title="([^"]{2,80})"', win) or re.search(r'alt="([^"]{2,80})"', win)
        if mm:
            title = _clean(mm.group(1))
        if not title:
            title = _clean(m.group(3))
        if not title or (kw and kw not in title):
            continue
        pic = ""
        mm = re.search(r'(?:data-original|data-src|src)="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', win)
        if mm:
            pic = _abs(base, mm.group(1))
        items.append({"vod_id": m.group(2), "vod_name": title, "vod_pic": pic, "vod_remarks": ""})
        if len(items) >= 40:
            break
    return _dedup(items)


# ---------------------------------------------------------------------------
# 站点清单
# ---------------------------------------------------------------------------
SITES = [
    XyxssSite(), WeimeiSite(), ToptvSite(), GuochangSite(), LlspSite(), YeseSite(),
    ChaoduanjuSite(), HsexSite(), HsckSite(), JavboboSite(), Rb91Site(),
    PornhubSite(), LujjSite(), JavdbSite(), JavbusSite(),
]
SITE_MAP = dict((s.id, s) for s in SITES)



class Spider(BaseSpider):
    """壳入口。tid 约定：<站id>  或  <站id>~<站内分类>；ids 约定：<站id>@<站内id>"""

    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self._cats = {}
        self._lock = None

    def getName(self):
        return "绿果鉴·瑟瑟"

    def init(self, extend=""):
        # 壳可能传 dict / str / list / None，一律不参与逻辑，避免作用域坑
        if not hasattr(self, "_cats") or self._cats is None:
            self._cats = {}
        return None

    # ---- 内部 ----
    def _sess(self, site):
        return sess(site.id)

    def _cats_of(self, site):
        if site.id in self._cats:
            return self._cats[site.id]
        try:
            cs = site.cats(self._sess(site)) or []
        except Exception:
            cs = []
        if not cs:
            cs = [{"n": "全部", "v": "1"}]
        self._cats[site.id] = cs
        return cs

    # ---- 首页 ----
    def homeContent(self, filter=False):
        classes = []
        filters = {}
        for s in SITES:
            classes.append({"type_id": s.id, "type_name": s.name})
            cs = self._cats_of(s)
            if len(cs) > 1:
                filters[s.id] = [{"key": "cat", "name": "分类", "value": cs}]
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    # ---- 分类 ----
    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg or 1)
        tid = str(tid or "")
        sid, cat = tid, ""
        if "~" in tid:
            sid, cat = tid.split("~", 1)
        ext = extend or {}
        if isinstance(ext, dict):
            cat = ext.get("cat") or cat
        site = SITE_MAP.get(sid)
        if not site:
            return {"list": [], "page": pg, "pagecount": pg, "limit": 20, "total": 0}
        if not cat:
            cs = self._cats_of(site)
            cat = cs[0]["v"] if cs else "1"
        try:
            items, pc = site.listing(self._sess(site), cat, pg)
        except Exception as e:
            log("category", site.id, "err", e)
            items, pc = [], pg
        out = []
        for it in items:
            it2 = dict(it)
            it2["vod_id"] = "%s@%s" % (site.id, it.get("vod_id"))
            try:
                _CACHE[it2["vod_id"]] = dict(it)
            except Exception:
                pass
            if not it2.get("vod_remarks"):
                it2["vod_remarks"] = site.name
            out.append(it2)
        return {"list": out, "page": pg, "pagecount": max(pc, pg), "limit": 20, "total": len(out)}

    # ---- 详情 ----
    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else ids
        sid, _, vid = str(raw).partition("@")
        site = SITE_MAP.get(sid)
        if not site:
            return {"list": []}
        try:
            v = site.detail(self._sess(site), vid)
        except Exception as e:
            log("detail", sid, "err", e)
            v = None
        if not v:
            cached = _CACHE.get(raw)
            if not cached:
                return {"list": []}
            v = _vod(vid, cached.get("vod_name") or vid, cached.get("vod_pic") or "",
                     cached.get("vod_remarks") or "", "")
            v["vod_play_from"] = site.name
            v["vod_play_url"] = "正片$%s" % vid
        # 播放地址统一加站前缀
        pf = v.get("vod_play_from") or ""
        pu = v.get("vod_play_url") or ""
        if pu:
            parts = []
            for grp in pu.split("#"):
                if "$" in grp:
                    nm, u = grp.split("$", 1)
                    parts.append("%s$%s@%s@%s" % (nm, sid, u, pf))
                else:
                    parts.append(grp)
            v["vod_play_url"] = "#".join(parts)
        v["vod_id"] = raw
        return {"list": [v]}

    # ---- 搜索 ----
    def searchContent(self, key, quick=False, pg=1):
        pg = int(pg or 1)
        key = (key or "").strip()
        if not key:
            return {"list": []}
        results = []
        from concurrent.futures import ThreadPoolExecutor, as_completed
        def one(site):
            try:
                return site.id, site.search(self._sess(site), key, pg) or []
            except Exception:
                return site.id, []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(one, s) for s in SITES]
            for f in as_completed(futs, timeout=40):
                try:
                    sid, items = f.result()
                except Exception:
                    continue
                site = SITE_MAP.get(sid)
                for it in items[:20]:
                    it2 = dict(it)
                    it2["vod_id"] = "%s@%s" % (sid, it.get("vod_id"))
                    it2["vod_name"] = "[%s] %s" % (site.name, it.get("vod_name") or "")
                    results.append(it2)
        return {"list": results[:200]}

    # ---- 播放 ----
    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "")
        parts = raw.split("@")
        if len(parts) < 2:
            return {"parse": 0, "playUrl": "", "url": "", "header": ""}
        sid, vid = parts[0], parts[1]
        site = SITE_MAP.get(sid)
        if not site:
            return {"parse": 0, "playUrl": "", "url": "", "header": ""}
        try:
            if str(vid).startswith("http"):
                r = find_play_url(self._sess(site), site.base, vid, "")
            else:
                r = site.play(self._sess(site), vid, flag)
        except Exception as e:
            log("play", sid, "err", e)
            r = None
        if not r:
            return {"parse": 0, "playUrl": "", "url": "", "header": ""}
        u, hdrs = r
        # 磁力交给壳/外部播放器
        if str(u).startswith("magnet:"):
            return {"parse": 0, "playUrl": "", "url": u, "header": {"User-Agent": UA_MOB}}
        return {"parse": 0, "playUrl": "", "url": u, "header": hdrs or {"User-Agent": UA_MOB}}


# 兼容：有的壳按模块名找类，有的按固定别名
Spider = Spider
