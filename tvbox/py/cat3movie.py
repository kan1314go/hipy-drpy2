# -*- coding: utf-8 -*-
# ============================================================================
#  TVBox Python 爬虫 —— cat3movie.club   v1.1.0
# ----------------------------------------------------------------------------
#  v1.1.0 修复:
#    [P0] vod_play_from 与 vod_play_url 的 $$$ 分组数必须 1:1 —— 原来 3 组对 1 组，
#         导致线路绑定失败、点开即黑屏。现每条线路独立分组。
#    [P0] 封面不再从 content 抠（content 多为空），改为解析列表页 HTML 的
#         background-image，并以 meta.fifu_image_url / og:image 兜底。
#    [P1] 直连 mp4 被 CDN 拦 Referer 时，本地代理补 UA/Referer/Origin 后回源。
# ============================================================================

import base64
import json
import re
import sys
import time
from urllib.parse import quote, unquote

import requests

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def init(self, extend=''):
            pass


class Spider(BaseSpider):

    siteUrl   = 'https://www.cat3movie.club'
    kissasian = 'https://kissasian.info'
    kisskh    = 'https://kisskh.top'
    okWorker  = 'https://s3.nizu.top'
    proxyHost = 'https://s1.nizu.top'
    proxyPath = '/api/m.php'

    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

    FIELDS = 'id,slug,link,date,categories,title,content,excerpt,meta,featured_media'

    RE_SHORTCODE = re.compile(
        r"\[jwplayer\s+id\s*=\s*[’'\"′]?\s*(https?://[^\s’'\"′\]]+?\.(?:mp4|m3u8))", re.I)
    RE_KISKKH_SRC = re.compile(r"jwplayer/\?source=([^&\"'\s>]+)", re.I)
    RE_KISKKH_JW  = re.compile(r'"file"\s*:\s*"([^"]+?\.(?:mp4|m3u8))"', re.I)
    RE_LINK_KISKKH    = re.compile(r"https?://kisskh\.top/movies/([A-Za-z0-9\-_]+)", re.I)
    RE_LINK_KISSASIAN = re.compile(
        r"https?://kissasian\.info/(?:movies|tv-series)/([A-Za-z0-9\-_]+)", re.I)

    # 列表页：同一 <a> 标签内 href 在前、background-image 在后
    RE_CARD = re.compile(
        r'href="(?:https?://www\.cat3movie\.club)?/([A-Za-z0-9\-_%]+)/?"'
        r'[^>]*?background-image:\s*url\(&quot;([^&]+)&quot;\)', re.I)
    RE_OGIMG = re.compile(
        r'<meta\s+property="og:image"\s+content="([^"]+)"', re.I)

    def __init__(self):
        self.timeout = 15
        self.headers = {
            'User-Agent': self.UA,
            'Accept': 'text/html,application/json,*/*',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8',
            'Referer': self.siteUrl + '/',
        }
        self._cache = {}
        self._pics = {}

    def init(self, extend=''):
        try:
            cfg = json.loads(extend) if extend else {}
            if isinstance(cfg, dict):
                self.siteUrl = (cfg.get('site') or self.siteUrl).rstrip('/')
                self.timeout = int(cfg.get('timeout') or self.timeout)
        except Exception:
            pass

    # ==================================================================
    #  基础
    # ==================================================================
    def _get(self, url, headers=None, binary=False):
        h = dict(self.headers)
        if headers:
            h.update(headers)
        if 'kissasian' in url:
            h['Referer'] = self.kissasian + '/'
        elif 'kisskh' in url:
            h['Referer'] = self.kisskh + '/'
        elif 'nizu' in url or 'rumble' in url:
            h['Referer'] = self.kissasian + '/'
            h['Origin'] = self.kissasian

        last = None
        for _ in range(2):
            try:
                if hasattr(self, 'fetch'):
                    r = self.fetch(url, headers=h, timeout=self.timeout)
                else:
                    r = requests.get(url, headers=h, timeout=self.timeout)
                if binary:
                    return r.content
                return getattr(r, 'text', None) or r.content.decode('utf-8', 'ignore')
            except Exception as e:
                last = e
                time.sleep(0.4)
        raise last if last else RuntimeError(url)

    def _json(self, url):
        if url in self._cache:
            return self._cache[url]
        try:
            data = json.loads(self._get(url))
        except Exception:
            data = None
        self._cache[url] = data
        return data

    def _abs(self, path):
        return path if path.startswith('http') else self.siteUrl + '/' + path.lstrip('/')

    @staticmethod
    def _clean_title(t):
        t = re.sub(r'<[^>]+>', '', t or '')
        t = unquote(t).replace('&amp;', '&').replace('&#8217;', "'").replace('&quot;', '"')
        t = re.sub(r'^\s*(VIVAMAX|TBONX|SEXTOP|VMAX)\s*\|\s*', '', t, flags=re.I)
        return t.strip()

    def _proxy(self, url):
        """把真实地址包成本地代理，代理侧补头回源。"""
        try:
            if hasattr(self, 'getProxyUrl'):
                return self.getProxyUrl({'url': url, 'type': 'mp4'})
        except Exception:
            pass
        return url

    # ==================================================================
    #  封面：列表页 HTML 映射 → fifu → og:image
    # ==================================================================
    def _load_pic_map(self, page_url):
        if page_url in self._pics:
            return self._pics[page_url]
        m = {}
        try:
            html = self._get(page_url)
            for slug, pic in self.RE_CARD.findall(html):
                pic = unquote(pic)
                if pic.startswith('http') and slug not in m:
                    m[slug] = pic
        except Exception:
            pass
        self._pics[page_url] = m
        return m

    def _pic_of(self, post, pic_map):
        slug = post.get('slug') or ''
        if slug and slug in pic_map:
            return pic_map[slug]
        meta = post.get('meta') or {}
        if meta.get('fifu_image_url'):
            return meta['fifu_image_url']
        try:
            m = re.search(r'background-image:\s*url\(&quot;(.*?)&quot;\)',
                          (post.get('content') or {}).get('rendered') or '')
            if m:
                return unquote(m.group(1))
        except Exception:
            pass
        return ''

    # ==================================================================
    #  首页
    # ==================================================================
    def homeContent(self, filter):
        classes = [{'type_id': '0', 'type_name': '最新更新'}]
        cats = self._json('{}/wp-json/wp/v2/categories?per_page=100&_fields=id,name,count'
                          .format(self.siteUrl))
        if isinstance(cats, list):
            for c in cats:
                if c.get('count', 0) <= 0:
                    continue
                classes.append({'type_id': str(c['id']), 'type_name': c.get('name')})
        return {'class': classes, 'filters': {},
                'list': self.homeVideoContent().get('list', [])}

    def homeVideoContent(self):
        return {'list': self._list('https://www.cat3movie.club/page/1/',
                                   '/wp-json/wp/v2/posts?page=1&per_page=20')}

    # ==================================================================
    #  列表 / 分类 / 搜索
    # ==================================================================
    def _list(self, page_url, api_path):
        posts = self._json('{}{}&_fields={}'.format(self.siteUrl, api_path, self.FIELDS))
        if not isinstance(posts, list):
            return []
        pic_map = self._load_pic_map(page_url)
        out = []
        for p in posts:
            out.append({
                'vod_id': p.get('slug') or str(p.get('id')),
                'vod_name': self._clean_title((p.get('title') or {}).get('rendered')),
                'vod_pic': self._pic_of(p, pic_map),
                'vod_remarks': (p.get('date') or '')[:10],
            })
        return out

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1')
        if tid in ('', None, '0', 'latest'):
            page_url = '{}/page/{}/'.format(self.siteUrl, pg)
            api = '/wp-json/wp/v2/posts?page={}&per_page=20'.format(pg)
        else:
            page_url = '{}/?cat={}&paged={}'.format(self.siteUrl, tid, pg)
            api = '/wp-json/wp/v2/posts?categories={}&page={}&per_page=20'.format(tid, pg)
        vlist = self._list(page_url, api)
        total = int(pg) + (1 if len(vlist) >= 20 else 0)
        return {'page': int(pg), 'pagecount': total, 'limit': 20,
                'total': total * 20, 'list': vlist}

    def searchContent(self, key, quick, pg='1'):
        pg = str(pg or '1')
        api = '/wp-json/wp/v2/posts?search={}&page={}&per_page=20'.format(quote(key or ''), pg)
        page_url = '{}/?s={}&paged={}'.format(self.siteUrl, quote(key or ''), pg)
        return {'page': int(pg), 'pagecount': 1, 'limit': 20,
                'total': 20, 'list': self._list(page_url, api)}

    # ==================================================================
    #  详情
    # ==================================================================
    def _post(self, key):
        key = str(key)
        if key.isdigit():
            d = self._json('{}/wp-json/wp/v2/posts/{}?_fields={}'.format(
                self.siteUrl, key, self.FIELDS))
            return d if isinstance(d, dict) else None
        arr = self._json('{}/wp-json/wp/v2/posts?slug={}&_fields={}'.format(
            self.siteUrl, quote(key), self.FIELDS))
        return arr[0] if isinstance(arr, list) and arr else None

    def _mp4_variants(self, mp4, name):
        """代理优先（补头回源），直连次之，最后给 m.php 代理。"""
        out = []
        p = self._proxy(mp4)
        if p != mp4:
            out.append((name + '·代理', p))
        out.append((name, mp4))
        try:
            b64 = quote(base64.b64encode(mp4.encode()).decode(), safe='')
            ext = 'm3u8' if mp4.endswith('.m3u8') else 'mp4'
            out.append(('m.php', '{}{}?v={}&type={}'.format(self.proxyHost, self.proxyPath, b64, ext)))
        except Exception:
            pass
        return out

    def _from_kisskh(self, slug):
        html = self._get('{}/movies/{}/'.format(self.kisskh, slug))
        m = self.RE_KISKKH_SRC.search(html)
        if m:
            u = unquote(m.group(1).replace('&amp;', '&'))
            if u.startswith('http'):
                return u
        m = self.RE_KISKKH_JW.search(html)
        if m:
            u = unquote(m.group(1).replace('\\/', '/'))
            if u.startswith('http'):
                return u
        return None

    def _from_kissasian(self, slug=None, title=None):
        q = ('find_slug=' + quote(slug)) if slug else ('search=' + quote(title or ''))
        data = self._json('{}/api/movies.php?{}&paginated=1&limit=5'.format(self.kissasian, q))
        if not isinstance(data, dict) or not data.get('data'):
            return [], None
        rows = data['data']
        best = rows[0]
        if title:
            tl = title.strip().lower()
            for r in rows:
                if (r.get('title') or '').strip().lower() == tl:
                    best = r
                    break
        out, sub = [], None
        try:
            servers = json.loads(best.get('servers') or '[]')
        except Exception:
            servers = []
        for sv in servers:
            for ep in sv.get('episodes') or []:
                raw = ep.get('url') or ''
                if not raw:
                    continue
                parts = raw.split('|')
                u = parts[0]
                if not sub and len(parts) > 2 and parts[2].startswith('http'):
                    sub = parts[2]
                if 'ok.ru' in u:
                    try:
                        j = self._json('{}?url={}'.format(self.okWorker, quote(u, safe='')))
                        st = (j or {}).get('streams') or []
                        if st:
                            out.append(('OK', st[0].get('proxyUrl') or st[0].get('url')))
                    except Exception:
                        pass
                elif u.endswith('.mp4') or u.endswith('.m3u8'):
                    out.extend(self._mp4_variants(u, 'Rumble'))
        return out, sub

    def _sources(self, post, slug):
        seen, res = set(), []

        def push(pairs):
            for name, url in pairs:
                if url and url not in seen:
                    seen.add(url)
                    res.append((name, url))

        content = (post.get('content') or {}).get('rendered') or ''
        for m in self.RE_SHORTCODE.finditer(content):
            push(self._mp4_variants(unquote(m.group(1)), '直连'))
        if res:
            return res, None

        try:
            html = self._get('{}/{}/'.format(self.siteUrl, slug))
        except Exception:
            html = content

        m = self.RE_LINK_KISKKH.search(html)
        if m:
            u = self._from_kisskh(m.group(1))
            if u:
                push(self._mp4_variants(u, 'Kisskh'))
        if res:
            return res, None

        sub = None
        m = self.RE_LINK_KISSASIAN.search(html)
        if m:
            pairs, sub = self._from_kissasian(slug=m.group(1))
            push(pairs)
        if res:
            return res, sub

        title = self._clean_title((post.get('title') or {}).get('rendered'))
        if title:
            pairs, s2 = self._from_kissasian(slug=slug, title=title)
            push(pairs)
            sub = sub or s2
        return res, sub

    def detailContent(self, ids):
        key = str(ids[0])
        post = self._post(key)
        if not post:
            return {'list': []}
        slug = post.get('slug') or key
        sources, sub = self._sources(post, slug)

        pic = self._pic_of(post, {})
        if not pic:
            try:
                m = self.RE_OGIMG.search(self._get('{}/{}/'.format(self.siteUrl, slug)))
                if m:
                    pic = m.group(1)
            except Exception:
                pass

        froms, plays = [], []
        for name, url in sources:
            froms.append(name)
            plays.append('播放$' + url)          # 一条线路一个分组，与 froms 严格 1:1
        if not froms:
            froms, plays = ['线路'], ['播放$']

        vod = {
            'vod_id': slug,
            'vod_name': self._clean_title((post.get('title') or {}).get('rendered')),
            'vod_pic': pic,
            'vod_remarks': (post.get('date') or '')[:10],
            'vod_content': re.sub(r'<[^>]+>', '',
                                  (post.get('excerpt') or {}).get('rendered') or '')[:400],
            'vod_play_from': '$$$'.join(froms),
            'vod_play_url': '$$$'.join(plays),
        }
        if sub:
            vod['vod_sub'] = sub
        return {'list': [vod]}

    # ==================================================================
    #  播放
    # ==================================================================
    def playerContent(self, flag, id, vipFlags):
        url = (id or '').strip()
        header = {'User-Agent': self.UA,
                  'Referer': self.kissasian + '/',
                  'Origin': self.kissasian}

        if 'ok.ru' in url and 'nizu' not in url:
            try:
                j = self._json('{}?url={}'.format(self.okWorker, quote(url, safe='')))
                st = (j or {}).get('streams') or []
                if st:
                    url = st[0].get('proxyUrl') or st[0].get('url') or url
            except Exception:
                pass

        if url.endswith('.m3u8') or 'hls' in url or 'm.php' in url:
            header = {'User-Agent': self.UA}
        return {'parse': 0, 'playUrl': '', 'url': url, 'header': header}

    def localProxy(self, param):
        try:
            url = param.get('url') if isinstance(param, dict) else param
            if not url:
                return [404, 'text/plain', b'']
            data = self._get(url, binary=True)
            ctype = ('application/vnd.apple.mpegurl' if url.endswith('.m3u8')
                     else 'video/mp4')
            return [200, ctype, data]
        except Exception:
            return [500, 'text/plain', b'']