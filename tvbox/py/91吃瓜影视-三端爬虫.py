# coding=utf-8
import base64
import gzip
import hashlib
import json
import os
import random
import re
import ssl
import string
import time
import urllib.parse
import urllib.request
from urllib.parse import urlencode, urlsplit, parse_qs, unquote, quote

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    requests = None
    _HAS_REQUESTS = False

try:
    from base.spider import Spider as _Spider
except Exception:
    class _Spider(object):
        pass

NAME = '91吃瓜影视'
SITE = 'https://www.91cg1.com'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
MOBILE_UA = ('Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36')
TIMEOUT = 20
PAGE_SIZE = 30
HOME_SIZE = 30

GLOBAL_PROXY = 'https://1.h8.ccwu.cc'
COVER_DECRYPT = 'https://2.h8.ccwu.cc/?url='

FALLBACK_CATEGORY_TREE = [
    ('今日吃瓜', [('今日吃瓜', 'zxcghl'), ('必吃大瓜', 'bcdg'), ('体育直播', 'sports-live')]),
    ('吃瓜热门', [('深夜撸片', 'sflyp'), ('网黄合集', 'whhj'), ('每日大赛', 'mrds'),
                  ('91探花', '91th'), ('师生专栏', 'sszl'), ('明星AI', 'mxai')]),
    ('吃瓜百科', [('自拍偷拍', 'zptp'), ('海角乱伦', 'hjln'), ('AI短剧', 'aidj'),
                  ('社会奇闻', 'shqw'), ('乱伦曝光', 'llbg'), ('明星黑料', 'mxhl')]),
    ('51原创', [('原创博主', 'yczq'), ('91剧场', '91jc')]),
]

_RE_ARTICLE = re.compile(r'<article[^>]*itemscope[^>]*>([\s\S]*?)</article>', re.I)
_RE_ARCHIVE_LINK = re.compile(
    r'<meta[^>]+itemprop="url mainEntityOfPage"[^>]+content="[^"]*?/archives/(\d+)/"', re.I)
_RE_ARCHIVE_LINK_ALT = re.compile(r'<a[^>]+href="[^"]*?/archives/(\d+)/"', re.I)
_RE_POST_TITLE = re.compile(r'<h2[^>]*class="post-card-title"[^>]*>([\s\S]*?)</h2>', re.I)
_RE_DATE = re.compile(r'itemprop="datePublished"[^>]*>([\s\S]{0,80}?)<', re.I)
_RE_BANNER = re.compile(r"loadBannerDirect\(\s*'([^']+)'", re.I)
_RE_TAG_STRIP = re.compile(r'<[^>]+>')

_RE_NAV_ITEM = re.compile(
    r'<a\s+href="([^"]*?/category/[^"]+)"[^>]*?(?:title="([^"]*)")?[^>]*>\s*([^<]{1,30}?)\s*</a>', re.I)
_RE_NAV_PLAIN = re.compile(r'<li class="menu-item"><a href="([^"]*)"[^>]*>([^<]{1,30})</a>', re.I)
_RE_NAV_BTN = re.compile(
    r'<button[^>]*dropdown-toggle[^>]*>(?:<div[^>]*>([^<]{1,30})</div>)?([^<]{1,30})?</button>', re.I)

_RE_H1 = re.compile(r'<h1[^>]*class="post-title[^"]*"[^>]*>([\s\S]*?)</h1>', re.I)
_RE_H1_ALT = re.compile(r'<h1[^>]*>([\s\S]*?)</h1>', re.I)
_RE_DPLAYER = re.compile(r'<div[^>]*class="[^"]*dplayer[^"]*"[^>]*data-config=\'([^\']+)\'', re.I)
_RE_DPLAYER_ALT = re.compile(r'data-config="([^"]{40,})"', re.I)
_RE_DATACFG = re.compile(r"data-config='(\{[^']{40,}\})'", re.I)
_RE_OG_IMAGE = re.compile(r'property="og:image"[^>]+content="([^"]+)"', re.I)
_RE_ARTICLE_BODY = re.compile(r'itemprop="articleBody"[^>]*>([\s\S]*)', re.I)
_RE_KEYWORDS = re.compile(r'itemprop="keywords"[^>]*>([\s\S]{0,1500}?)(?:</(?:span|div)>|</p>)', re.I)
_RE_PAGER_CAT = re.compile(r'/category/[^/]+/(\d+)/')
_RE_PAGER_HOME = re.compile(r'href="/page/(\d+)/"')

REALTIME_MAP = {
    'sstp': [('热门推荐', ''), ('实时监控', 'live'), ('精彩回放', 'replay')],
}
REALTIME_CATS = [('实时偷拍', 'sstp')]

_RE_RT_CARD = re.compile(r'class="realtime-card"([\s\S]*?)</a>', re.I)
_RE_RT_HREF = re.compile(r'href="[^"]*?/category/([a-z0-9]+)/video/(\d+)/"', re.I)
_RE_RT_LABEL = re.compile(r'aria-label="([^"]*)"', re.I)
_RE_RT_PIC = re.compile(r'data-xkrkllgl="([^"]*)"', re.I)
_RE_RT_COVER = re.compile(r'realtime-card__cover"[^>]*src="([^"]*)"', re.I)
_RE_RT_STATUS = re.compile(r'realtime-card__status[^>]*>([\s\S]*?)</span>', re.I)

_ENTITIES = (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
             ("&quot;", '"'), ("&#39;", "'"), ("&#x27;", "'"), ("&apos;", "'"))


def _unescape(s):
    s = str(s or "")
    for a, b in _ENTITIES:
        s = s.replace(a, b)
    return re.sub(r'&#(\d{2,6});', lambda m: chr(int(m.group(1))) if int(m.group(1)) < 1114112 else m.group(0), s)


def _strip_tags(s):
    return re.sub(r'\s+', ' ', _RE_TAG_STRIP.sub(' ', str(s or ''))).strip()


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _decode(raw):
    if not raw:
        return ''
    if isinstance(raw, bytes):
        for enc in ('utf-8', 'gb18030'):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode('utf-8', 'ignore')
    return str(raw)


def _clean_name(raw):
    s = re.sub(r'<div class="wrap">[\s\S]*?</div>', ' ', str(raw or ''), flags=re.I)
    s = re.sub(r'<span class="wraps?">[\s\S]*?</span>', ' ', s, flags=re.I)
    s = _strip_tags(_unescape(s))
    return re.sub(r'\s+', ' ', s).strip(' •-—|【】[]')


class Spider(_Spider):
    def __init__(self):
        try:
            _Spider.__init__(self)
        except Exception:
            pass
        self.name = NAME
        self.site = SITE
        self.proxy = GLOBAL_PROXY
        self.cover_decrypt = COVER_DECRYPT
        self._last_req = 0.0
        self._nav = None
        self._cache = {}
        self._tree = [(p, list(kids)) for p, kids in FALLBACK_CATEGORY_TREE]
        self.extend = {}

    def _headers(self, referer=None, image=False):
        hd = {
            'User-Agent': UA,
            'Accept': ('image/avif,image/webp,image/apng,image/*,*/*;q=0.8' if image
                       else 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        if not image:
            hd['Accept-Encoding'] = 'gzip, deflate'
        if referer:
            hd['Referer'] = referer
        return hd

    def _throttle(self):
        gap = time.time() - self._last_req
        if gap < 0.12:
            time.sleep(0.12 - gap)
        self._last_req = time.time()

    def _build_url(self, path):
        if str(path).startswith('http://') or str(path).startswith('https://'):
            return path
        full = self.site + str(path)
        if self.proxy:
            return self.proxy.rstrip('/') + '/' + full
        return full

    def _open(self, url, referer=None, image=False, retry=2):
        last = ''
        for attempt in range(retry + 1):
            self._throttle()
            try:
                req = urllib.request.Request(url, headers=self._headers(referer, image=image))
                with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_ctx()) as resp:
                    raw = resp.read()
                try:
                    if raw[:2] == b'\x1f\x8b':
                        raw = gzip.decompress(raw)
                except Exception:
                    pass
                return raw
            except Exception as exc:
                last = str(exc)[:120]
                time.sleep(0.3)
        return b''

    def _get(self, path, referer=None, ttl=0, binary=False):
        url = self._build_url(path)
        if ttl > 0:
            hit = self._cache.get(url)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
        raw = self._open(url, referer=referer, image=binary)
        if not raw:
            return b'' if binary else ''
        body = raw if binary else _decode(raw)
        if ttl > 0:
            if len(self._cache) > 300:
                self._cache.clear()
            self._cache[url] = (time.time(), body)
        return body

    def _abs(self, url):
        u = str(url or '').strip()
        if not u:
            return ''
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('http://') or u.startswith('https://'):
            return u
        if u.startswith('/'):
            return self.site + u
        return self.site + '/' + u

    def _cover(self, url):
        u = str(url or '').strip()
        if not u:
            return ''
        if self.proxy and u.startswith(self.proxy.rstrip('/') + '/'):
            u = u[len(self.proxy.rstrip('/')) + 1:]
        elif u.startswith(GLOBAL_PROXY + '/'):
            u = u[len(GLOBAL_PROXY) + 1:]
        u = self._abs(u)
        if not u:
            return ''
        if not self.cover_decrypt:
            return u
        return self.cover_decrypt + quote(u, safe='')

    def _proxy_cover(self, url):
        return self._cover(url)

    def _extract_slug(self, href):
        m = re.search(r'/category/([^/]+)/', href)
        return m.group(1) if m else ''

    def _refresh_tree(self, html):
        try:
            i = html.find('<ul id="menu-menu-1"')
            if i < 0:
                return
            j = html.find('</nav>', i)
            seg = html[i:j if j > 0 else len(html)]
        except Exception:
            return
        tree = []
        for m in re.finditer(r'<button[^>]*dropdown-toggle[^>]*>([^<]{1,30})</button>[\s\S]{0,400}?<ul class="dropdown-menu">([\s\S]*?)</ul>', seg):
            parent = m.group(1).strip()
            sub_blk = m.group(2)
            subs = []
            for sm in re.finditer(r'<a\s+href="([^"]*?/category/[^"]+)"[^>]*>\s*([^<]{1,30}?)\s*</a>', sub_blk):
                label = sm.group(2).strip()
                slug = self._extract_slug(sm.group(1))
                if slug and label and (label, slug) not in subs:
                    subs.append((label, slug))
            if parent and subs:
                tree.append((parent, subs))
        seg_nd = re.sub(r'<ul class="dropdown-menu">[\s\S]*?</ul>', '', seg)
        for m in re.finditer(r'<li class="[^"]*menu-item[^"]*"[^>]*>[\s\S]{0,300}?<a\s+href="([^"]*?/category/[^"]+)"[^>]*>\s*([^<]{1,30}?)\s*</a>', seg_nd):
            label = m.group(2).strip()
            slug = self._extract_slug(m.group(1))
            if not slug or not label:
                continue
            if any(any(s[1] == slug for s in subs) for _, subs in tree):
                continue
            tree.append((label, [(label, slug)]))
        if tree:
            self._tree = tree

    def _rt_tabs(self, slug, html):
        out = []
        for name, sub in REALTIME_MAP.get(slug, []):
            out.append({'name': name, 'value': sub})
        return out

    def _parse_realtime(self, html):
        out, seen = [], set()
        if not html:
            return out
        for blk in _RE_RT_CARD.findall(html):
            hm = _RE_RT_HREF.search(blk)
            if not hm:
                continue
            slug, vid = hm.group(1), hm.group(2)
            key = '%s:%s' % (slug, vid)
            if key in seen:
                continue
            seen.add(key)
            lm = _RE_RT_LABEL.search(blk)
            title = _clean_name(lm.group(1)) if lm else ''
            if not title:
                title = '视频 %s' % vid
            pm = _RE_RT_PIC.search(blk) or _RE_RT_COVER.search(blk)
            cover = self._proxy_cover(pm.group(1)) if pm else ''
            sm = _RE_RT_STATUS.search(blk)
            status = _strip_tags(_unescape(sm.group(1))) if sm else ''
            if status == '在线':
                status = '直播中'
            if not status:
                status = '实时偷拍'
            out.append({
                'vod_id': key,
                'vod_name': title[:120],
                'vod_pic': cover,
                'vod_remarks': status[:80],
                'type_name': '',
            })
        return out

    def _parse_list(self, html):
        out, seen = [], set()
        if not html:
            return out
        for blk in _RE_ARTICLE.findall(html):
            m = _RE_ARCHIVE_LINK.search(blk) or _RE_ARCHIVE_LINK_ALT.search(blk)
            if not m:
                continue
            aid = m.group(1)
            if not aid or aid in seen:
                continue
            tm = _RE_POST_TITLE.search(blk)
            name = _clean_name(tm.group(1)) if tm else ''
            if not name:
                continue
            dm = _RE_DATE.search(blk)
            remark = _strip_tags(_unescape(dm.group(1))).strip(' •-') if dm else ''
            bm = _RE_BANNER.search(blk)
            cover = self._proxy_cover(bm.group(1)) if bm else ''
            seen.add(aid)
            out.append({
                'vod_id': aid,
                'vod_name': name[:120],
                'vod_pic': cover,
                'vod_remarks': re.sub(r'\s+', ' ', remark).strip()[:80],
                'type_name': '',
            })
        return out

    def _extract_play(self, html):
        plays = []
        seen = set()
        blocks = _RE_DPLAYER.findall(html) or _RE_DATACFG.findall(html) or _RE_DPLAYER_ALT.findall(html)
        for raw in blocks:
            cfg = None
            try:
                cfg = json.loads(_unescape(raw).replace('\\/', '/'))
            except Exception:
                try:
                    cfg = json.loads(raw.replace('\\/', '/'))
                except Exception:
                    cfg = None
            if not isinstance(cfg, dict):
                m = re.search(r'"url"\s*:\s*"(https?://[^"]+)"', raw)
                if m:
                    cfg = {'video': {'url': m.group(1), 'type': 'hls'}}
                else:
                    continue

            def add(url, name):
                u = str(url or '').strip().replace('\\/', '/')
                if not u.startswith('http') or u in seen:
                    return
                seen.add(u)
                plays.append((name, u))

            for key, label in (('video', '标清'), ('video_h265', 'H265'),
                               ('video_4k', '4K'), ('video_hd', '高清')):
                node = cfg.get(key)
                if isinstance(node, dict):
                    add(node.get('url'), label)
            if not plays:
                for u in re.findall(r'https?://[^"\']+?\.m3u8[^"\']*', raw):
                    add(u, '播放')
        return plays

    def _extract_desc(self, html):
        m = _RE_ARTICLE_BODY.search(html)
        if not m:
            om = re.search(r'property="og:description"[^>]+content="([^"]*)"', html)
            return _strip_tags(_unescape(om.group(1))) if om else ''
        seg = m.group(1)
        for stop in ('id="comments', 'class="post-tags', 'class="post-next',
                     'class="related', 'class="sidebar'):
            i = seg.find(stop)
            if i > 200:
                seg = seg[:i]
        seg = re.sub(r'<div class="txt-apps">[\s\S]*?</div>\s*(?=<)', ' ', seg, flags=re.I)
        seg = re.sub(r'<div class="content-tabs">[\s\S]*?</div>\s*(?=<)', ' ', seg, flags=re.I)
        seg = re.sub(r'<table[\s\S]*?</table>', ' ', seg, flags=re.I)
        seg = re.sub(r'<div class="btn-download">[\s\S]*?</div>', ' ', seg, flags=re.I)
        seg = re.sub(r'<div class="copy-box">[\s\S]*?</div>', ' ', seg, flags=re.I)
        paras = []
        for p in re.findall(r'<p[^>]*>([\s\S]*?)</p>', seg, re.I):
            t = _strip_tags(_unescape(p)).strip()
            if len(t) < 4:
                continue
            if re.match(r'^(下载|分享|热门吃瓜|吃瓜中心|APP|广告)', t):
                continue
            if '永久地址' in t or '广告' in t:
                continue
            paras.append(t)
        desc = ' '.join(paras)
        for cut in ('下载APP观看完整版', '分享好友吃瓜', '关键词：'):
            if cut in desc:
                desc = desc.split(cut)[0]
        return re.sub(r'\s+', ' ', desc).strip()[:1200]

    def _extract_tags(self, html):
        out = []
        m = _RE_KEYWORDS.search(html)
        if m:
            for a in re.findall(r'<a[^>]*>([^<]{1,20})</a>', m.group(1)):
                t = _strip_tags(_unescape(a)).strip()
                if t and t not in out:
                    out.append(t)
        if not out:
            i = html.find('itemprop="keywords"')
            if i > 0:
                km = re.search(r'content="([^"]+)"', html[i:i + 600])
                if km:
                    out = [x.strip() for x in km.group(1).split(',') if x.strip()][:6]
        return out[:8]

    def _detail_meta(self, html):
        tm = _RE_H1.search(html) or _RE_H1_ALT.search(html)
        title = _clean_name(tm.group(1)) if tm else ''
        cover = ''
        im = _RE_OG_IMAGE.search(html)
        if im and 'social-default' not in im.group(1) and '/images/91cg' not in im.group(1):
            cover = self._proxy_cover(im.group(1))
        if not cover:
            cm = re.search(r'"video"\s*:\s*\{[^{}]*?"pic"\s*:\s*"([^"]+)"', html)
            if cm:
                cover = self._proxy_cover(cm.group(1).replace('\\/', '/'))
        if not cover:
            cm2 = re.search(r'data-config=\'[^\']*?"pic"\s*:\s*"([^"]+)"', html)
            if cm2:
                cover = self._proxy_cover(cm2.group(1).replace('\\/', '/'))
        if not cover:
            ik = re.search(r'data-xkrkllgl="(https?://[^"]+)"', html)
            if ik:
                cover = self._proxy_cover(ik.group(1))
        if not cover:
            bm = _RE_BANNER.search(html)
            if bm:
                cover = self._proxy_cover(bm.group(1))
        desc = self._extract_desc(html)
        year = ''
        ym = re.search(r'(19\d{2}|20\d{2})', title)
        if ym:
            year = ym.group(1)
        if not year:
            ym2 = re.search(r'(19\d{2}|20\d{2})', html)
            if ym2:
                year = ym2.group(1)
        return title, cover, desc, year

    def init(self, extend=""):
        cfg = extend
        if isinstance(cfg, str) and cfg.strip():
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {} if not cfg.startswith('http') else {'proxy': cfg}
        if not isinstance(cfg, dict):
            cfg = {}
        self.extend = cfg
        proxy = str(cfg.get('proxy') or '').strip()
        if proxy:
            self.proxy = proxy
        site = str(cfg.get('site') or cfg.get('host') or '').strip().rstrip('/')
        if site:
            if not re.match(r'^https?://', site, re.I):
                site = 'https://' + site
            self.site = site
        cover_dec = str(cfg.get('coverDecrypt') or cfg.get('cover_decrypt') or '').strip()
        if cover_dec:
            self.cover_decrypt = cover_dec
        return self

    def getName(self):
        return NAME

    def getDependence(self):
        return []

    def _classes(self):
        out = [{'type_id': '@home', 'type_name': '首页推荐'}]
        for parent, kids in self._tree:
            kids = [k for k in kids if k[1]]
            if not kids:
                continue
            gid = '@grp:%s' % parent
            out.append({'type_id': gid, 'type_name': parent})
            if not (len(kids) == 1 and kids[0][0] == parent):
                for name, slug in kids:
                    cid = 'cat:%s' % slug
                    out.append({'type_id': cid, 'type_name': name})
        return out

    def _filters(self):
        filters = {'@home': [self._filter_sort()]}
        for parent, kids in self._tree:
            kids = [k for k in kids if k[1]]
            if not kids:
                continue
            gid = '@grp:%s' % parent
            if not (len(kids) == 1 and kids[0][0] == parent):
                filters[gid] = [self._filter_sub(kids)]
                for name, slug in kids:
                    filters['cat:%s' % slug] = []
            else:
                filters[gid] = []
        for name, slug in REALTIME_CATS:
            key = 'cat:%s' % slug
            if key not in filters:
                filters[key] = []
            filters[key] = [self._filter_rt(slug)]
        return filters

    @staticmethod
    def _filter_rt(slug):
        return {'key': 'sub', 'name': '子分类',
                'value': [{'n': n, 'v': v} for n, v in REALTIME_MAP.get(slug, [])]}

    @staticmethod
    def _filter_sub(kids):
        return {'key': 'sub', 'name': '子分类',
                'value': [{'n': '全部', 'v': ''}] + [{'n': n, 'v': s} for n, s in kids]}

    @staticmethod
    def _filter_sort():
        return {'key': 'sort', 'name': '排序',
                'value': [{'n': '最新', 'v': 'new'}, {'n': '热门', 'v': 'hot'}]}

    def homeContent(self, filter=False):
        html = self._get('/', ttl=120)
        if html:
            self._refresh_tree(html)
        return {'class': self._classes(), 'list': [], 'parse': 0, 'jx': 0,
                **({'filters': self._filters()} if filter else {})}

    def homeVideoContent(self):
        try:
            html = self._get('/', ttl=120)
            rows = self._parse_list(html)
            return {'list': rows[:HOME_SIZE], 'page': 1, 'pagecount': 1,
                    'limit': len(rows[:HOME_SIZE]), 'total': len(rows),
                    'totalpage': 1, 'moresort': False, 'parse': 0, 'jx': 0}
        except Exception:
            return {'list': [], 'parse': 0, 'jx': 0}

    def _slug_of(self, tid):
        t = str(tid or '').strip().strip('/')
        if t.startswith('category/'):
            t = t[len('category/'):]
        return t

    def _resolve_tid(self, tid, extend):
        raw = str(tid or '').strip()
        ext = {}
        if isinstance(extend, dict):
            ext = {str(k).strip(): v for k, v in extend.items()}
        elif isinstance(extend, str) and extend.strip():
            try:
                d = json.loads(extend)
                if isinstance(d, dict):
                    ext = {str(k).strip(): v for k, v in d.items()}
            except Exception:
                ext = {}
        if 'extend' in ext and isinstance(ext.get('extend'), dict):
            for k, v in ext['extend'].items():
                ext.setdefault(str(k).strip(), v)
        if raw.startswith('@home'):
            return '', '/'
        slug = raw
        if raw.startswith('cat:'):
            slug = raw[4:]
        elif raw.startswith('@grp:'):
            parent = raw[5:]
            kids = [kk for p, kk in self._tree if p == parent for kk in kk]
            picked = str(ext.get('sub') or '').strip().strip('/').replace('category/', '', 1)
            if not picked:
                picked = kids[0][1] if kids else ''
            slug = picked
        slug = self._slug_of(slug)
        if not slug:
            return '', '/'
        return slug, '/category/%s/' % slug

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        slug, prefix = self._resolve_tid(tid, extend)
        ext = {}
        if isinstance(extend, dict):
            ext = {str(k).strip(): v for k, v in extend.items()}
        elif isinstance(extend, str) and extend.strip():
            try:
                d = json.loads(extend)
                if isinstance(d, dict):
                    ext = {str(k).strip(): v for k, v in d.items()}
            except Exception:
                ext = {}
        sub = str(ext.get('sub') or '').strip().strip('/').replace('category/', '', 1)
        if slug and slug not in REALTIME_MAP:
            sub = ''
        if sub:
            path = '/category/%s/%s/' % (slug, sub)
        elif slug:
            path = '/category/%s/' % slug if page == 1 else '/category/%s/%d/' % (slug, page)
        else:
            path = '/' if page == 1 else '/page/%d/' % page
        try:
            html = self._get(path, ttl=60)
            items = self._parse_realtime(html)
            if not items:
                items = self._parse_list(html)
        except Exception:
            items = []
            html = ''
        pagecount = page + 1
        if slug in REALTIME_MAP:
            pagecount = 1
        try:
            if items and slug not in REALTIME_MAP:
                body = html or ''
                total = self._page_total(body, slug, page)
                if total:
                    pagecount = total
        except Exception:
            pass
        return {'list': items, 'page': page, 'pagecount': pagecount,
                'limit': len(items) or PAGE_SIZE, 'total': 0,
                'totalpage': pagecount, 'moresort': False, 'parse': 0, 'jx': 0}

    def _detail_path(self, raw):
        s = str(raw or '').strip().strip('/')
        if not s:
            return '', ''
        if ':' in s and not s.startswith('http'):
            slug, vid = s.split(':', 1)
            slug = slug.strip()
            vid = re.sub(r'\D', '', vid)
            if slug and vid:
                return vid, '/category/%s/video/%s/' % (slug, vid)
        aid = re.sub(r'\D', '', s)
        if aid:
            return aid, '/archives/%s/' % aid
        m = re.search(r'/category/([a-z0-9]+)/video/(\d+)/', raw)
        if m:
            return m.group(2), '/category/%s/video/%s/' % (m.group(1), m.group(2))
        m2 = re.search(r'/archives/(\d+)/', raw)
        if m2:
            return m2.group(1), '/archives/%s/' % m2.group(1)
        return '', ''

    @staticmethod
    def _page_total(body, slug, page):
        if not body:
            return 0
        total = 0
        m = re.search(r'class="page-info"[^>]*>\s*(\d+)\s*/\s*(\d+)\s*<', body)
        if m:
            try:
                total = int(m.group(2))
            except Exception:
                total = 0
        if total <= 0:
            if slug:
                pat = r'/category/%s/(\d+)/' % re.escape(slug)
            else:
                pat = r'href="/page/(\d+)/"'
            nums = [int(x) for x in re.findall(pat, body) if str(x).isdigit() and int(x) > 0]
            if nums:
                total = max(nums)
        if total <= 0:
            nums = [int(x) for x in _RE_PAGER_CAT.findall(body) if x.isdigit() and int(x) > 0]
            if nums:
                total = max(nums)
        if total > 0 and total < page:
            total = page
        return total

    def detailContent(self, ids):
        raw = str((ids or [''])[0] if isinstance(ids, (list, tuple)) and ids else ids or '').strip()
        if not raw:
            return {'list': [], 'parse': 0, 'jx': 0}
        aid, path = self._detail_path(raw)
        if not aid or not path:
            return {'list': [], 'parse': 0, 'jx': 0}
        try:
            html = self._get(path, ttl=120)
        except Exception:
            return {'list': [], 'parse': 0, 'jx': 0}
        if not html:
            return {'list': [], 'parse': 0, 'jx': 0}
        title, cover, desc, year = self._detail_meta(html)
        tags = self._extract_tags(html)
        plays = self._extract_play(html)
        if plays:
            from_flags, from_urls = [], []
            for name, url in plays:
                from_flags.append(name)
                from_urls.append('%s$%s_dm_%s' % (name, raw, url))
            play_from = '$$$'.join(from_flags)
            play_url = '$$$'.join(from_urls)
        else:
            play_from = NAME
            play_url = '暂无资源$'
        vod = {
            'vod_id': aid,
            'vod_name': title or ('%s %s' % (NAME, aid)),
            'vod_pic': cover,
            'vod_pic_slide': cover,
            'vod_year': year,
            'vod_area': '未知',
            'vod_lang': '',
            'vod_class': ','.join(tags),
            'vod_tag': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_remarks': year or '',
            'vod_content': ('[年份] ' + year + ' | ' if year else '') + desc,
            'type_name': NAME,
            'vod_play_from': play_from,
            'vod_play_url': play_url,
        }
        return {'list': [vod], 'parse': 0, 'jx': 0, 'url': ''}

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or '').strip()
        if not raw:
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': {}, 'jx': 0}
        m = re.match(r'^([a-z0-9]+:?\d+)_dm_(.+)$', raw, re.S)
        if m:
            aid, url = m.group(1), m.group(2)
            _, page_path = self._detail_path(aid)
            page = self.site + (page_path or '/archives/%s/' % aid)
        else:
            url = raw
            page = self.site + '/'
        if not url.startswith('http'):
            url = self.site + '/' + url.lstrip('/')
        return {'parse': 0, 'playUrl': '', 'url': url,
                'header': {'User-Agent': UA, 'Referer': page, 'Origin': self.site}, 'jx': 0}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        kw = re.sub(r'\s+', ' ', str(key or '')).strip()
        if not kw:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 0,
                    'total': 0, 'totalpage': 1, 'moresort': False, 'parse': 0, 'jx': 0}
        cands = [kw]
        for cut in (24, 16, 10, 6):
            short = kw[:cut].strip()
            if short and short not in cands:
                cands.append(short)
        items = []
        for k in cands:
            enc = quote(k, safe='')
            path = '/tag/%s/' % enc if pg <= 1 else '/tag/%s/%d/' % (enc, pg)
            try:
                html = self._get(path, ttl=60)
                items = self._parse_list(html)
            except Exception:
                items = []
            if items:
                break
        return {'list': items, 'page': pg, 'pagecount': pg + 1 if items else 1,
                'limit': len(items), 'total': 0,
                'totalpage': pg + 1 if items else 1, 'moresort': False,
                'parse': 0, 'jx': 0}

    def searchContentPage(self, key, quick, pg="1", size="20"):
        return self.searchContent(key, quick, pg)

    def action(self, action):
        return '{}'

    def liveContent(self, url=""):
        return ''

    def _extract_proxy_url(self, param):
        if param is None:
            return ''
        url = ''
        if isinstance(param, str):
            url = param
        elif isinstance(param, dict):
            for k in ('url', 'pic', 'img', 'target', 'src', 'image', 'href', 'link', 'path', 'uri', 'raw', 'u'):
                v = param.get(k)
                if v:
                    url = str(v[0] if isinstance(v, list) and v else v)
                    break
            if not url:
                for vv in param.values():
                    if isinstance(vv, str) and vv.startswith('http'):
                        url = vv
                        break
        elif isinstance(param, (list, tuple)) and param:
            first = param[0]
            if isinstance(first, dict):
                return self._extract_proxy_url(first)
            elif isinstance(first, str):
                url = first
            else:
                url = str(first)
        else:
            url = str(param)
        url = url.strip().strip('"\'').strip()
        for _ in range(3):
            try:
                dec = unquote(url)
                if dec == url:
                    break
                url = dec
            except Exception:
                break
        if url.startswith('http') and 'url=' in url:
            try:
                q = parse_qs(urlsplit(url).query)
                if q.get('url'):
                    url = unquote(q['url'][0])
            except Exception:
                pass
        return url

    def _image(self, url):
        u = str(url or '').strip()
        if not u.startswith('http'):
            return b''
        raw = self._open(u, referer=self.site + '/', image=True)
        return raw

    def localProxy(self, param):
        try:
            url = self._extract_proxy_url(param)
            if not url:
                return [404, 'text/plain', b'', 'no url']
            if not url.startswith('http'):
                return [404, 'text/plain', b'', 'invalid url']
            raw = self._image(url)
            if not raw:
                return [200, 'text/plain;charset=utf-8', b'']
            if raw[:3] == b'\xff\xd8\xff':
                return [200, 'image/jpeg', raw]
            if raw[:8] == b'\x89PNG\r\n\x1a\n':
                return [200, 'image/png', raw]
            if raw[:3] == b'GIF':
                return [200, 'image/gif', raw]
            if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
                return [200, 'image/webp', raw]
            return [200, 'text/plain;charset=utf-8', b'']
        except Exception:
            return [200, 'text/plain;charset=utf-8', b'']

    def proxy(self, param):
        return self.localProxy(param)

    def isVideoFormat(self, url):
        u = str(url or '').lower()
        return any(x in u for x in ('.m3u8', '.mp4', '.flv', '.mkv', '.ts'))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._nav = None
        self._cache.clear()


_FIX_RT = """
<main class="candid-video-shell realtime-page">
  <nav class="realtime-tabs" aria-label="偷拍视频分类切换">
    <a class="active" href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/sstp/">热门推荐</a>
    <a class="" href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/sstp/live/">实时监控</a>
    <a class="" href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/sstp/replay/">精彩回放</a>
  </nav>
  <section class="realtime-grid" aria-label="热门推荐列表">
    <a class="realtime-card" href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/sstp/video/11115/" aria-label="偷情住了半个月天天呆在酒店有空就打两炮">
      <img class="realtime-card__cover" src="https://1.h8.ccwu.cc/https://www.91cg1.com/usr/themes/Mirages/images/zw.png" data-xkrkllgl="https://1.h8.ccwu.cc/https://pic.hdhwqx.cn/upload_01/upload/20260914/2026091419061253962.jpeg" data-xuid="candid-list-11115" alt="偷情住了半个月" loading="lazy" />
      <span class="realtime-card__shade"></span>
      <span class="realtime-card__status realtime-card__status--online"><i></i>在线</span>
    </a>
    <a class="realtime-card" href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/sstp/video/11383/" aria-label="情趣酒店小情侣一边亲嘴一边抠逼画面很美">
      <img class="realtime-card__cover" src="https://1.h8.ccwu.cc/https://www.91cg1.com/usr/themes/Mirages/images/zw.png" data-xkrkllgl="https://1.h8.ccwu.cc/https://pic.hdhwqx.cn/upload_01/upload/20260915/2026091522371223225.jpeg" data-xuid="candid-list-11383" alt="情趣酒店" loading="lazy" />
      <span class="realtime-card__status realtime-card__status--online"><i></i>在线</span>
    </a>
  </section>
</main>
"""

_FIX_RT_DETAIL = """
<html><head>
<meta property="og:image" content="https://1.h8.ccwu.cc/https://www.91cg1.com/usr/themes/Mirages/images/91cg3.jpg"/>
</head><body>
<h1 class="post-title">偷情住了半个月天天呆在酒店有空就打两炮</h1>
<section class="video-detail-player">
  <div class="dplayer dplayer-online" data-video_status="online" data-config='{"live":true,"video":{"url":"https://1.h8.ccwu.cc/https://op.udhhzr.cn/videos5/aaa/aaa.m3u8?auth_key=9&v=3","type":"hls","pic":"https://1.h8.ccwu.cc/https://pic.hdhwqx.cn/upload_01/upload/20260914/x.jpeg"}}'></div>
</section>
</body></html>
"""

_FIX_LIST = """
<div id="archive" role="main">
<article itemscope itemtype="http://schema.org/BlogPosting" class="">
  <meta itemprop="url mainEntityOfPage" content="/archives/126237/" />
  <a href="/archives/126237/">
    <div class="post-card" id="post-card-126237">
      <script type="text/javascript">
        loadBannerDirect('https://pic.91cg1.com/upload/20261027/126237.jpg', '',
          document.querySelector('#post-card-126237'), '-1', 100, 100);
      </script>
      <h2 class="post-card-title" itemprop="headline">
        法国球星姆巴佩 亲口承认自己辱华行为        <div class="wrap"><span class="wraps">热搜 HOT</span></div>
      </h2>
      <span itemprop="datePublished" content="2026-10-27T00:00:00+00:00">2026 年 10 月 27 日 </span>
    </div>
  </a>
</article>
<article itemscope itemtype="http://schema.org/BlogPosting" class="">
  <meta itemprop="url mainEntityOfPage" content="/archives/126338/" />
  <a href="/archives/126338/">
    <div class="post-card">
      <script>loadBannerDirect('https://pic.91cg1.com/upload/20261027/126338.jpg', '', document.querySelector('#x'), '-1', 1, 1);</script>
      <h2 class="post-card-title">姆巴佩就涉华不当言论道歉 &amp; 此前多家企业终止合作</h2>
      <span itemprop="datePublished" content="2026-10-27T00:00:00+00:00">2026 年 10 月 27 日</span>
    </div>
  </a>
</article>
<article itemscope itemtype="http://schema.org/BlogPosting" class="">
  <a href="/archives/126349/"><h2 class="post-card-title">91AI短剧 姆巴佩辱华国内神秘金主爆怒</h2></a>
</article>
</div>
"""

_FIX_NAV = """
<ul id="menu-menu-1" class="menu navbar-nav" data-content="24">
  <li class="menu-item"><a class="active" href="https://1.h8.ccwu.cc/https://www.91cg1.com/">首页</a></li>
  <li class="menu-item"><a href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/zxcghl/">今日吃瓜</a></li>
  <li class="nav-item dropdown">
    <button class="nav-link dropdown-toggle nav-item-button">午夜影院</button>
    <ul class="dropdown-menu">
      <li class="dropdown-item"><a href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/lpsd/">深夜撸片</a></li>
      <li class="dropdown-item"><a href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/hjll/">海角乱伦</a></li>
    </ul>
  </li>
  <li class="nav-item dropdown">
    <button class="nav-link dropdown-toggle nav-item-button">91吃瓜TOP榜</button>
    <ul class="dropdown-menu">
      <li class="dropdown-item"><a href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/zdtop/">91周榜</a></li>
      <li class="dropdown-item"><a href="https://1.h8.ccwu.cc/https://www.91cg1.com/category/ydtop/">91月榜</a></li>
    </ul>
  </li>
</ul>
"""

_FIX_DETAIL = """
<html><head>
<meta property="og:image" content="https://pic.91cg1.com/upload/20261027/126237.jpg"/>
</head><body>
<h1 class="post-title " itemprop="name headline">法国球星姆巴佩 亲口承认自己辱华行为</h1>
<div class="post-content" itemprop="articleBody">
  <div class="txt-apps"><a href="https://ads.x.cc" class="btn-app"><span>空降约炮</span></a></div>
  <p><img src="https://pic.91cg1.com/upload/20261027/1.jpg"></p>
  <h2>事情经过</h2>
  <p>正文第一段&nbsp;&amp;说明。</p>
  <div class="dplayer" data-video_id="126237001" data-config='{"live":false,"video":{"url":"https:\\/\\/hls.91cg1.com\\/videos\\/aaa\\/aaa.m3u8?auth_key=1&v=3&time=0","type":"hls"},"video_h265":{"url":"https:\\/\\/hls.91cg1.com\\/m3m\\/bbb.m3u8?auth_key=2&v=3&time=0","type":"hls"}}'></div>
  <p>正文第二段, 补充说明。</p>
  <p>下载APP观看完整版</p>
  <table><tr><td><a href="/">广告表格</a></td></tr></table>
</div>
<p><span itemprop="keywords" class="keywords"><a href="/tag/mupai/">姆巴佩</a><a href="/tag/rh/">辱华</a></span></p>
<div class="post-tags">标签区</div>
</body></html>
"""


def _offline_suite():
    sp = Spider()
    sp.init('{}')
    sp._tree = [(p, list(kids)) for p, kids in FALLBACK_CATEGORY_TREE]
    rows = []

    def ck(name, cond, info=''):
        rows.append((name, bool(cond), info))

    # 1. 列表解析
    items = sp._parse_list(_FIX_LIST)
    ck('list.count', len(items) == 3, 'len=%d' % len(items))
    ck('list.ids', [i['vod_id'] for i in items] == ['126237', '126338', '126349'],
       str([i['vod_id'] for i in items]))
    ck('list.name_strip', '姆巴佩' in items[0]['vod_name'], items[0]['vod_name'])
    ck('list.unescape', '&' in items[1]['vod_name'], items[1]['vod_name'])
    ck('list.cover', '2.h8.ccwu.cc' in items[0]['vod_pic'], items[0]['vod_pic'][:70])
    ck('list.nocover_ok', items[2]['vod_pic'] == '', 'no-cover card kept')
    ck('list.remark', '10' in items[0]['vod_remarks'], items[0]['vod_remarks'])

    # 2. 导航/分类体系
    sp._refresh_tree(_FIX_NAV)
    ck('nav.groups', len(sp._tree) == 3, str([p for p, _ in sp._tree]))
    ck('nav.subs', [s for _, s in sp._tree[0][1]] == ['lpsd', 'hjll'], str(sp._tree[0][1]))
    ck('nav.btn_name', sp._tree[0][0] == '午夜影院', sp._tree[0][0])
    ck('slug_of', sp._slug_of('/category/whhj/') == 'whhj', '')

    # 3. 详情解析
    title, cover, desc, year = sp._detail_meta(_FIX_DETAIL)
    ck('detail.title', '姆巴佩' in title, title)
    ck('detail.cover', '2.h8.ccwu.cc' in cover, cover[:70])
    ck('detail.desc_cut', '下载APP' not in desc and '空降约炮' not in desc, desc[:80])
    ck('detail.desc_body', '正文第一段' in desc and '正文第二段' in desc, desc[:120])
    ck('detail.tags', sp._extract_tags(_FIX_DETAIL) == ['姆巴佩', '辱华'],
       str(sp._extract_tags(_FIX_DETAIL)))

    # 4. 播放解析
    plays = sp._extract_play(_FIX_DETAIL)
    ck('play.count', len(plays) == 2, str([p[0] for p in plays]))
    ck('play.names', [p[0] for p in plays] == ['标清', 'H265'], str([p[0] for p in plays]))
    ck('play.url_unescaped', '\\/' not in plays[0][1], plays[0][1][:50])
    ck('play.keep_query', 'auth_key=1&v=3&time=0' in plays[0][1], plays[0][1])

    # 5. 全链路
    sp._get = lambda path, referer=None, ttl=0, binary=False: _FIX_DETAIL if 'archives' in str(path) else _FIX_LIST
    det = sp.detailContent(['126237'])
    v = det['list'][0]
    ck('detail.vod_id', v['vod_id'] == '126237', v['vod_id'])
    ck('detail.play_from', v['vod_play_from'] == '标清$$$H265', v['vod_play_from'])
    segs = v['vod_play_url'].split('$$$')
    ck('detail.two_lines', len(segs) == 2, str(len(segs)))
    ep = segs[0].split('#')[0].split('$', 1)[1]
    ck('detail.ep_encoded', '_dm_' in ep, ep[:60])
    pc = sp.playerContent('标清', ep, [])
    ck('player.parse', pc['parse'] == 0, str(pc['parse']))
    ck('player.url', pc['url'].endswith('.m3u8?auth_key=1&v=3&time=0'), pc['url'][-40:])
    ck('player.referer', pc['header']['Referer'].endswith('/archives/126237/'),
       pc['header']['Referer'])

    # 6. 分类菜单
    cls = sp._classes()
    flt = sp._filters()
    ck('menu.home_first', cls[0]['type_id'] == '@home', cls[0]['type_id'])
    ck('menu.has_grp', any(c['type_id'].startswith('@grp:') for c in cls), '')
    ck('menu.has_cat', any(c['type_id'].startswith('cat:') for c in cls), '')
    ck('filter.sub_shape', isinstance(flt.get('@grp:午夜影院'), list) and
       flt['@grp:午夜影院'][0].get('key') == 'sub', '')
    ck('filter.sub_count', len(flt['@grp:午夜影院'][0]['value']) == 3,
       str(len(flt['@grp:午夜影院'][0]['value'])))
    ck('filter.keys_cover_class', all(c['type_id'] in flt for c in cls), '')

    # 7. type_id 解析
    ck('tid.home', sp._resolve_tid('@home', None) == ('', '/'), '')
    ck('tid.cat', sp._resolve_tid('cat:hjll', None) == ('hjll', '/category/hjll/'), '')
    ck('tid.grp_default', sp._resolve_tid('@grp:午夜影院', None)[0] == 'lpsd', '')
    ck('tid.grp_extend', sp._resolve_tid('@grp:午夜影院', {'sub': 'hjll'})[0] == 'hjll', '')
    ck('tid.grp_json', sp._resolve_tid('@grp:午夜影院', '{"sub":"zdtop"}')[0] == 'zdtop', '')
    ck('tid.bare_slug', sp._resolve_tid('hjll', None)[0] == 'hjll', '')

    # 8. categoryContent 全链路
    paths = []
    sp2 = Spider()
    sp2.init('{}')
    sp2._tree = sp._tree
    sp2._get = lambda path, referer=None, ttl=0, binary=False: paths.append(str(path)) or _FIX_LIST
    c = sp2.categoryContent('@grp:午夜影院', '1', True, {'sub': 'hjll'})
    ck('cat.filtered_path', paths[-1] == '/category/hjll/', paths[-1])
    ck('cat.filtered_list', len(c['list']) == 3, 'len=%d' % len(c['list']))
    sp2.categoryContent('@grp:午夜影院', '3', True, {'sub': 'hjll'})
    ck('cat.p3_path', paths[-1] == '/category/hjll/3/', paths[-1])
    sp2.categoryContent('@home', '2', True, {})
    ck('cat.home_p2', paths[-1] == '/page/2/', paths[-1])

    # 9. 搜索
    sp2._get = lambda path, referer=None, ttl=0, binary=False: _FIX_LIST
    s = sp2.searchContent('姆巴佩', False, '1')
    ck('search.list', len(s['list']) > 0, 'n=%d' % len(s['list']))
    ck('search.empty', sp2.searchContent('', False, '1')['list'] == [], '')

    # 10. 接口完整性
    ck('interfaces', all(hasattr(sp2, m) for m in ('init', 'getName', 'homeContent',
                                                   'homeVideoContent', 'categoryContent',
                                                   'detailContent', 'playerContent',
                                                   'searchContent', 'searchContentPage',
                                                   'action', 'liveContent', 'localProxy',
                                                   'proxy', 'isVideoFormat',
                                                   'manualVideoCheck', 'getDependence',
                                                   'destroy')), '')

    # 11. 封面解密代理
    cov = sp._proxy_cover('https://pic.91cg1.com/upload/20261027/1.jpg')
    ck('cover.decrypt_url', cov.startswith('https://2.h8.ccwu.cc/?url='), cov[:70])

    # 12. 实时偷拍 realtime 模板
    rt = sp._parse_realtime(_FIX_RT)
    ck('rt.count', len(rt) == 2, 'len=%d' % len(rt))
    ck('rt.ids', [r['vod_id'] for r in rt] == ['sstp:11115', 'sstp:11383'],
       str([r['vod_id'] for r in rt]))
    ck('rt.title', '偷情' in rt[0]['vod_name'], rt[0]['vod_name'][:40])
    ck('rt.status', rt[0]['vod_remarks'] == '直播中', rt[0]['vod_remarks'])
    ck('rt.cover', rt[0]['vod_pic'].startswith('https://2.h8.ccwu.cc/?url='), rt[0]['vod_pic'][:60])
    ck('rt.no_double_proxy', '1.h8.ccwu.cc' not in rt[0]['vod_pic'], rt[0]['vod_pic'][:80])
    ck('rt.no_article', rt and 'article' not in rt[0]['vod_name'].lower(), '')

    # 13. 复合 id 详情路径
    ck('path.composite', sp._detail_path('sstp:11115') == ('11115', '/category/sstp/video/11115/'),
       str(sp._detail_path('sstp:11115')))
    ck('path.plain', sp._detail_path('126413') == ('126413', '/archives/126413/'),
       str(sp._detail_path('126413')))

    # 14. 实时详情：data-config 多 class + 封面落 pic 字段
    plays_rt = sp._extract_play(_FIX_RT_DETAIL)
    ck('rt.play_found', len(plays_rt) == 1, str(len(plays_rt)))
    ck('rt.play_url', 'op.udhhzr.cn' in plays_rt[0][1], plays_rt[0][1][:60])
    t2, c2, d2, y2 = sp._detail_meta(_FIX_RT_DETAIL)
    ck('rt.detail_title', '偷情' in t2, t2[:40])
    ck('rt.detail_cover_pic', c2.startswith('https://2.h8.ccwu.cc/?url='), c2[:70])
    ck('rt.detail_cover_real', 'pic.hdhwqx.cn' in c2, c2[:90])

    # 15. 实时分类过滤与分页抑制
    ck('rt.filter_exists', sp._filter_rt('sstp').get('key') == 'sub', '')
    ck('rt.filter_values', [v['v'] for v in sp._filter_rt('sstp')['value']] == ['', 'live', 'replay'],
       str([v['v'] for v in sp._filter_rt('sstp')['value']]))
    ck('rt.page_total_skip', sp._page_total('', 'sstp', 1) == 0, '')

    # 16. 分页总数 page-info
    ck('pager.page_info', sp._page_total(
        '<span class="page-info"> 1/1391 </span>', 'zxcghl', 1) == 1391, '')
    ck('pager.cat_fallback', sp._page_total(
        'href="/category/zxcghl/2/"', 'zxcghl', 1) == 2, '')
    ck('pager.clamp', sp._page_total('<span class="page-info"> 9/5 </span>', 'x', 9) == 9, '')

    return rows


def _print(title, rows):
    print('\n===== %s =====' % title)
    for name, ok, info in rows:
        print('  [%s] %s %s' % ('PASS' if ok else 'FAIL', name, info))
    bad = [r for r in rows if not r[1]]
    print('  -> %d/%d passed' % (len(rows) - len(bad), len(rows)))
    return not bad


if __name__ == "__main__":
    all_ok = _print('OFFLINE PARSE TESTS', _offline_suite())

    try:
        sp = Spider()
        sp.init('{}')
        hc = sp.homeContent(True)
        cls = hc.get('class') or []
        ok = len(cls) >= 5
        print('\n[NETWORK] homeContent classes=%d %s' % (len(cls), 'OK' if ok else 'FAIL'))
        hv = sp.homeVideoContent()
        print('[NETWORK] homeVideoContent list=%d %s' % (len(hv['list']), 'OK' if hv['list'] else 'SKIP'))
        if hv['list']:
            c1 = sp.categoryContent('cat:zxcghl', '1', True, '')
            print('[NETWORK] categoryContent p1 list=%d %s' % (len(c1['list']), 'OK' if c1['list'] else 'SKIP'))
            if c1['list']:
                vid = c1['list'][0]['vod_id']
                vod = sp.detailContent([vid])['list'][0]
                print('[NETWORK] detailContent id=%s name=%s from=%s %s'
                      % (vid, vod['vod_name'][:30], vod['vod_play_from'][:30],
                         'OK' if vod['vod_name'] else 'FAIL'))
                sc = sp.searchContent('吃瓜', False, '1')
                print('[NETWORK] searchContent list=%d %s' % (len(sc['list']), 'OK' if sc['list'] else 'SKIP'))
    except Exception as e:
        print('[NETWORK] skipped: %s' % str(e)[:100])

    print('\n==== %s ====' % ('ALL PASS' if all_ok else 'HAS FAILURES'))
