# coding: utf-8
"""
站点：jfdxl.dfjxlw02.lol（WordPress 自定义主题，DPlayer 直出 m3u8）
架构：列表/分类/搜索同构卡片 div.post-item；详情 video:{url:xxx.m3u8}
播放：多码率主表 → 子流 631 片，明文 TS，1 个插片广告目录（m3u8_ad_filter v5.1）
验证：2026-10-29 实测
"""
import re
import json
import posixpath
from urllib.parse import quote, urljoin, unquote, urlparse, parse_qsl

from base.spider import Spider as BaseSpider


IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.avif')
VIDEO_EXT = ('.ts', '.m4s', '.mp4', '.aac', '.m4a', '.cmfv', '.cmfa', '.m4v')
_GLOBAL_TAGS = (
    '#EXTM3U', '#EXT-X-VERSION', '#EXT-X-TARGETDURATION', '#EXT-X-MEDIA-SEQUENCE',
    '#EXT-X-DISCONTINUITY-SEQUENCE', '#EXT-X-PLAYLIST-TYPE', '#EXT-X-INDEPENDENT-SEGMENTS',
    '#EXT-X-START', '#EXT-X-I-FRAMES-ONLY',
)


class M3U8AdFilter(object):
    """m3u8 广告分片过滤器 v5.1（自包含）。spider 需提供 getProxyUrl() 与 fetch()。"""

    def __init__(self, spider=None, need_clean=True, ad_dirs=None, anchor_dirs=None,
                 long_factor=3.0, long_floor=25.0, max_depth=2, logger=None):
        self.spider = spider
        self.need_clean = bool(need_clean)
        self.ad_dirs = [self._norm_dir(d) for d in (ad_dirs or []) if d]
        self.anchor_dirs = [self._norm_dir(d) for d in (anchor_dirs or []) if d]
        self.long_factor = float(long_factor)
        self.long_floor = float(long_floor)
        self.max_depth = int(max_depth)
        self.logger = logger

    def _log(self, data):
        if self.logger:
            try:
                self.logger(data)
            except Exception:
                pass

    def _proxy_base(self):
        sp = self.spider
        if sp is None:
            return ''
        for name in ('getProxyUrl', 'get_proxy_url'):
            fn = getattr(sp, name, None)
            if callable(fn):
                try:
                    return str(fn() or '')
                except Exception:
                    return ''
        return ''

    def _fetch(self, url, timeout=20, referer=None):
        sp = self.spider
        if sp is None:
            return b''
        headers = {}
        h = getattr(sp, 'headers', None)
        if isinstance(h, dict):
            headers.update(h)
        if referer:
            headers.setdefault('Referer', referer)
        fn = getattr(sp, 'fetch', None)
        if not callable(fn):
            return b''
        resp = fn(url, headers=headers, timeout=timeout)
        if resp is None:
            return b''
        content = getattr(resp, 'content', None)
        if content is None:
            content = getattr(resp, 'text', b'')
        if isinstance(content, str):
            content = content.encode('utf-8', 'ignore')
        return content or b''

    @staticmethod
    def _norm_dir(d):
        d = str(d or '').strip()
        if not d:
            return ''
        return d if d.endswith('/') else d + '/'

    @staticmethod
    def _path(url, source_url):
        u = url if url.startswith(('http://', 'https://')) else urljoin(source_url, url)
        return urlparse(u).path

    @staticmethod
    def _parse_duration(line):
        m = re.match(r'#EXTINF:\s*([\d.]+)', line or '')
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def proxy_url(self, url, depth=0):
        u = str(url or '').strip().replace('\\/', '/')
        base = self._proxy_base()
        if not base:
            return u
        sep = '&' if '?' in base else '?'
        parts = []
        if 'do=py' not in base:
            parts.append('do=py')
        parts.append('url=' + quote(u, safe=''))
        if depth:
            parts.append('d=%d' % int(depth))
        return base + sep + '&'.join(parts)

    def probe(self, text, source_url):
        lines = self._lines(text)
        ev = {'segment_count': 0, 'is_multi_bitrate': False, 'is_fake_image_stream': False,
              'dirs': {}, 'key_uris': [], 'suspicious_ad_dirs': [], 'anchor_dirs': [],
              'dur_median': None, 'cue_segments': 0}
        if any(l.startswith('#EXT-X-STREAM-INF') for l in lines):
            ev['is_multi_bitrate'] = True
        pre, entries, _ = self._split(lines)
        ev['segment_count'] = len(entries)
        if not entries:
            return ev
        counter = self._dir_counter(entries, source_url)
        ev['dirs'] = dict(sorted(counter.items(), key=lambda kv: -kv[1]))
        ev['is_fake_image_stream'] = self._is_image_stream(entries, source_url)
        ev['key_uris'] = [self._tag_uri(t) for t in pre + [x for e in entries for x in e['tags']]
                          if t.startswith(('#EXT-X-KEY', '#EXT-X-MAP')) and 'URI=' in t]
        ev['cue_segments'] = sum(1 for e in entries if e.get('cue'))
        anchors, strength = self._resolve_anchors(entries, source_url, ev['is_fake_image_stream'], pre)
        ev['anchor_dirs'] = anchors
        ev['anchor_strength'] = strength
        ev['suspicious_ad_dirs'] = [d for d, c in counter.items()
                                    if d not in anchors and not any(d.startswith(a) for a in anchors)]
        durs = sorted(e['dur'] for e in entries
                      if e.get('dur') and any(self._path(e['url'], source_url).startswith(a) for a in anchors))
        ev['dur_median'] = durs[len(durs) // 2] if durs else None
        ev['need_clean'] = bool(ev['suspicious_ad_dirs'] or ev['is_fake_image_stream'] or ev['cue_segments'])
        return ev

    @staticmethod
    def _tag_uri(tag):
        m = re.search(r'URI="([^"]+)"', tag or '')
        return m.group(1) if m else ''

    @staticmethod
    def _lines(text):
        return [l.strip() for l in str(text or '').replace('\r', '').split('\n') if l.strip()]

    def _split(self, lines):
        pre, entries, pending = [], [], []
        cur_inf, cur_tags = None, []
        cue_on = False
        seen_entry = False
        for line in lines:
            if line.startswith('#'):
                if line.startswith('#EXTINF'):
                    if cur_inf is not None:
                        cur_inf, cur_tags = None, []
                    cur_inf = line
                    continue
                if cur_inf is not None:
                    cur_tags.append(line)
                elif seen_entry:
                    pending.append(line)
                else:
                    pre.append(line)
                if line.startswith('#EXT-X-CUE-OUT'):
                    cue_on = True
                elif line.startswith('#EXT-X-CUE-IN'):
                    cue_on = False
                continue
            if cur_inf is None:
                pre.append(line)
                continue
            entries.append({'dur': self._parse_duration(cur_inf), 'inf': cur_inf,
                            'tags': pending + cur_tags, 'url': line, 'cue': cue_on})
            seen_entry = True
            pending, cur_inf, cur_tags = [], None, []
        trailer = pending + cur_tags
        if entries:
            cue_n = sum(1 for e in entries if e['cue'])
            if cue_n * 2 >= len(entries):
                for e in entries:
                    e['cue'] = False
        return pre, entries, trailer

    def _dir_counter(self, entries, source_url):
        counter = {}
        for e in entries:
            d = posixpath.dirname(self._path(e['url'], source_url))
            if d and d != '/':
                d += '/'
                counter[d] = counter.get(d, 0) + 1
        return counter

    def _is_image_stream(self, entries, source_url):
        has_video = has_image = False
        for e in entries:
            p = self._path(e['url'], source_url).lower()
            if p.endswith(VIDEO_EXT):
                has_video = True
            elif p.endswith(IMAGE_EXT):
                has_image = True
        return has_image and not has_video

    def _resolve_anchors(self, entries, source_url, is_img, pre=None):
        if self.anchor_dirs:
            return self.anchor_dirs, 'config'
        if not entries:
            return [], 'none'
        total = len(entries)
        counter = self._dir_counter(entries, source_url)
        if not counter:
            return [], 'none'
        key_dirs = []
        tags_all = list(pre or []) + [t for e in entries for t in e['tags']]
        for t in tags_all:
            if t.startswith(('#EXT-X-KEY', '#EXT-X-MAP')) and 'URI=' in t:
                kd = posixpath.dirname(self._path(self._tag_uri(t), source_url))
                if kd and kd != '/':
                    key_dirs.append(kd + '/')
        if key_dirs:
            best, best_n = None, 0
            for kd in sorted(set(key_dirs)):
                n = sum(1 for e in entries if self._path(e['url'], source_url).startswith(kd))
                if n > best_n:
                    best, best_n = kd, n
            if best:
                return [best], 'key'
        top = max(counter.items(), key=lambda kv: kv[1])[0]
        topn = counter[top]
        anchors = [top]
        for d, c in counter.items():
            if d == top:
                continue
            if c * 2 > topn or d.startswith(top) or top.startswith(d):
                anchors.append(d)
        if anchors == [top] and topn * 2 < total:
            return sorted(set(anchors)), 'weak'
        return sorted(set(anchors)), 'dir'


    def clean(self, text, source_url, depth=0):
        lines = self._lines(text)
        if not lines:
            return '#EXTM3U\n'
        if any(l.startswith('#EXT-X-STREAM-INF') for l in lines):
            return self._rewrite_master(lines, source_url, depth)
        pre, entries, trailer = self._split(lines)
        if not entries:
            return '\n'.join(self._rewrite_tag(l, source_url) for l in lines) + '\n'
        is_img = self._is_image_stream(entries, source_url)
        anchors, strength = self._resolve_anchors(entries, source_url, is_img, pre)
        ctx = {'path': lambda u: self._path(u, source_url), 'anchors': anchors, 'median': None}
        durs = sorted(e['dur'] for e in entries
                      if e.get('dur') and (not anchors or any(ctx['path'](e['url']).startswith(a) for a in anchors)))
        ctx['median'] = durs[len(durs) // 2] if durs else None
        last_idx = len(entries) - 1
        reasons, kept = {}, []
        for i, e in enumerate(entries):
            r = self._decide(e, ctx, i == last_idx)
            if r:
                reasons[r] = reasons.get(r, 0) + 1
            else:
                kept.append(e)
        removed = len(entries) - len(kept)
        if removed:
            if (not kept) or (removed * 2 >= len(entries)):
                self._log({'stage': 'clean', 'fallback': 'no_filter', 'removed': removed,
                           'kept': len(kept), 'anchor': anchors, 'strength': strength, 'reasons': reasons})
                return '\n'.join(self._rewrite_tag(l, source_url) for l in lines) + '\n'
            self._log({'stage': 'clean', 'removed': removed, 'kept': len(kept),
                       'anchor': anchors, 'strength': strength, 'image': is_img, 'reasons': reasons})
        out = [t for t in pre if t.split(':')[0] in _GLOBAL_TAGS]
        if not out or out[0] != '#EXTM3U':
            out.insert(0, '#EXTM3U')
        cur_key, cur_map = self._initial_state(pre)
        emit_key, emit_map = None, None
        for e in entries:
            k, m = self._scan_state(e['tags'])
            if k is not None:
                cur_key = k
            if m is not None:
                cur_map = m
            if e not in kept:
                continue
            if cur_key and cur_key != emit_key:
                out.extend(self._rewrite_tag(t, source_url) for t in cur_key)
                emit_key = cur_key
            if cur_map and cur_map != emit_map:
                out.append(self._rewrite_tag(cur_map, source_url))
                emit_map = cur_map
            out.append(e['inf'])
            out.extend(self._rewrite_tag(t, source_url) for t in e['tags']
                       if not t.startswith(('#EXT-X-KEY', '#EXT-X-MAP', '#EXT-X-CUE-', '#EXT-X-SCTE35')))
            out.append(e['url'] if e['url'].startswith(('http://', 'https://')) else urljoin(source_url, e['url']))
        for t in trailer:
            if t.startswith(_GLOBAL_TAGS):
                out.append(self._rewrite_tag(t, source_url))
        if not any(t.startswith('#EXT-X-ENDLIST') for t in out) and any(t.startswith('#EXT-X-ENDLIST') for t in lines):
            out.append('#EXT-X-ENDLIST')
        return '\n'.join(self._dedup(out)) + '\n'

    def _decide(self, e, ctx, is_last):
        if e.get('cue'):
            return 'cue'
        p = ctx['path'](e['url'])
        if self.ad_dirs and any(p.startswith(d) for d in self.ad_dirs):
            return 'ad_dir'
        if ctx['anchors'] and not any(p.startswith(a) for a in ctx['anchors']):
            return 'off_anchor'
        dur, median = e.get('dur'), ctx.get('median')
        if median and dur is not None and not is_last:
            if dur > max(median * self.long_factor, self.long_floor):
                return 'long'
            if dur < min(2.0, median * 0.25):
                return 'short'
        return None

    @staticmethod
    def _scan_state(tags):
        key, mp = None, None
        for t in tags:
            if t.startswith('#EXT-X-KEY'):
                if key is None:
                    key = [t]
                else:
                    key.append(t)
            elif t.startswith('#EXT-X-MAP'):
                mp = t
        return key, mp

    @staticmethod
    def _initial_state(pre):
        key_lines, mp = [], None
        for t in pre:
            if t.startswith('#EXT-X-KEY'):
                if not key_lines or not key_lines[-1].startswith('#EXT-X-KEY'):
                    key_lines = [t]
                else:
                    key_lines.append(t)
            elif t.startswith('#EXT-X-MAP'):
                mp = t
        return (key_lines or None), mp

    def _rewrite_master(self, lines, source_url, depth):
        out = []
        for line in lines:
            if line.startswith('#'):
                if 'URI="' in line:
                    def repl(m):
                        uri = m.group(1)
                        full = uri if uri.startswith(('http://', 'https://')) else urljoin(source_url, uri)
                        if '.m3u8' in full.lower() and depth < self.max_depth:
                            return 'URI="' + self.proxy_url(full, depth + 1) + '"'
                        return 'URI="' + full + '"'
                    line = re.sub(r'URI="([^"]+)"', repl, line)
                out.append(line)
                continue
            child = line if line.startswith(('http://', 'https://')) else urljoin(source_url, line)
            if '.m3u8' in child.lower() and depth < self.max_depth:
                out.append(self.proxy_url(child, depth + 1))
            else:
                out.append(child)
        return '\n'.join(out) + '\n'

    def _rewrite_tag(self, line, source_url):
        if 'URI="' in line:
            def repl(m):
                uri = m.group(1)
                if uri.startswith(('http://', 'https://')):
                    return 'URI="' + uri + '"'
                return 'URI="' + urljoin(source_url, uri) + '"'
            return re.sub(r'URI="([^"]+)"', repl, line)
        if line and not line.startswith('#'):
            return line if line.startswith(('http://', 'https://')) else urljoin(source_url, line)
        return line

    @staticmethod
    def _dedup(lines):
        noise = ('#EXT-X-DISCONTINUITY', '#EXT-X-KEY:METHOD=NONE')
        out = []
        for i, line in enumerate(lines):
            if line in noise:
                prev = out[-1] if out else ''
                nxt = lines[i + 1] if i + 1 < len(lines) else ''
                if prev in noise or not nxt or nxt.startswith('#EXT-X-ENDLIST'):
                    continue
            out.append(line)
        while len(out) > 1 and out[-1] in noise:
            out.pop()
        return out

    def local_proxy(self, param):
        try:
            target, depth = self._parse_param(param)
            if not target or not re.match(r'^https?://', target, re.I):
                return [400, 'text/plain', 'invalid url']
            content = self._fetch(target, timeout=20)
            if not content:
                p = urlparse(target)
                content = self._fetch(target, timeout=20, referer=p.scheme + '://' + p.netloc + '/')
            if not content:
                return [502, 'text/plain', 'fetch failed']
            head = content[:1024].lstrip(b'\xef\xbb\xbf').lstrip()
            if not head.startswith(b'#EXTM3U'):
                return [200, 'application/octet-stream', content]
            text = content.decode('utf-8', 'ignore')
            body = self.clean(text, target, depth).encode('utf-8')
            return [200, 'application/vnd.apple.mpegurl', body]
        except Exception as e:
            self._log({'stage': 'localProxy', 'error': type(e).__name__})
            return [500, 'text/plain', 'proxy error']

    @staticmethod
    def _parse_param(param):
        raw = {}
        if isinstance(param, dict):
            raw = dict(param)
        else:
            s = str(param or '').lstrip('?')
            for kv in s.split('&'):
                if '=' in kv:
                    k, v = kv.split('=', 1)
                    raw[k] = v
        target = raw.get('url') or raw.get('source') or ''
        if isinstance(target, str) and '%' in target:
            target = unquote(target)
        try:
            depth = int(raw.get('d') or 0)
        except Exception:
            depth = 0
        return target, depth


class Spider(BaseSpider):
    # 站点真实分类（写源时一次性内联，运行时不读外部文件）
    _CLASSES = [
                {
                        "type_id": "ou-mei-jin-bao",
                        "type_name": "欧美劲爆"
                },
                {
                        "type_id": "lun-li-ying-pian",
                        "type_name": "伦理影片"
                },
                {
                        "type_id": "zi-pai-tou-pai",
                        "type_name": "自拍偷拍"
                },
                {
                        "type_id": "ri-han-wu-ma",
                        "type_name": "日韩无码"
                },
                {
                        "type_id": "cheng-ren-dong-man",
                        "type_name": "成人动漫"
                },
                {
                        "type_id": "ri-han-jing-pin",
                        "type_name": "日韩精品"
                },
                {
                        "type_id": "guo-chan-zhu-bo",
                        "type_name": "国产主播"
                },
                {
                        "type_id": "zi-wei-xi-lie",
                        "type_name": "自慰系列"
                },
                {
                        "type_id": "kou-jiao-shi-pin",
                        "type_name": "口交视频"
                },
                {
                        "type_id": "jiao-shi-xue-sheng",
                        "type_name": "教师学生"
                },
                {
                        "type_id": "yan-she-xi-lie",
                        "type_name": "颜射系列"
                },
                {
                        "type_id": "ju-ru-you-wu",
                        "type_name": "巨乳尤物"
                },
                {
                        "type_id": "qun-p-huan-qi",
                        "type_name": "群P换妻"
                },
                {
                        "type_id": "ai-huan-lian",
                        "type_name": "AI换脸"
                },
                {
                        "type_id": "av-ming-xing",
                        "type_name": "AV明星"
                },
                {
                        "type_id": "av-jie-shuo",
                        "type_name": "AV解说"
                },
                {
                        "type_id": "zhong-wen-zi-mu",
                        "type_name": "中文字幕"
                },
                {
                        "type_id": "sm-zhong-wei",
                        "type_name": "SM重味"
                },
                {
                        "type_id": "qiang-jian-luan-lun",
                        "type_name": "强奸乱伦"
                },
                {
                        "type_id": "ren-qi-xi-lie",
                        "type_name": "人妻系列"
                },
                {
                        "type_id": "zhi-fu-you-huo",
                        "type_name": "制服诱惑"
                },
                {
                        "type_id": "shu-nv-shao-fu",
                        "type_name": "熟女少妇"
                },
                {
                        "type_id": "chi-gua-hei-liao",
                        "type_name": "吃瓜黑料"
                },
                {
                        "type_id": "yan-zhi-zheng-yi",
                        "type_name": "颜值正义"
                },
                {
                        "type_id": "guo-chan-chuan-mei",
                        "type_name": "国产传媒"
                },
                {
                        "type_id": "jiu-dian-tan-hua",
                        "type_name": "酒店探花"
                },
                {
                        "type_id": "zhi-bo-luo-liao",
                        "type_name": "直播裸聊"
                },
                {
                        "type_id": "fan-cha-mu-gou",
                        "type_name": "反差母狗"
                },
                {
                        "type_id": "jia-ting-luan-lun",
                        "type_name": "家庭乱伦"
                },
                {
                        "type_id": "tou-qing-shao-fu",
                        "type_name": "偷情少妇"
                },
                {
                        "type_id": "bai-he-nv-tong",
                        "type_name": "百合女同"
                },
                {
                        "type_id": "sm-tiao-jiao",
                        "type_name": "SM调教"
                },
                {
                        "type_id": "lu-guan-bi-kan",
                        "type_name": "撸管必看"
                },
                {
                        "type_id": "ye-zhan-che-zhen",
                        "type_name": "野战车震"
                },
                {
                        "type_id": "xue-sheng-kong-jie",
                        "type_name": "学生空姐"
                }
        ]

    def __init__(self):
        self.extend = ''
        self.host = 'https://jfdxl.dfjxlw02.lol'
        self.base = self.host + '/dfjxl'
        self.classes = list(self._CLASSES)
        self.filters = {}
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14; 22127RK46C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
            'Referer': self.base + '/',
            'Accept-Encoding': 'gzip, deflate',
        }
        self.adf = None
        # 锚点留空 -> 由 M3U8AdFilter 按当前流自动推导（各视频目录不同，硬编码会失效）
        self._anchor = []
        # 实测高频插片目录（跨视频重复出现，可安全作黑名单）
        self._ad_dirs = ['/20261009/RCP0FQBQ/9622kb/hls/']

    def getName(self):
        return '打飞机训练'

    def getDependence(self):
        return []

    def init(self, extend=''):
        # 零网络：动态域名探测不放这里
        self.extend = extend or ''
        self.adf = M3U8AdFilter(spider=self, need_clean=True,
                                ad_dirs=self._ad_dirs, anchor_dirs=self._anchor,
                                logger=self.log)

    def isVideoFormat(self, url):
        return bool(url) and ('.m3u8' in url or '.mp4' in url)

    def manualVideoCheck(self):
        return False

    def _get(self, url, timeout=15):
        try:
            r = self.fetch(url, headers=self.headers, timeout=timeout)
        except Exception as e:
            self.log({'fetch': 'exception', 'error': type(e).__name__})
            return ''
        if not r or getattr(r, 'status_code', 0) != 200:
            return ''
        text = getattr(r, 'text', None)
        if text is None:
            c = getattr(r, 'content', b'') or b''
            text = c.decode('utf-8', 'ignore') if isinstance(c, bytes) else str(c)
        return text or ''

    @staticmethod
    def _norm_ids(ids):
        if ids is None:
            return ''
        if isinstance(ids, (list, tuple)):
            if not ids:
                return ''
            ids = ids[0]
        if isinstance(ids, bytes):
            ids = ids.decode('utf-8', 'ignore')
        return str(ids).strip()

    @staticmethod
    def _parse_cards(html):
        """锚点式解析：以 div.post-item 为锚，后开 900 字符窗口取字段。
        同一 vid 只取首次命中。"""
        out, seen = [], set()
        if not html:
            return out
        for m in re.finditer(r'<div class="post-item">', html):
            seg = html[m.end(): m.end() + 900]
            a = re.search(r'<a\s+href="([^"]+)"\s+class="post-link"', seg)
            if not a:
                a = re.search(r'<a[^>]*class="post-link"[^>]*href="([^"]+)"', seg)
            if not a:
                continue
            mm = re.search(r'/dfjxl/v/([a-z0-9]+)/', a.group(1))
            if not mm:
                continue
            vid = mm.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            pic, title = '', ''
            img = re.search(r'<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"', seg)
            if img:
                pic, title = img.group(1), img.group(2)
            else:
                img = re.search(r'<img[^>]*alt="([^"]*)"[^>]*src="([^"]+)"', seg)
                if img:
                    title, pic = img.group(1), img.group(2)
            out.append({'vod_id': vid, 'vod_name': title, 'vod_pic': pic, 'vod_remarks': ''})
        return out

    @staticmethod
    def _pagecount(html, default=9999):
        """从 page-numbers 提取最大页码；取不到用大默认值。"""
        nums = re.findall(r'class="page-numbers"[^>]*href="[^"]*/page/(\d+)/"', html or '')
        if not nums:
            nums = re.findall(r'/page/(\d+)/', html or '')
        try:
            return max(int(n) for n in nums) if nums else default
        except Exception:
            return default

    def homeContent(self, filter):
        # 零网络
        return {'class': self.classes, 'filters': self.filters if filter else {}}

    def getHomeContent(self, filter):
        return self.homeContent(filter)

    def homeVideoContent(self):
        html = self._get(self.base + '/')
        return {'list': self._parse_cards(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page = str(pg or '1')
        slug = str(tid or '').strip()
        if not slug:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 12, 'total': 0}
        if page == '1':
            url = '%s/vt/%s/' % (self.base, slug)
        else:
            url = '%s/vt/%s/page/%s/' % (self.base, slug, page)
        html = self._get(url)
        items = self._parse_cards(html)
        pc = self._pagecount(html)
        try:
            pn = int(page)
        except Exception:
            pn = 1
        return {'list': items, 'page': pn, 'pagecount': pc, 'limit': 12, 'total': pc * 12}

    def searchContent(self, key, quick, pg='1'):
        page = str(pg or '1')
        kw = quote(str(key or ''), safe='')
        if page == '1':
            url = '%s/?s=%s' % (self.base, kw)
        else:
            url = '%s/page/%s/?s=%s' % (self.base, page, kw)
        html = self._get(url)
        items = self._parse_cards(html)
        try:
            pn = int(page)
        except Exception:
            pn = 1
        return {'list': items, 'page': pn}

    def _extract_play(self, html):
        """L2 播放器变量：平衡括号切出 video:{...}，取 url。"""
        if not html:
            return ''
        m = re.search(r'video\s*:\s*\{', html)
        if not m:
            return ''
        start = m.end() - 1
        bal, end = 0, -1
        limit = min(start + 3000, len(html))
        for j in range(start, limit):
            ch = html[j]
            if ch == '{':
                bal += 1
            elif ch == '}':
                bal -= 1
                if bal == 0:
                    end = j + 1
                    break
        block = html[start:end] if end > start else ''
        if not block:
            return ''
        mm = re.search(r'url\s*:\s*([\'\"])(.*?)\1', block, re.S)
        if not mm:
            return ''
        return mm.group(2).replace('\\/', '/').strip()

    def _find_pic(self, vid):
        """详情页无封面时，回查分类页与首页补图。最多试 3 个来源。"""
        if not vid:
            return ''
        tid = ''
        html_detail = self._get('%s/v/%s/' % (self.base, vid))
        if html_detail:
            act = re.findall(r'class="nav-item active"[^>]*href="([^"]+)"', html_detail)
            if act:
                m = re.search(r'/vt/([a-z0-9\-]+)/', act[0])
                if m:
                    tid = m.group(1)
        targets = []
        if tid:
            targets.append('%s/vt/%s/' % (self.base, tid))
        targets.append(self.base + '/')
        targets.append('%s/vt/%s/page/2/' % (self.base, tid) if tid else '')
        for u in targets:
            if not u:
                continue
            html = self._get(u)
            if not html:
                continue
            for m in re.finditer(r'<div class="post-item">', html):
                seg = html[m.end(): m.end() + 900]
                if vid not in seg:
                    continue
                img = re.search(r'<img[^>]*src="([^"]+)"', seg)
                if img and img.group(1).startswith('http'):
                    return img.group(1)
        return ''

    def detailContent(self, ids):
        raw = self._norm_ids(ids)
        if not raw:
            return {'list': []}
        vid = raw.split('|$|')[0].split('$')[0].strip()
        if not vid:
            return {'list': []}
        url = '%s/v/%s/' % (self.base, vid)
        html = self._get(url)
        title, pic, content = '', '', ''
        if html:
            h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
            if h1:
                title = re.sub(r'<[^>]+>', '', h1.group(1)).strip()
            if not title:
                t = re.search(r'<title>(.*?)</title>', html, re.S)
                if t:
                    title = re.sub(r'\s*[\-\u2013|]\s*[^-<]*$', '', t.group(1)).strip()
            for sel in (r'<img[^>]*class="[^"]*post-image[^"]*"[^>]*src="([^"]+)"',
                        r'<img[^>]*src="(https?://[^"]+\.(?:jpg|png|webp))"'):
                m = re.search(sel, html)
                if m:
                    pic = m.group(1)
                    break
            m = re.search(r'<div[^>]*class="[^"]*(?:video-desc|video-info|content)[^"]*"[^>]*>(.*?)</div>', html, re.S)
            if m:
                content = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not pic:
            pic = self._find_pic(vid)
        play = self._extract_play(html)
        vod = {
            'vod_id': raw,
            'vod_name': title or '未知标题',
            'vod_pic': pic,
            'vod_remarks': '',
            'vod_content': content,
            'vod_play_from': '默认线路',
            'vod_play_url': '正片$' + (play or url).replace('$', '|'),
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        pid = str(id or '').strip()
        if not pid:
            return {'parse': 1, 'url': '', 'header': self.headers}
        target = pid
        if not re.match(r'^https?://', target, re.I):
            html = self._get('%s/v/%s/' % (self.base, target))
            target = self._extract_play(html)
        if not target or not re.match(r'^https?://', target, re.I):
            return {'parse': 1, 'url': '%s/v/%s/' % (self.base, pid), 'header': self.headers}
        if '.m3u8' in target.lower():
            if self.adf is None:
                self.adf = M3U8AdFilter(spider=self, need_clean=True,
                                        ad_dirs=self._ad_dirs, anchor_dirs=self._anchor,
                                        logger=self.log)
            return {'parse': 0, 'url': self.adf.proxy_url(target), 'header': {}}
        return {'parse': 0, 'url': target, 'header': {'User-Agent': self.headers['User-Agent']}}

    def recommendContent(self, ids, pg='1'):
        vid = self._norm_ids(ids).split('|$|')[0].split('$')[0].strip()
        if not vid:
            return {'list': []}
        html = self._get('%s/v/%s/' % (self.base, vid))
        cards = self._parse_cards(html)
        return {'list': [c for c in cards if c['vod_id'] != vid][:12]}

    def localProxy(self, param):
        if self.adf is None:
            self.adf = M3U8AdFilter(spider=self, need_clean=True,
                                    ad_dirs=self._ad_dirs, anchor_dirs=self._anchor,
                                    logger=self.log)
        return self.adf.local_proxy(param)

    def destroy(self):
        self.adf = None
        self.classes = []

