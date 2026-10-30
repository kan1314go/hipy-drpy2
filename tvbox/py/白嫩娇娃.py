# coding: utf-8
import re
import base64
import posixpath
from urllib.parse import quote, unquote, urlparse, urljoin, parse_qsl

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def __init__(self):
        self.extend = ''
        self.host = 'https://Peace.bnnjw90.cfd'
        self._host_candidates = [
            'https://Peace.bnnjw90.cfd',
            'https://Light.bnjw22.cc',
        ]
        self._cached_host = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14; 22127RK46C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36',
            'Referer': self.host + '/',
            'Accept-Encoding': 'gzip, deflate',
        }
        self.classes = self._CLASSES
        self.filters = {}
        self._ad_filter = None


    _CLASSES = [
        {"type_id": "9177581", "type_name": "".join(chr(x) for x in [31934,21697,25512,33616])},
        {"type_id": "9187581", "type_name": "".join(chr(x) for x in [22269,20135,20256,23186])},
        {"type_id": "9197581", "type_name": "".join(chr(x) for x in [25506,33457,31995,21015])},
        {"type_id": "9207581", "type_name": "".join(chr(x) for x in [20599,25293,33258,25293])},
        {"type_id": "9217581", "type_name": "".join(chr(x) for x in [29087,22899,23569,22919])},
        {"type_id": "9227581", "type_name": "".join(chr(x) for x in [26080,30721,19987,21306])},
        {"type_id": "9237581", "type_name": "".join(chr(x) for x in [27431,32654,24615,29233])},
        {"type_id": "9247581", "type_name": "".join(chr(x) for x in [39068,20540,27491,20041])},
        {"type_id": "9477611", "type_name": "".join(chr(x) for x in [31934,21697,32593,32418])},
        {"type_id": "9277591", "type_name": "".join(chr(x) for x in [32654,20083,24040,20083])},
        {"type_id": "9287591", "type_name": "".join(chr(x) for x in [32593,26333,20107,20214])},
        {"type_id": "9297591", "type_name": "".join(chr(x) for x in [22269,20135,20027,25773])},
        {"type_id": "9307591", "type_name": "".join(chr(x) for x in [20013,25991,23383,24149])},
        {"type_id": "9317591", "type_name": "".join(chr(x) for x in [21046,26381,19997,34972])},
        {"type_id": "9327591", "type_name": "".join(chr(x) for x in [21475,20132,33258,24944])},
        {"type_id": "9337591", "type_name": "".join(chr(x) for x in [22269,20135,31934,21697])},
        {"type_id": "9347591", "type_name": "".join(chr(x) for x in [22823,31168,35270,39057])},
        {"type_id": "9487611", "type_name": "".join(chr(x) for x in [22810,20154,32676,20132])},
        {"type_id": "9377601", "type_name": "".join(chr(x) for x in [20122,27954,24773,33394])},
        {"type_id": "9387601", "type_name": "".join(chr(x) for x in [24378,22904,20081,20262])},
        {"type_id": "9397601", "type_name": "".join(chr(x) for x in [20262,29702,19977,32423])},
        {"type_id": "9407601", "type_name": "".join(chr(x) for x in [22899,21516,24615,24651])},
        {"type_id": "9417601", "type_name": "".join(chr(x) for x in [26126,26143,25442,33080])},
        {"type_id": "9427601", "type_name": "".join(chr(x) for x in [65,32,86,32,35299,35828])},
        {"type_id": "9437601", "type_name": "".join(chr(x) for x in [23569,22899,33821,33673])},
        {"type_id": "9447601", "type_name": "".join(chr(x) for x in [35282,33394,21095,24773])},
        {"type_id": "9497611", "type_name": "".join(chr(x) for x in [83,32,77,32,35843,25945])},
    ]

    # ---------- 基础信息 ----------
    def getName(self):
        return 'bnjw'

    def getDependence(self):
        return []

    def init(self, extend=''):
        self.extend = extend or ''

    def destroy(self):
        self._cached_host = None

    # ---------- host 选择（懒加载，带缓存） ----------
    def _pick_host(self):
        if self._cached_host:
            return self._cached_host
        for h in self._host_candidates:
            try:
                r = self.fetch(h + '/', headers=self.headers, timeout=10)
                if r and getattr(r, 'status_code', 0) == 200 and len(getattr(r, 'content', b'') or b'') > 500:
                    self._cached_host = h
                    self.host = h
                    self.headers['Referer'] = h + '/'
                    return h
            except Exception:
                continue
        self._cached_host = self._host_candidates[0]
        return self._cached_host

    # ---------- AES-GCM 解包 ----------
    @staticmethod
    def _b64d(x):
        x = x.replace('-', '+').replace('_', '/')
        pad = (-len(x)) % 4
        return base64.b64decode(x + '=' * pad)

    @staticmethod
    def _find_arrays(s):
        out = {}
        for m in re.finditer(r'(\w+)\s*=\s*\[\[', s):
            name = m.group(1)
            start = m.end() - 2
            depth = 0
            i = start
            while i < len(s):
                if s[i] == '[':
                    depth += 1
                elif s[i] == ']':
                    depth -= 1
                    if depth == 0:
                        out[name] = s[start:i + 1]
                        break
                i += 1
        return out

    def _arr_to_bytes(self, arr_text):
        items = re.findall(r'\[\s*(\d+)\s*,\s*"([^"]*)"\s*\]', arr_text)
        items.sort(key=lambda x: int(x[0]))
        b64 = ''.join(v for _, v in items)
        return self._b64d(b64)

    def _unwrap(self, html):
        if not html or '<script' not in html:
            return html
        m = re.search(r'<script[^>]*>(.*?)</script>', html, re.S)
        if not m:
            return html
        s = m.group(1)
        if 'AES-GCM' not in s:
            return html
        if AES is None:
            return html
        try:
            arrays = self._find_arrays(s)
            dec_m = re.search(r'decrypt\(\{name:"AES-GCM",iv:\w+\([^)]*\(\s*(\w+)\s*\)[^)]*\),additionalData:\w+\([^)]*\(\s*(\w+)\s*\)[^)]*\),tagLength:128\},\s*\w+\s*,\s*\w+\([^)]*\(\s*(\w+)\s*\)[^)]*\)\)', s)
            key_m = re.search(r'atob\(s\),c=>c\.charCodeAt\(0\)\);\s*const\s+\w+\s*=\s*\w+\([^)]*\(\s*(\w+)\s*\)[^)]*\),\s*\w+\s*=\s*\w+\([^)]*\(\s*(\w+)\s*\)[^)]*\)', s)
            if not dec_m or not key_m:
                return html
            iv_name, aad_name, ct_name = dec_m.groups()
            ka, kb = key_m.groups()
            if not all(n in arrays for n in (ka, kb, iv_name, aad_name, ct_name)):
                return html
            k1 = self._arr_to_bytes(arrays[ka])
            k2 = self._arr_to_bytes(arrays[kb])
            if len(k1) != 32 or len(k2) != 32:
                return html
            key = bytes(a ^ b for a, b in zip(k1, k2))
            iv = self._arr_to_bytes(arrays[iv_name])
            aad = self._arr_to_bytes(arrays[aad_name])
            ct = self._arr_to_bytes(arrays[ct_name])
            if len(ct) < 16:
                return html
            tag, body = ct[-16:], ct[:-16]
            cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
            cipher.update(aad)
            pt = cipher.decrypt_and_verify(body, tag)
            return pt.decode('utf-8', errors='ignore')
        except Exception:
            return html

    def _get_html(self, url):
        try:
            r = self.fetch(url, headers=self.headers, timeout=15)
            if not r or getattr(r, 'status_code', 0) != 200:
                return ''
            text = getattr(r, 'text', '') or ''
            if not text:
                raw = getattr(r, 'content', b'') or b''
                text = raw.decode('utf-8', errors='ignore')
            return self._unwrap(text)
        except Exception:
            return ''

    # ---------- 列表锚点式解析 ----------
    def _parse_list(self, html):
        items = []
        seen = set()
        for m in re.finditer(r'<a\s+href=["\']/video\.php\?id=(\d+)["\'][^>]*>', html):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            window = html[m.end():m.end() + 1500]
            pic = ''
            pm = re.search(r"background-image:\s*url\(['\"]?([^'\")]+)", window)
            if pm:
                pic = pm.group(1).strip()
            name = ''
            nm = re.search(r'<a[^>]*class=["\']tuzi["\'][^>]*>(.*?)</a>', window, re.S)
            if nm:
                name = re.sub(r'<[^>]+>', '', nm.group(1)).strip()
            if not name:
                continue
            packed = vid + '|$|' + name + '|$|' + pic
            items.append({'vod_id': packed, 'vod_name': name, 'vod_pic': pic, 'vod_remarks': ''})
        return items

    # ---------- 5 大接口 ----------
    def homeContent(self, filter):
        return {'class': self.classes, 'filters': self.filters if filter else {}}

    def getHomeContent(self, filter):
        return self.homeContent(filter)

    def homeVideoContent(self):
        host = self._pick_host()
        html = self._get_html(host + '/')
        return {'list': self._parse_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page = str(pg or '1')
        host = self._pick_host()
        url = '%s/list.php?id=%s&page=%s' % (host, tid, page)
        html = self._get_html(url)
        items = self._parse_list(html)
        return {'list': items, 'page': int(page), 'pagecount': 9999, 'limit': 20, 'total': 999999}

    def searchContent(self, key, quick, pg='1'):
        host = self._pick_host()
        url = '%s/search.php?s=&content=%s' % (host, quote(key, safe=''))
        html = self._get_html(url)
        return {'list': self._parse_list(html), 'page': int(pg or '1')}

    def recommendContent(self, ids, pg='1'):
        return {'list': []}

    @staticmethod
    def _norm_ids(ids):
        if ids is None:
            return ''
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ''
        if isinstance(ids, bytes):
            ids = ids.decode('utf-8', errors='ignore')
        return str(ids).strip()

    def _skeleton(self, vid, title='', pic='', remarks=''):
        pid = str(vid).split('|$|')[0].replace('$', '|')
        return {'list': [{
            'vod_id': vid, 'vod_name': title or '视频', 'vod_pic': pic or '',
            'vod_remarks': remarks, 'vod_content': '',
            'vod_play_from': '默认', 'vod_play_url': '默认$' + pid,
        }]}

    def detailContent(self, ids):
        raw = self._norm_ids(ids)
        if not raw:
            return {'list': []}
        try:
            ps = raw.split('|$|')
            vid = ps[0]
            old_name = ps[1] if len(ps) > 1 else ''
            old_pic = ps[2] if len(ps) > 2 else ''
            host = self._pick_host()
            html = self._get_html('%s/video.php?id=%s' % (host, vid))
            if not html:
                return self._skeleton(raw, old_name, old_pic)
            name = old_name
            if not name:
                nm = re.search(r'<h3>.*?:\s*(.*?)</h3>', html, re.S)
                if nm:
                    name = re.sub(r'<[^>]+>', '', nm.group(1)).strip()
            if not name:
                tm = re.search(r'<title[^>]*>(.*?)</title>', html, re.S)
                if tm:
                    name = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
            m3u8 = ''
            mm = re.search(r'loadSource\(["\']([^"\']+\.m3u8[^"\']*)', html)
            if not mm:
                mm = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
            if mm:
                m3u8 = mm.group(1) if mm.groups() else mm.group(0)
            pic = old_pic
            if not pic:
                pm = re.search(r'poster=["\']([^"\']+)["\']', html)
                if pm:
                    pic = pm.group(1)
                if not pic:
                    # 从详情页封面区再取一次
                    pm2 = re.search(r"background-image:\s*url\(['\"]?([^'\")]+)", html)
                    if pm2:
                        pic = pm2.group(1).strip()
            if not m3u8:
                return self._skeleton(raw, name, pic)
            return {'list': [{
                'vod_id': raw, 'vod_name': name, 'vod_pic': pic,
                'vod_remarks': '', 'vod_content': '',
                'vod_play_from': '默认',
                'vod_play_url': '正片$' + m3u8.replace('$', '|'),
            }]}
        except Exception as e:
            self.log('detail_err ' + type(e).__name__)
            return self._skeleton(raw)

    def playerContent(self, flag, id, vipFlags):
        play_id = str(id or '').replace('|', '$')
        if not play_id:
            return {'parse': 1, 'url': '', 'header': self.headers}
        if play_id.endswith('.m3u8'):
            proxy = self.getProxyUrl() + '&url=' + quote(play_id, safe='')
            return {'parse': 0, 'url': proxy, 'header': self.headers}
        if play_id.endswith(('.mp4', '.flv')):
            return {'parse': 0, 'url': play_id, 'header': self.headers}
        return {'parse': 1, 'url': play_id, 'header': self.headers}

    def _get_ad_filter(self):
        if self._ad_filter is None:
            self._ad_filter = M3U8AdFilter(
                spider=self, need_clean=True,
                ad_dirs=None, anchor_dirs=None,
                logger=None,
            )
        return self._ad_filter

    def localProxy(self, param):
        try:
            return self._get_ad_filter().local_proxy(param)
        except Exception as e:
            self.log('localProxy_err ' + type(e).__name__)
            return [500, 'text/plain', b'proxy error']





VIDEO_EXT = ('.ts', '.m4s', '.mp4', '.aac', '.m4a', '.cmfv', '.cmfa', '.m4v')
IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.avif')
_GLOBAL_TAGS = (
    '#EXTM3U', '#EXT-X-VERSION', '#EXT-X-TARGETDURATION', '#EXT-X-MEDIA-SEQUENCE',
    '#EXT-X-DISCONTINUITY-SEQUENCE', '#EXT-X-PLAYLIST-TYPE', '#EXT-X-INDEPENDENT-SEGMENTS',
    '#EXT-X-START', '#EXT-X-I-FRAMES-ONLY',
)


class M3U8AdFilter(object):
    """m3u8 广告分片过滤器。spider 只需提供 getProxyUrl() 与 fetch()。"""

    def __init__(self, spider=None, need_clean=True, ad_dirs=None, anchor_dirs=None,
                 min_coverage=0.30, long_factor=3.0, long_floor=25.0,
                 max_depth=2, logger=None):
        self.spider = spider
        self.need_clean = bool(need_clean)
        # 已知广告目录 / 已知正片目录（都可为空，留空则动态推导）
        self.ad_dirs = [self._norm_dir(d) for d in (ad_dirs or []) if d]
        self.anchor_dirs = [self._norm_dir(d) for d in (anchor_dirs or []) if d]
        self.min_coverage = float(min_coverage)   # 目录覆盖率门槛
        self.long_factor = float(long_factor)     # 长片判据倍数
        self.long_floor = float(long_floor)       # 长片判据秒数下限
        self.max_depth = int(max_depth)           # 主表/子表递归上限
        self.logger = logger

    # ================= 接入适配层 =================
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
        for name in ('headers', '_headers'):
            h = getattr(sp, name, None)
            if isinstance(h, dict):
                headers.update(h)
                break
        if referer:
            headers.setdefault('Referer', referer)
            headers.setdefault('Origin', referer.split('/', 3)[0] + '//' + referer.split('/', 3)[2])
        fn = getattr(sp, 'fetch', None)
        if not callable(fn):
            return b''
        resp = None
        try:
            resp = fn(url, headers=headers, timeout=timeout)
        except Exception as e:
            # SSLError：部分 CDN 证书链不完整，宿主默认验证会失败。
            # 降级为不验证证书重试（先 requests，再 urllib），仅此异常类型触发。
            if type(e).__name__ == 'SSLError':
                try:
                    import requests as _rq
                    import urllib3 as _u3
                    _u3.disable_warnings()
                    resp = _rq.get(url, headers=headers, timeout=timeout, verify=False)
                except Exception:
                    resp = None
                if resp is None:
                    try:
                        import ssl as _ssl
                        import urllib.request as _ur
                        ctx = _ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = _ssl.CERT_NONE
                        _x = _ur.urlopen(_ur.Request(url, headers=headers), timeout=timeout, context=ctx)
                        _b = _x.read()

                        class _R(object):
                            pass

                        resp = _R()
                        resp.content = _b
                    except Exception:
                        return b''
            else:
                return b''
        if resp is None:
            return b''
        content = getattr(resp, 'content', None)
        if content is None:
            content = getattr(resp, 'text', None)
        if isinstance(content, str):
            content = content.encode('utf-8', 'ignore')
        return content or b''

    # ================= 工具 =================
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
        """生成代理地址。已编码字符不再二次编码，避免签名 URL 失效。"""
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

    # ================= 取证（第 0 步）=================
    def probe(self, text, source_url):
        """不上代理也能先看清结构：返回证据 dict，据此决定 need_clean。"""
        lines = self._lines(text)
        evidence = {
            'segment_count': 0, 'is_multi_bitrate': False, 'is_fake_image_stream': False,
            'dirs': {}, 'key_uris': [], 'suspicious_ad_dirs': [], 'anchor_dirs': [],
            'dur_median': None, 'cue_segments': 0,
        }
        if any(l.startswith('#EXT-X-STREAM-INF') for l in lines):
            evidence['is_multi_bitrate'] = True
            evidence['sub_streams'] = [l for l in lines if not l.startswith('#') and '.m3u8' in l.lower()]
        pre, entries, _ = self._split(lines)
        evidence['segment_count'] = len(entries)
        if not entries:
            return evidence

        counter = self._dir_counter(entries, source_url)
        evidence['dirs'] = dict(sorted(counter.items(), key=lambda kv: -kv[1]))
        total = len(entries) or 1
        evidence['is_fake_image_stream'] = self._is_image_stream(entries, source_url)
        evidence['key_uris'] = [self._tag_uri(t) for t in pre + [x for e in entries for x in e['tags']]
                                if t.startswith(('#EXT-X-KEY', '#EXT-X-MAP')) and 'URI=' in t]
        evidence['cue_segments'] = sum(1 for e in entries if e.get('cue'))
        anchors, strength = self._resolve_anchors(entries, source_url, evidence['is_fake_image_stream'], pre)
        evidence['anchor_dirs'] = anchors
        evidence['anchor_strength'] = strength
        evidence['suspicious_ad_dirs'] = [d for d, c in counter.items()
                                          if d not in anchors and not any(d.startswith(a) for a in anchors)]
        durs = sorted(e['dur'] for e in entries
                      if e.get('dur') and any(self._path(e['url'], source_url).startswith(a) for a in anchors))
        evidence['dur_median'] = durs[len(durs) // 2] if durs else None
        evidence['need_clean'] = bool(evidence['suspicious_ad_dirs'] or evidence['is_fake_image_stream']
                                      or evidence['cue_segments'])
        return evidence

    @staticmethod
    def _tag_uri(tag):
        m = re.search(r'URI="([^"]+)"', tag or '')
        return m.group(1) if m else ''

    # ================= 解析 =================
    @staticmethod
    def _lines(text):
        return [l.strip() for l in str(text or '').replace('\r', '').split('\n') if l.strip()]

    def _split(self, lines):
        """拆成 (头部全局标签, 分片条目, 尾部标签)。

        关键点：分片之间出现的标签（KEY / MAP / DISCONTINUITY / CUE）属于**下一条**分片，
        不能丢到尾部，否则中途换 KEY 的流会整段解不开。
        """
        pre, entries, pending = [], [], []
        cur_inf, cur_tags = None, []
        cue_on = False
        seen_entry = False

        for line in lines:
            if line.startswith('#'):
                if line.startswith('#EXTINF'):
                    if cur_inf is not None:          # 缺媒体行的残条，丢弃
                        cur_inf, cur_tags = None, []
                    cur_inf = line
                    continue
                if cur_inf is not None:              # EXTINF 之后的标签归本条分片
                    cur_tags.append(line)
                elif seen_entry:                     # 分片之间的标签归下一条分片
                    pending.append(line)
                else:                                # 首个 EXTINF 之前：全局头
                    pre.append(line)
                if line.startswith('#EXT-X-CUE-OUT'):
                    cue_on = True
                elif line.startswith('#EXT-X-CUE-IN'):
                    cue_on = False
                continue

            # 媒体行
            if cur_inf is None:
                pre.append(line)                     # 少见的伪 m3u：无 EXTINF 的裸地址
                continue
            entries.append({'dur': self._parse_duration(cur_inf), 'inf': cur_inf,
                            'tags': pending + cur_tags, 'url': line, 'cue': cue_on})
            seen_entry = True
            pending, cur_inf, cur_tags = [], None, []

        trailer = pending + cur_tags
        # cue 标记过半时不可信，整体作废（防止把正片当广告区间）
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
        """强证据：有图片后缀分片且无视频后缀分片。不做域名特征猜测。"""
        has_video = has_image = False
        for e in entries:
            p = self._path(e['url'], source_url).lower()
            if p.endswith(VIDEO_EXT):
                has_video = True
            elif p.endswith(IMAGE_EXT):
                has_image = True
        return has_image and not has_video

    def _resolve_anchors(self, entries, source_url, is_img, pre=None):
        """返回 (锚点目录列表, 强度)。强度: config/key/dir/weak/none"""
        if self.anchor_dirs:
            return self.anchor_dirs, 'config'
        if not entries:
            return [], 'none'
        total = len(entries)
        counter = self._dir_counter(entries, source_url)
        if not counter:
            return [], 'none'

        # 强锚点：KEY / MAP 目录。多条 KEY 时取覆盖分片最多的那条，
        # 否则广告段自带的 KEY 目录会被误当成锚点（把广告一起放行）。
        key_dirs = []
        tags_all = list(pre or []) + [t for e in entries for t in e['tags']]
        for t in tags_all:
            if t.startswith(('#EXT-X-KEY', '#EXT-X-MAP')) and 'URI=' in t:
                kp = self._path(self._tag_uri(t), source_url)
                kd = posixpath.dirname(kp)
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

        # 覆盖率锚点：以占比最高的目录为主锚点，
        # 同层数量不低于主目录一半的（分库正片）以及其子/父目录一并纳入。
        # 广告目录通常只占零头，不会进来；万一进来也是漏广告，不会误杀。
        top = max(counter.items(), key=lambda kv: kv[1])[0]
        topn = counter[top]
        anchors = [top]
        for d, c in counter.items():
            if d == top:
                continue
            if c * 2 > topn or d.startswith(top) or top.startswith(d):
                anchors.append(d)
        if anchors == [top] and topn * 2 < total:
            # 主目录都不到一半 -> 结构太散，退化为弱锚点
            return sorted(set(anchors)), 'weak'
        return sorted(set(anchors)), 'dir'

    # ================= 主入口 =================
    def clean(self, text, source_url, depth=0):
        lines = self._lines(text)
        if not lines:
            return '#EXTM3U\n'

        # 主表：子流改代理地址，音轨 / I-FRAME 的 URI 也要处理
        if any(l.startswith('#EXT-X-STREAM-INF') for l in lines):
            return self._rewrite_master(lines, source_url, depth)

        pre, entries, trailer = self._split(lines)
        if not entries:
            return '\n'.join(self._rewrite_tag(l, source_url) for l in lines) + '\n'

        is_img = self._is_image_stream(entries, source_url)
        anchors, strength = self._resolve_anchors(entries, source_url, is_img, pre)
        check = {'url': lambda u: self._path(u, source_url)}
        ctx = {'ad_dirs': self.ad_dirs, 'anchors': anchors, 'median': None,
               'path': check['url']}

        # 时长基线：只统计锚点内分片
        durs = sorted(e['dur'] for e in entries
                      if e.get('dur') and (not anchors or any(check['url'](e['url']).startswith(a) for a in anchors)))
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

        # 误杀保护：一条不留、或滤掉一半以上 -> 整体回退
        if removed:
            suspicious = (not kept) or (removed * 2 >= len(entries))
            if suspicious:
                self._log({'stage': 'clean', 'fallback': 'no_filter', 'removed': removed,
                           'kept': len(kept), 'anchor': anchors, 'strength': strength,
                           'reasons': reasons})
                return '\n'.join(self._rewrite_tag(l, source_url) for l in lines) + '\n'
            self._log({'stage': 'clean', 'removed': removed, 'kept': len(kept),
                       'anchor': anchors, 'strength': strength, 'image': is_img,
                       'reasons': reasons})

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
                continue                                  # 状态照样更新，只是不输出
            if cur_key and cur_key != emit_key:
                out.extend(self._rewrite_tag(t, source_url) for t in cur_key)
                emit_key = cur_key
            if cur_map and cur_map != emit_map:
                out.append(self._rewrite_tag(cur_map, source_url))
                emit_map = cur_map
            out.append(e['inf'])
            out.extend(self._rewrite_tag(t, source_url) for t in e['tags']
                       if not t.startswith(('#EXT-X-KEY', '#EXT-X-MAP',
                                            '#EXT-X-CUE-', '#EXT-X-SCTE35')))
            out.append(e['url'] if e['url'].startswith(('http://', 'https://'))
                       else urljoin(source_url, e['url']))

        for t in trailer:
            if t.startswith(_GLOBAL_TAGS):
                out.append(self._rewrite_tag(t, source_url))
        if not any(t.startswith('#EXT-X-ENDLIST') for t in out) and any(
                t.startswith('#EXT-X-ENDLIST') for t in lines):
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
        """清孤立噪声：连续 DISCONTINUITY、METHOD=NONE、断层 PDT。"""
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

    # ================= localProxy =================
    def local_proxy(self, param):
        try:
            target, depth = self._parse_param(param)
            if not target or not re.match(r'^https?://', target, re.I):
                return [400, 'text/plain', 'invalid url']
            content = self._fetch(target, timeout=20)
            if not content:
                # 二次尝试：带 Referer 再拉一次（不少 CDN 首次裸拉 403）
                p = urlparse(target)
                content = self._fetch(target, timeout=20, referer=p.scheme + '://' + p.netloc + '/')
            if not content:
                return [502, 'text/plain', 'fetch failed']
            head = content[:1024].lstrip(b'\xef\xbb\xbf').lstrip()
            if not head.startswith(b'#EXTM3U'):
                # 不是 m3u8（key / 分片等）原样透传，不碰内容
                return [200, 'application/octet-stream', content]
            text = content.decode('utf-8', 'ignore')
            return [200, 'application/vnd.apple.mpegurl', self.clean(text, target, depth).encode('utf-8')]
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
            target = unquote(target)             # 只解一次
        depth = 0
        try:
            depth = int(raw.get('d') or 0)
        except Exception:
            depth = 0
        return target, depth

