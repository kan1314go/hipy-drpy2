# coding=utf-8
"""
TrendyPorn TVBox / 影视仓 / kus Python 源

链路：homeContent(分类) -> categoryContent(列表) -> detailContent(详情) -> playerContent(直链 mp4)
要点：
1. 列表页每条视频是 <div id="vid-183780"> ... </div>，内含 video/*.html 详情链接、封面、时长。
2. 详情页 <source src="https://videos.trendyporn.com/videos/....mp4?md5=...&expires=...">，
   md5+expires 签名约一年有效，所以 playerContent 每次重新抓详情页，保证永远拿到可用地址。
3. 翻页统一是 <列表地址>pageN.html，不需要额外的表单。
"""

import re
import html
import urllib.parse

try:
    import requests
except Exception:
    requests = None

BASE = "https://www.trendyporn.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# 分类：type_id 直接就是站内路径，翻页时拼 pageN.html
CATS = [
    ("最新更新", "most-recent"),
    ("最高评分", "top-rated"),
    ("最多观看", "most-viewed"),
    ("时长最长", "longest"),
    ("Amateur 业余", "channels/2/amateur"),
    ("Anal 肛交", "channels/3/anal"),
    ("Asian 亚洲", "channels/1/asian"),
    ("Ass 屁股", "channels/4/ass"),
    ("BBW 肉感", "channels/5/bbw"),
    ("BDSM", "channels/6/bdsm"),
    ("Blonde 金发", "channels/7/blonde"),
    ("Blowjobs 口交", "channels/8/blowjobs"),
    ("British 英伦", "channels/9/british"),
    ("Chinese 国产", "channels/13/chinese"),
    ("Creampie 内射", "channels/14/close-ups"),
    ("Ebony 黑人", "channels/17/ebony"),
    ("Gangbang 群交", "channels/20/gangbang"),
    ("Gay 男同", "channels/21/gay"),
    ("Hardcore 硬核", "channels/25/hardcore"),
    ("HD 高清", "channels/26/hd"),
    ("Hentai 里番", "channels/27/hentai"),
    ("Home Made 自拍", "channels/28/home-made"),
    ("Indian 印度", "channels/29/indian"),
    ("Interracial 跨种族", "channels/30/interracial"),
    ("Japanese 日本", "channels/31/japanese"),
    ("Korean 韩国", "channels/48/korean"),
    ("Lesbians 女同", "channels/33/lesbians"),
    ("Massage 按摩", "channels/34/massage"),
    ("MILF 熟女", "channels/35/milf"),
    ("Pornstars 女优", "channels/54/pornstars"),
    ("POV 主观", "channels/55/pov"),
    ("Public 户外", "channels/37/public"),
    ("Shemale 人妖", "channels/42/toys"),
    ("Teen 少女", "channels/40/teen"),
    ("Tits 美胸", "channels/41/tits"),
    ("Vintage 复古", "channels/43/vintage"),
    ("Wife 人妻", "channels/45/wife"),
]

RE_HREF = re.compile(r'href="(https?://[^"]*?/video/[^"]+?\.html)"')
RE_TITLE = re.compile(r'title="([^"]+)"')
RE_PIC = re.compile(r'data-original="([^"]+)"')
RE_SRC = re.compile(r'\ssrc="([^"]+)"')
RE_DUR = re.compile(r'<div class="duration">\s*([^<]+?)\s*</div>')
RE_MP4 = re.compile(r'https?://videos\.trendyporn\.com/[^\s"\'<>]+')
RE_MAXPG = re.compile(r'page(\d+)\.html')


def _headers(referer=BASE):
    return {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        "Referer": referer,
        "Connection": "keep-alive",
    }


def _get(url, referer=BASE):
    """抓页面，失败重试一次，最终返回空串而不是抛异常。"""
    if requests is None:
        return ""
    for _ in range(2):
        try:
            r = requests.get(url, headers=_headers(referer), timeout=15, verify=False)
            if r.status_code == 200 and r.text:
                if not r.encoding or r.encoding.lower() == "iso-8859-1":
                    r.encoding = "utf-8"
                return r.text
        except Exception:
            pass
    return ""


def _clean(s):
    return html.unescape(re.sub(r"\s+", " ", (s or ""))).strip()


def _parse_list(text):
    """从列表页抽视频，按 vid- 块切分，逐块取链接/标题/封面/时长。"""
    out, seen = [], set()
    if not text:
        return out
    for chunk in re.split(r'<div id="vid-', text)[1:]:
        vid = re.match(r"(\d+)", chunk)
        href = RE_HREF.search(chunk)
        if not (vid and href):
            continue
        url = href.group(1)
        if url in seen:
            continue
        seen.add(url)

        title = ""
        t = RE_TITLE.search(chunk)
        if t:
            title = _clean(t.group(1))
        if not title:
            continue

        pic = ""
        p = RE_PIC.search(chunk)
        if p:
            pic = p.group(1)
        else:
            s = RE_SRC.search(chunk)
            if s and "placeholder" not in s.group(1):
                pic = s.group(1)

        d = RE_DUR.search(chunk)
        out.append({
            "vod_id": url,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": _clean(d.group(1)) if d else "HD",
        })
    return out


def _page_url(tid, pg):
    pg = max(1, int(pg or 1))
    base = "%s/%s/" % (BASE, tid.strip("/"))
    return base if pg == 1 else base + "page%d.html" % pg


def _max_page(text, pg):
    nums = [int(x) for x in RE_MAXPG.findall(text or "")]
    return max(nums + [int(pg or 1)])


class Spider:
    def __init__(self):
        self.extend = ""
        self.sess = requests.Session() if requests else None

    # ---------- 基础信息 ----------
    def getName(self):
        return "TrendyPorn"

    def init(self, extend=""):
        self.extend = extend or ""
        try:
            requests.packages.urllib3.disable_warnings()
        except Exception:
            pass

    def isVideoFormat(self, url):
        return bool(url) and (".mp4" in url or ".m3u8" in url)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            if self.sess:
                self.sess.close()
        except Exception:
            pass

    # ---------- 首页 / 分类 ----------
    def homeContent(self, filter):
        return {"class": [{"type_id": tid, "type_name": name} for name, tid in CATS]}

    def homeVideoContent(self):
        return {"list": _parse_list(_get(BASE + "/"))}

    def categoryContent(self, tid, pg, filter, extend):
        pg = max(1, int(pg or 1))
        text = _get(_page_url(tid, pg))
        return {
            "list": _parse_list(text),
            "page": pg,
            "pagecount": _max_page(text, pg),
            "limit": 30,
            "total": 9999,
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        url = ids[0] if ids else ""
        if url and not url.startswith("http"):
            url = BASE + "/" + url.lstrip("/")
        text = _get(url)

        name = ""
        m = re.search(r'<meta property="og:title" content="([^"]*)"', text)
        if m:
            name = _clean(m.group(1))
        if not name:
            m = re.search(r"<title>([^<]+)</title>", text)
            name = _clean(m.group(1)).split(" - Videos")[0] if m else "未知标题"

        pic = ""
        m = re.search(r'<meta property="og:image" content="([^"]*)"', text)
        if m:
            pic = m.group(1)

        dur = ""
        m = re.search(r"Runtime:\s*<span>([^<]+)</span>", text)
        if m:
            dur = _clean(m.group(1))

        tags = [_clean(x) for x in re.findall(r'/tag/[^"]+/?"[^>]*>([^<]+)</a>', text)]
        cats = [_clean(x) for x in re.findall(r'/channels/\d+/[^"]+/?"[^>]*>([^<]+)</a>', text)]
        desc = "时长 %s" % dur if dur else ""
        if tags:
            desc += "\n标签: " + ", ".join(tags[:12])
        if cats:
            desc += "\n分类: " + ", ".join(cats[:8])
        desc += "\n来源: trendyporn.com"

        play = self._resolve(url, text) or url

        return {"list": [{
            "vod_id": url,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": dur or "HD",
            "vod_content": desc.strip(),
            "vod_play_from": "TrendyPorn",
            "vod_play_url": "正片$" + play,
        }]}

    # ---------- 播放 ----------
    def _resolve(self, page_url, text=None):
        """从详情页取出带 md5/expires 的 mp4 直链。"""
        if page_url and page_url.split("?")[0].endswith(".mp4"):
            return page_url
        if text is None:
            text = _get(page_url)
        m = RE_MP4.search(text or "")
        if not m:
            return ""
        return html.unescape(m.group(0)).replace("&amp;", "&")

    def playerContent(self, flag, id, vipFlags):
        url = id or ""
        if url and not url.startswith("http"):
            url = BASE + "/" + url.lstrip("/")
        play = self._resolve(url)
        if not play:
            return {"parse": 0, "url": url}
        return {
            "parse": 0,
            "url": play,
            "header": {
                "User-Agent": UA,
                "Referer": BASE + "/",
                "Origin": BASE,
            },
        }

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        key = (key or "").strip()
        if not key:
            return {"list": []}
        tid = "search/" + urllib.parse.quote(key)
        return self.categoryContent(tid, pg, False, {})

    # ---------- 其他 ----------
    def liveContent(self, url):
        return {}

    def localProxy(self, params):
        return [404, "text/plain", b""]


class csp_TrendyPorn(Spider):
    """给用 csp_ 类名映射的壳子（官方 TVBox 系）用。"""
    pass