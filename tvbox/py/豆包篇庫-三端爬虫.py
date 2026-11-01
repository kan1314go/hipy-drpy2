# coding=utf-8
import base64
import hashlib
import json
import random
import re
import ssl
import string
import time
import urllib.parse
import urllib.request
import uuid

try:
    from base.spider import Spider as _Spider
except Exception:
    class _Spider(object):
        pass

NAME = '豆包篇庫'
UA = ('Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
DOMAIN_SOURCES = [
    'https://d15beepu2m390g.cloudfront.net/crks.json',
    'https://d2uyctkvrdlxg9.cloudfront.net/crks_ldy.json',
]
FALLBACK_DOMAINS = [
    'https://xBNie95.qcj2o8pi.work',
    'https://qoIkFE7.833x5qay.work',
    'https://RA9T7xv.uackh75z.work',
]
COVER_WORKER = 'https://2.h8.ccwu.cc/?url='
# 图片解密密钥：逆向自 APK com.androidx.lv.base.glide.decrypt 链路
# d.e.a.a.c.a.d.onResponse -> d.e.a.a.g.i.a(bytes, 100, "2020-zq3-888")
IMG_XOR_KEY = '2020-zq3-888'
IMG_XOR_HEAD = 100
PAGE_SIZE = 30
HOME_SIZE = 30
TIMEOUT = 8
TOKEN_TTL = 3600 * 24 * 30
ALL_TID = '__all__'
DEFAULT_CLASSES = [
    {'type_id': '33', 'type_name': '短剧精选'},
    {'type_id': '2', 'type_name': '都市'},
    {'type_id': '1', 'type_name': '古装'},
    {'type_id': '3', 'type_name': '甜宠'},
    {'type_id': '4', 'type_name': '战神'},
    {'type_id': '5', 'type_name': '逆袭'},
    {'type_id': '6', 'type_name': '穿越'},
    {'type_id': '7', 'type_name': '重生'},
    {'type_id': '8', 'type_name': '悬疑'},
    {'type_id': '9', 'type_name': '喜剧'},
]

_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16]
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _gxtime(a):
    a <<= 1
    if a & 0x100:
        a ^= 0x11b
    return a & 0xff


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _gxtime(a)
        b >>= 1
    return r


def _aes_round_keys(key):
    w = [list(key[4 * i:4 * i + 4]) for i in range(4)]
    for i in range(4, 44):
        t = w[i - 1][:]
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // 4 - 1]
        w.append([t[j] ^ w[i - 4][j] for j in range(4)])
    return w


def _aes_enc_mix(c):
    return [_gmul(c[0], 2) ^ _gmul(c[1], 3) ^ _gmul(c[2], 1) ^ _gmul(c[3], 1),
            _gmul(c[0], 1) ^ _gmul(c[1], 2) ^ _gmul(c[2], 3) ^ _gmul(c[3], 1),
            _gmul(c[0], 1) ^ _gmul(c[1], 1) ^ _gmul(c[2], 2) ^ _gmul(c[3], 3),
            _gmul(c[0], 3) ^ _gmul(c[1], 1) ^ _gmul(c[2], 1) ^ _gmul(c[3], 2)]


def _aes_inv_mix(c):
    return [_gmul(c[0], 14) ^ _gmul(c[1], 11) ^ _gmul(c[2], 13) ^ _gmul(c[3], 9),
            _gmul(c[0], 9) ^ _gmul(c[1], 14) ^ _gmul(c[2], 11) ^ _gmul(c[3], 13),
            _gmul(c[0], 13) ^ _gmul(c[1], 9) ^ _gmul(c[2], 14) ^ _gmul(c[3], 11),
            _gmul(c[0], 11) ^ _gmul(c[1], 13) ^ _gmul(c[2], 9) ^ _gmul(c[3], 14)]


def _aes_enc_block(block, w):
    def rk(r):
        out = []
        for i in range(4):
            out += w[r * 4 + i]
        return out

    def shift_rows(st):
        out = [0] * 16
        for r in range(4):
            for c in range(4):
                out[r + 4 * c] = st[r + 4 * ((c + r) % 4)]
        return out

    def mix_columns(st):
        out = [0] * 16
        for col in range(4):
            out[col * 4:col * 4 + 4] = _aes_enc_mix(st[col * 4:col * 4 + 4])
        return out

    state = [block[j] ^ rk(0)[j] for j in range(16)]
    for rnd in range(1, 10):
        st = [_SBOX[b] for b in state]
        st = shift_rows(st)
        st = mix_columns(st)
        key = rk(rnd)
        state = [st[j] ^ key[j] for j in range(16)]
    st = [_SBOX[b] for b in state]
    st = shift_rows(st)
    key = rk(10)
    return [st[j] ^ key[j] for j in range(16)]


def _aes_dec_block(block, w):
    def rk(r):
        out = []
        for i in range(4):
            out += w[r * 4 + i]
        return out

    def inv_shift(st):
        out = [0] * 16
        for col in range(4):
            for row in range(4):
                out[col * 4 + row] = st[((col - row) % 4) * 4 + row]
        return out

    state = [block[j] ^ rk(10)[j] for j in range(16)]
    for rnd in range(9, 0, -1):
        st = inv_shift(state)
        st = [_INV_SBOX[b] for b in st]
        key = rk(rnd)
        st = [st[j] ^ key[j] for j in range(16)]
        out = [0] * 16
        for col in range(4):
            out[col * 4:col * 4 + 4] = _aes_inv_mix(st[col * 4:col * 4 + 4])
        state = out
    st = inv_shift(state)
    st = [_INV_SBOX[b] for b in st]
    key = rk(0)
    return [st[j] ^ key[j] for j in range(16)]


def _aes_crypt(data, key, encrypt=True):
    w = _aes_round_keys(key)
    out = bytearray()
    for i in range(0, len(data), 16):
        blk = list(data[i:i + 16])
        if len(blk) < 16:
            blk += [0] * (16 - len(blk))
        out += bytes(_aes_enc_block(blk, w) if encrypt else _aes_dec_block(blk, w))
    return bytes(out)


def aes_ecb_encrypt(plain, key):
    data = plain.encode('utf-8') if isinstance(plain, str) else plain
    padlen = 16 - len(data) % 16
    data = data + bytes([padlen]) * padlen
    return base64.b64encode(_aes_crypt(data, key.encode('utf-8'), True)).decode()


def aes_ecb_decrypt(ct, key):
    data = base64.b64decode(ct)
    raw = _aes_crypt(data, key.encode('utf-8'), False)
    padlen = raw[-1] if raw else 0
    if 0 < padlen <= 16:
        raw = raw[:-padlen]
    return raw.decode('utf-8', 'replace')


def aes_cbc_decrypt(ct, key, iv=None):
    key = key.encode('utf-8') if isinstance(key, str) else key
    if iv is None:
        iv = key
    elif isinstance(iv, str):
        iv = iv.encode('utf-8')
    data = base64.b64decode(ct)
    w = _aes_round_keys(key)
    prev = list(iv)
    out = bytearray()
    for i in range(0, len(data), 16):
        blk = list(data[i:i + 16])
        if len(blk) < 16:
            blk += [0] * (16 - len(blk))
        dec = bytes(_aes_dec_block(blk, w))
        out += bytes(dec[j] ^ prev[j] for j in range(16))
        prev = blk
    padlen = out[-1] if out else 0
    if 0 < padlen <= 16:
        out = out[:-padlen]
    return bytes(out)


def _md5(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest()


# ---- 图片解密（复刻 d.e.a.a.g.i.a）----
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
_JPG_MAGIC = b'\xff\xd8\xff'
_GIF_MAGIC = b'GIF'
_WEBP_RIFF = b'RIFF'


def _img_already_plain(data):
    """已是 PNG / JPEG / GIF 明文则无需解密，原样返回（与原实现判断一致）"""
    if len(data) > 7 and data[:8] == _PNG_MAGIC:
        return True
    if len(data) > 2 and data[:3] == _GIF_MAGIC:
        return True
    if len(data) > 7 and data[:3] == _JPG_MAGIC:
        return True
    return False


def decrypt_image(data):
    """
    站点图片只对前 100 字节做了重复密钥 XOR，后段为原始数据。
    算法等价于 Java:
        for (i = 0; i < 100; i++) out[i] = data[i] ^ key[i % key.length()]
    """
    if not data:
        return data
    if _img_already_plain(data):
        return data
    key = IMG_XOR_KEY.encode('utf-8')
    out = bytearray(data)
    n = min(IMG_XOR_HEAD, len(data))
    klen = len(key)
    for i in range(n):
        out[i] = data[i] ^ key[i % klen]
    return bytes(out)


def _img_mime(data):
    if len(data) > 12 and data[:4] == _WEBP_RIFF and data[8:12] == b'WEBP':
        return 'image/webp'
    if len(data) > 7 and data[:8] == _PNG_MAGIC:
        return 'image/png'
    if len(data) > 2 and data[:3] == _JPG_MAGIC:
        return 'image/jpeg'
    if len(data) > 2 and data[:3] == _GIF_MAGIC:
        return 'image/gif'
    if len(data) > 1 and data[:2] == b'BM':
        return 'image/bmp'
    return 'application/octet-stream'


def _ssl_opener():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx))


def _login_key():
    ts = int(time.time())
    hexstr = format(ts, 'x')
    if len(hexstr) >= 8:
        key = hexstr[:8] + uuid.uuid4().hex[:16]
    else:
        key = ('%8s' % hexstr).replace(' ', '0') + uuid.uuid4().hex[:16]
    length = ts % 8
    length2 = length + 16
    if length2 <= len(key) or length >= 0:
        start = length
    else:
        length = length2 = len(key) + (-16)
        start = length
    return key, key[start:length2][::-1]


class Spider(_Spider):
    def __init__(self):
        self.base = ''
        self.device = ''
        self.token = ''
        self.token_time = 0
        self.user = {}
        self._classes = []
        self._filters = {}
        self._class_time = 0
        self._err = ''

    def _probe_domains(self, extend, fast=False):
        hosts = []
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {'host': extend.strip().rstrip('/')} if extend.strip().startswith('http') else {}
        if not isinstance(cfg, dict):
            cfg = {}
        for key in ('host', 'base', 'url', 'site'):
            v = str(cfg.get(key) or '').strip().rstrip('/')
            if v.startswith('http'):
                hosts.append(v)
        if fast:
            for h in FALLBACK_DOMAINS:
                if h not in hosts:
                    hosts.append(h)
            return hosts
        from concurrent.futures import ThreadPoolExecutor

        def fetch(src):
            try:
                req = urllib.request.Request(src, headers={'User-Agent': UA})
                with _ssl_opener().open(req, timeout=4) as r:
                    raw = r.read().decode('utf-8', 'replace')
                arr = json.loads(raw)
                if isinstance(arr, list):
                    return [str(i).strip().rstrip('/') for i in arr
                            if str(i or '').strip().startswith('http')]
            except Exception:
                pass
            return []

        try:
            with ThreadPoolExecutor(max_workers=min(3, len(DOMAIN_SOURCES) + 1)) as ex:
                lists = list(ex.map(fetch, DOMAIN_SOURCES))
        except Exception:
            lists = []
        for arr in lists:
            for h in arr:
                if h and h not in hosts:
                    hosts.append(h)
        for h in FALLBACK_DOMAINS:
            if h not in hosts:
                hosts.append(h)
        return hosts

    def _login(self):
        device = self.device or _md5('doubao-' + str(random.randint(0, 999999)))
        self.device = device
        key, enc_key = _login_key()
        ttb = random.choice(string.ascii_letters + string.digits)
        payload = json.dumps({'deviceId': device, 'code': '', 'ttb': ttb}, separators=(',', ':'))
        enc = aes_ecb_encrypt(payload, enc_key)
        body = json.dumps({'encStr': enc}, separators=(',', ':'))
        url = self.base + '/api/user/traveler/' + key + '/login'
        code, text = self._http(url, 'POST', body=body)
        if code != 200:
            return False
        try:
            obj = json.loads(text)
        except Exception:
            return False
        data = obj.get('data')
        if isinstance(data, str):
            try:
                data = json.loads(aes_ecb_decrypt(data, enc_key))
            except Exception:
                return False
        if not data or not data.get('token'):
            return False
        self.user = data
        self.token = data.get('token')
        self.token_time = time.time()
        return True

    def _http(self, url, method='GET', body=None, params=None, timeout=TIMEOUT, raw=False):
        if params:
            url = url + ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
        ts = str(int(time.time() * 1000))
        s = _md5(ts[3:8])
        headers = {
            'User-Agent': UA,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'deviceId': self.device,
            't': ts,
            's': s,
        }
        if self.token:
            headers['aut'] = self.token
        req = urllib.request.Request(url, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        if body is not None:
            req.data = body.encode('utf-8') if isinstance(body, str) else body
        try:
            opener = _ssl_opener()
            with opener.open(req, timeout=timeout) as r:
                if raw:
                    return r.status, r.read()
                return r.status, r.read().decode('utf-8', 'replace')
        except Exception:
            return 0, ''

    def _api(self, path, params=None, retry=1):
        for i in range(retry + 1):
            if not self.token or (time.time() - self.token_time) > TOKEN_TTL:
                if not self._relogin_switch(fast=True):
                    return None
            code, text = self._http(self.base + path, 'GET', params=params)
            if not text:
                if i < retry:
                    self._relogin_switch(fast=True)
                continue
            try:
                obj = json.loads(text)
            except Exception:
                return None
            if obj.get('code') in (1001, 1003):
                self.token = ''
                if i < retry:
                    self._relogin_switch(fast=True)
                continue
            enc = obj.get('encData')
            if enc and self.token:
                try:
                    obj['data'] = json.loads(aes_cbc_decrypt(enc, self.token[2:18]))
                except Exception:
                    pass
            return obj
        return None

    def _relogin_switch(self, fast=False):
        hosts = self._probe_domains('', fast=fast)
        if not hosts:
            return False
        if self.base in hosts:
            hosts.remove(self.base)
        if not hosts:
            return False
        from concurrent.futures import ThreadPoolExecutor

        def try_login(h):
            if not h:
                return None
            s = Spider()
            s.base = h
            try:
                if s._login() and s.token:
                    if not fast:
                        s._load_classes()
                    return s
            except Exception:
                pass
            return None

        try:
            with ThreadPoolExecutor(max_workers=min(8, len(hosts))) as ex:
                results = list(ex.map(try_login, hosts))
        except Exception:
            results = []
        for s in results:
            if s and s.token:
                self.base = s.base
                self.device = s.device
                self.token = s.token
                self.token_time = s.token_time
                self.user = s.user
                if not fast:
                    self._classes = s._classes
                    self._class_time = s._class_time
                return True
        return False

    def _pick_cover(self, item, pub_domain='', auth_domain=''):
        """
        选封面地址。实测规则（2026-11 验证，严格区分两个域）：
          - 带 auth_key 的相对路径 -> 只能配 authDomain（6ks386huzyak.kgjci.com）
          - 不带 auth_key 的相对路径 -> 只能配公开图片域（列表 domain / 登录 imgDomain）
          - 交叉组合（公开域+带key / 鉴权域+无key）都会 403 或返回空
        因此这里必须拿到两个域，不能用一个 domain 参数顶替。
        """
        def first(v):
            if isinstance(v, list) and v:
                return str(v[0] or '').strip()
            if isinstance(v, str) and v.strip():
                return v.strip()
            return ''

        def join(host, rel):
            host = str(host or '').strip().rstrip('/')
            rel = str(rel or '').strip().lstrip('/')
            if not host or not rel:
                return ''
            if rel.startswith('http'):
                return rel
            return host + '/' + rel

        pub = str(pub_domain or '').strip().rstrip('/') or \
            str(self.user.get('imgDomain') or '').rstrip('/')
        auth = str(auth_domain or '').strip().rstrip('/') or \
            str(self.user.get('authImgDomain') or '').rstrip('/')

        # 1) 带 auth_key 的地址 -> authDomain（最可靠）
        for key in ('authCoverImg', 'authVerticalImg'):
            rel = first(item.get(key))
            if rel and 'auth_key=' in rel and auth:
                u = join(auth, rel)
                if u:
                    return u
        # 2) 无 key 地址 -> 公开图片域
        for key in ('coverImg', 'verticalImg'):
            rel = first(item.get(key))
            if rel and pub:
                u = join(pub, rel)
                if u:
                    return u
        # 3) 兜底：带 key 的优先落 auth，再落 pub
        for key in ('authCoverImg', 'authVerticalImg'):
            rel = first(item.get(key))
            if rel:
                u = join(auth or pub, rel)
                if u:
                    return u
        for key in ('coverImg', 'verticalImg'):
            rel = first(item.get(key))
            if rel:
                u = join(pub or auth, rel)
                if u:
                    return u
        return ''

    def _cover_url(self, url):
        """
        封面走 localProxy 本地解密。
        站点封面是「前 100 字节 XOR 混淆」的 webp（密钥 IMG_XOR_KEY），
        直接给播放器原图地址只会得到乱码，因此全部包装成 proxy:// 由脚本解密后回吐。
        """
        u = str(url or '').strip()
        if not u:
            return ''
        if u.startswith('proxy://'):
            return u
        b64 = base64.urlsafe_b64encode(u.encode('utf-8')).decode('utf-8').rstrip('=')
        return 'proxy://do=py&type=img&url=' + b64

    def _card(self, item, pub_domain='', auth_domain=''):
        vid = item.get('videoId') or item.get('id') or ''
        if vid is None:
            vid = ''
        name = str(item.get('title') or ('豆包视频' + str(vid)))
        pic = self._pick_cover(item, pub_domain, auth_domain)
        pic = self._cover_url(pic)
        tags = item.get('tagTitles') or []
        if isinstance(tags, list):
            tags = [str(t) for t in tags if t]
        remark = ''
        if item.get('completionStatus') is not None:
            remark = '已完结' if int(item.get('completionStatus')) == 2 else '连载中'
        if item.get('shortDrama'):
            remark = '短剧'
        return {
            'vod_id': str(vid),
            'vod_name': name,
            'vod_pic': pic,
            'vod_pic_slide': pic,
            'vod_remarks': remark,
            'vod_year': '',
            'vod_area': '',
            'vod_lang': '',
            'vod_class': ','.join(tags),
            'vod_tag': ','.join(tags),
            'vod_actor': str(item.get('nickName') or ''),
            'vod_director': '',
            'type_name': '',
        }

    def _pagecount_for(self, pg, n_items, page_size=PAGE_SIZE):
        """
        服务端 getVideoList 的 total 恒为 null，无法直接算出总页数。
        采用「满页即推定还有下一页」策略：
          本页条数 == pageSize  -> 至少还有下一页，pagecount = pg + 1
          本页不满 / 为空        -> 已是末页，pagecount = pg
        平台据此显示/继续翻页；翻到空页时自然停止。
        """
        pg = max(1, int(pg or 1))
        size = max(1, int(page_size or PAGE_SIZE))
        return pg + 1 if int(n_items or 0) >= size else pg

    def _list_resp(self, items, pg, pub_domain='', auth_domain='', page_size=None):
        lst = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            c = self._card(it, pub_domain, auth_domain)
            if c['vod_id']:
                lst.append(c)
        pg = max(1, int(pg or 1))
        size = max(1, int(page_size or PAGE_SIZE))
        pc = self._pagecount_for(pg, len(lst), size)
        # 已知条数下界：(pg-1)*size + 本页条数
        total = (pg - 1) * size + len(lst)
        return {'list': lst, 'page': pg, 'pagecount': pc,
                'limit': size, 'total': total,
                'totalpage': pc, 'moresort': pc > pg,
                'parse': 0, 'jx': 0}

    def _empty(self, pg, pagecount=1):
        pg = max(1, int(pg or 1))
        pc = max(pg, int(pagecount or pg))
        return {'list': [], 'page': pg, 'pagecount': pc,
                'limit': PAGE_SIZE, 'total': (pg - 1) * PAGE_SIZE,
                'totalpage': pc, 'moresort': False,
                'parse': 0, 'jx': 0}

    def _load_classes(self):
        if self._classes and (time.time() - self._class_time) < 3600:
            return self._classes
        cls = []
        try:
            obj = self._api('/api/video/classifyList')
            data = obj.get('data') if obj else None
            if isinstance(data, dict):
                data = data.get('data')
            if isinstance(data, list):
                for it in data:
                    if not isinstance(it, dict):
                        continue
                    cid = it.get('classifyId')
                    title = str(it.get('classifyTitle') or '')
                    if cid is None or not title:
                        continue
                    cls.append({'type_id': str(cid), 'type_name': title})
        except Exception:
            cls = []
        if not cls:
            cls = list(DEFAULT_CLASSES)
        self._classes = cls
        self._class_time = time.time()
        return cls

    def _load_filters(self):
        flt = self._default_filters(self._classes or list(DEFAULT_CLASSES))
        self._filters = flt
        return flt

    def _video_list(self, classify_id, pg, sort_type=1):
        params = {'pageSize': PAGE_SIZE, 'page': int(pg or 1),
                  'classifyId': classify_id, 'sortType': int(sort_type or 1)}
        obj = self._api('/api/video/getVideoList', params)
        data = obj.get('data') if obj else None
        items = data.get('data') if isinstance(data, dict) else None
        if not items:
            return self._empty(pg)
        return self._list_resp(items, pg,
                               data.get('domain') or '',
                               data.get('authDomain') or '')

    def _video_zone(self, zone_id, pg):
        params = {'pageSize': PAGE_SIZE, 'page': int(pg or 1), 'zoneId': zone_id}
        obj = self._api('/api/video/queryVideoByZone', params)
        data = obj.get('data') if obj else None
        items = data.get('data') if isinstance(data, dict) else None
        if not items:
            return self._empty(pg)
        return self._list_resp(items, pg,
                               data.get('domain') or '',
                               data.get('authDomain') or '')

    def _episodes(self, detail):
        eps = []
        serials = detail.get('serialVideos') or []
        if not isinstance(serials, list):
            serials = []
        if serials:
            for it in serials:
                if not isinstance(it, dict):
                    continue
                vid = it.get('videoId')
                title = str(it.get('title') or ('第%d集' % (len(eps) + 1)))
                if vid is None:
                    continue
                eps.append((str(vid), title))
        if not eps:
            vid = detail.get('videoId')
            if vid is not None:
                eps.append((str(vid), '正片'))
        return eps

    def _ep_url(self, vid):
        obj = self._api('/api/video/getVideoById', {'videoId': vid})
        data = obj.get('data') if obj else None
        if isinstance(data, dict) and 'data' in data and isinstance(data.get('data'), dict):
            data = data['data']
        if not isinstance(data, dict):
            return ''
        return str(data.get('videoUrl') or '')

    def _ep_urls(self, eps):
        try:
            from concurrent.futures import ThreadPoolExecutor

            def one(vid):
                try:
                    return self._ep_url(vid)
                except Exception:
                    return ''

            with ThreadPoolExecutor(max_workers=min(6, max(1, len(eps)))) as ex:
                return list(ex.map(lambda p: one(p), [v for v, _ in eps]))
        except Exception:
            return [self._ep_url(v) for v, _ in eps]

    def _proxy_url(self, path):
        dec = self.base + '/api/m3u8/decode/byPath?path=' + urllib.parse.quote(str(path), safe='')
        b64 = base64.urlsafe_b64encode(dec.encode('utf-8')).decode('utf-8').rstrip('=')
        return 'proxy://do=py&type=m3u8&url=' + b64

    @staticmethod
    def _b64d(s):
        s = str(s or '').strip()
        pad = '=' * (-len(s) % 4)
        try:
            return base64.urlsafe_b64decode((s + pad).encode('utf-8')).decode('utf-8')
        except Exception:
            try:
                return base64.b64decode((s + pad).encode('utf-8')).decode('utf-8')
            except Exception:
                return ''

    @staticmethod
    def _extract_param(param):
        url = ''
        if param is None:
            return url
        if isinstance(param, dict):
            for k in ('url', 'u', 'target', 'src', 'image', 'img', 'pic', 'href', 'link', 'path', 'uri', 'raw'):
                v = param.get(k)
                if v:
                    url = v[0] if isinstance(v, (list, tuple)) and v else v
                    break
        elif isinstance(param, str):
            url = param
        elif isinstance(param, (list, tuple)) and param:
            first = param[0]
            if isinstance(first, dict):
                for k in ('url', 'u', 'src', 'img', 'pic'):
                    if first.get(k):
                        url = first[k]
                        break
            elif isinstance(first, str):
                url = first
        if not url:
            return ''
        s = str(url).strip()
        if s.lower().startswith('proxy://'):
            s = s[len('proxy://'):]
            if 'url=' in s:
                try:
                    q = urllib.parse.parse_qs(s)
                    return (q.get('url') or [''])[0]
                except Exception:
                    pass
        return s

    def init(self, extend=""):
        self.extend = extend
        return self

    def _ensure_ready(self):
        if self.base and self.token and (time.time() - self.token_time) <= TOKEN_TTL:
            return True
        # 快速路径：直接并发登录 fallback 域名（不抓 cloudfront）
        if self._relogin_switch(fast=True):
            return True
        # 慢速路径：抓 cloudfront 补充域名再试
        hosts = self._probe_domains(self.extend or '')
        if not hosts:
            return False
        if self._relogin_switch():
            return True
        self.base = hosts[0]
        self._login()
        return bool(self.base and self.token)

    def getName(self):
        return NAME

    def getDependence(self):
        return []

    def homeContent(self, filter=False):
        try:
            # 触发一次快速登录，让后续 homeVideoContent/categoryContent 有 token
            self._ensure_ready()
            if self._classes and (time.time() - self._class_time) < 3600:
                cls = self._classes
            else:
                cls = list(DEFAULT_CLASSES)
            flt = self._default_filters(cls)
            return {'class': cls, 'filters': flt, 'list': [],
                    'parse': 0, 'jx': 0, 'url': (self.base or FALLBACK_DOMAINS[0]) + '/'}
        except Exception:
            return {'class': list(DEFAULT_CLASSES),
                    'filters': {}, 'list': [], 'parse': 0, 'jx': 0,
                    'url': FALLBACK_DOMAINS[0] + '/'}

    def _default_filters(self, cls):
        flt = {}
        for c in cls or []:
            tid = c['type_id']
            flt[tid] = [{
                'key': 'sortType',
                'name': '排序',
                'value': [
                    {'n': '最近更新', 'v': '1'},
                    {'n': '本周最热', 'v': '2'},
                    {'n': '10分钟以上', 'v': '3'},
                ],
            }]
        flt[ALL_TID] = flt.get('33', [])
        return flt

    def homeVideoContent(self):
        try:
            if not self._ensure_ready():
                return {'list': [], 'parse': 0, 'jx': 0}
            res = self._video_list('33', 1, 1)
            res['list'] = res['list'][:HOME_SIZE]
            return res
        except Exception:
            return {'list': [], 'parse': 0, 'jx': 0}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '').strip()
        pg = int(pg or 1)
        ext = {}
        if isinstance(extend, str) and extend.strip():
            try:
                ext = json.loads(extend)
            except Exception:
                ext = {}
        if not isinstance(ext, dict):
            ext = {}
        sort_type = int(ext.get('sortType') or 1)
        zone = str(ext.get('zoneId') or '').strip()
        try:
            if not self._ensure_ready():
                return self._empty(pg)
            if tid in ('', ALL_TID, 'home', '全部'):
                tid = '33'
            if zone and zone.isdigit():
                return self._video_zone(zone, pg)
            return self._video_list(tid, pg, sort_type)
        except Exception:
            return self._empty(pg)

    def detailContent(self, ids):
        vid = ''
        if isinstance(ids, (list, tuple)) and ids:
            vid = str(ids[0] or '').strip()
        elif ids:
            vid = str(ids).strip()
        if not vid:
            return {'list': [], 'parse': 0, 'jx': 0}
        if not self._ensure_ready():
            return {'list': [], 'parse': 0, 'jx': 0}
        obj = self._api('/api/video/getVideoById', {'videoId': vid})
        data = obj.get('data') if obj else None
        # 详情响应不带 domain/authDomain，封面域回退到登录返回的 imgDomain/authImgDomain
        if isinstance(data, dict) and 'data' in data and isinstance(data.get('data'), dict):
            data = data['data']
        if not isinstance(data, dict) or not data.get('videoId'):
            return {'list': [], 'parse': 0, 'jx': 0}
        card = self._card(data)
        name = card['vod_name']
        pic = card['vod_pic']
        tags = data.get('tagTitles') or []
        if isinstance(tags, list):
            tags = [str(t) for t in tags if t]
        eps = self._episodes(data)
        froms = []
        urls = []
        if eps:
            parts = []
            ep_urls = self._ep_urls(eps)
            for (ep_vid, ep_title), ep_url in zip(eps, ep_urls):
                if ep_url:
                    parts.append('%s$%s' % (ep_title, self._proxy_url(ep_url)))
            if parts:
                froms.append(NAME)
                urls.append('#'.join(parts))
        if not froms:
            froms = [NAME]
            urls = ['']
        bits = []
        if tags:
            bits.append('标签：' + ' / '.join(tags))
        if data.get('nickName'):
            bits.append('作者：' + str(data.get('nickName')))
        if data.get('playTime'):
            bits.append('时长：%d秒' % int(data.get('playTime')))
        if data.get('size'):
            bits.append('大小：%dMB' % int(int(data.get('size')) // 1048576))
        if data.get('fakeWatchNum') is not None:
            bits.append('播放：%s' % data.get('fakeWatchNum'))
        if data.get('reviewDate'):
            bits.append('日期：' + str(data.get('reviewDate'))[:10])
        if eps:
            bits.append('集数：共%d集' % len(eps))
        content = '\n'.join(bits).strip() or name
        year = str(data.get('reviewDate') or '')[:4]
        remark = card['vod_remarks'] or ''
        if eps:
            remark = '%s · %d集' % (remark, len(eps))
        return {'list': [{
            'vod_id': str(data.get('videoId')),
            'vod_name': name,
            'vod_pic': pic,
            'vod_pic_slide': pic,
            'vod_year': year,
            'vod_area': '',
            'vod_lang': '国语',
            'vod_class': ','.join(tags),
            'vod_tag': ','.join(tags),
            'vod_actor': str(data.get('nickName') or ''),
            'vod_director': '',
            'vod_remarks': remark,
            'vod_content': content,
            'type_name': tags[0] if tags else NAME,
            'vod_play_from': '$$$'.join(froms),
            'vod_play_url': '$$$'.join(urls),
        }], 'parse': 0, 'jx': 0, 'url': ''}

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or '').strip()
        if raw.startswith('proxy://'):
            return {'parse': 0, 'playUrl': '', 'url': raw,
                    'header': {'User-Agent': UA, 'Referer': self.base + '/'}, 'jx': 0}
        return {'parse': 0, 'playUrl': '', 'url': raw,
                'header': {'User-Agent': UA, 'Referer': self.base + '/'}, 'jx': 0}

    def searchContent(self, key, quick, pg="1"):
        kw = str(key or '').strip()
        pg = int(pg or 1)
        if not kw:
            return self._empty(pg)
        try:
            if not self._ensure_ready():
                return self._empty(pg)
            size = 20
            params = {'pageSize': size, 'page': pg, 'searchWord': kw,
                      'searchType': 3, 'loadType': 1}
            obj = self._api('/api/search/keyWord', params)
            data = obj.get('data') if obj else None
            items = data.get('videoList') if isinstance(data, dict) else None
            if not items:
                return self._empty(pg)
            return self._list_resp(items, pg,
                                   data.get('domain') or '',
                                   data.get('authDomain') or '',
                                   size)
        except Exception:
            return self._empty(pg)

    def searchContentPage(self, key, quick, pg="1", size="20"):
        return self.searchContent(key, quick, pg)

    def action(self, action):
        return '{}'

    def liveContent(self, url=""):
        return ''

    def localProxy(self, param):
        """
        本地代理，两种模式：
          type=img -> 下载封面原图、XOR 解密、按真实 MIME 回吐（解决「没有封面」）
          type=m3u8(默认) -> 带签名头请求 decode 接口，回吐播放列表
        """
        try:
            raw = self._extract_param(param)
            url = self._b64d(raw) if raw and not raw.startswith('http') else raw
            if not url or not url.startswith('http'):
                return [200, 'text/plain;charset=utf-8', b'']

            is_img = False
            if isinstance(param, dict):
                is_img = str(param.get('type') or '').lower() in ('img', 'image')
            elif isinstance(param, str) and 'type=img' in param:
                is_img = True

            if is_img:
                code, body = self._http(url, 'GET', raw=True)
                if code != 200 or not body:
                    return [200, 'text/plain;charset=utf-8', b'']
                body = decrypt_image(body)
                return [200, _img_mime(body), body]

            code, body = self._http(url, 'GET', raw=True)
            if code != 200 or not body:
                return [200, 'text/plain;charset=utf-8', b'']
            return [200, 'application/vnd.apple.mpegurl; charset=utf-8', body]
        except Exception:
            return [200, 'text/plain;charset=utf-8', b'']

    def isVideoFormat(self, url):
        u = str(url or '').lower()
        return any(x in u for x in ('.m3u8', '.mp4', '.flv', '.mkv', '.ts'))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._classes = []
        self._filters = {}
        self._err = ''


def _run_selftest():
    sp = Spider()
    sp.init('')
    print('base:', sp.base)
    print('token:', (sp.token or '')[:40])
    ok = True

    def check(tag, cond, info=''):
        nonlocal ok
        ok = ok and cond
        print(('[PASS] ' if cond else '[FAIL] ') + tag + (' ' + str(info) if info else ''))

    home = sp.homeContent(True)
    check('1 分类：一级分类导航', len(home.get('class') or []) > 0,
          '%d 个分类' % len(home.get('class') or []))
    check('1 分类：筛选器已生成', len(home.get('filters') or {}) > 0,
          '%d 组筛选' % len(home.get('filters') or {}))

    tid = home['class'][0]['type_id'] if home.get('class') else '33'
    cat1 = sp.categoryContent(tid, '1', True, '')
    cat2 = sp.categoryContent(tid, '2', True, '')
    cat3 = sp.categoryContent(tid, '3', True, '')
    cat_end = sp.categoryContent(tid, '999', True, '')
    check('2 分页：列表有数据', len(cat1.get('list') or []) > 0,
          'n=%d' % len(cat1.get('list') or []))
    walk_ids = [v['vod_id'] for v in cat1['list']] + [v['vod_id'] for v in cat2['list']] + \
               [v['vod_id'] for v in cat3['list']]
    check('2 分页：连续 3 页无重复',
          len(walk_ids) == len(set(walk_ids)),
          'p1=%d p2=%d p3=%d 去重=%d' % (len(cat1['list']), len(cat2['list']), len(cat3['list']), len(set(walk_ids))))
    check('2 分页：pagecount 逐页递增（满页时）',
          int(cat1.get('pagecount') or 0) == 2 and int(cat2.get('pagecount') or 0) == 3,
          'p1_pc=%s p2_pc=%s moresort=%s' % (cat1.get('pagecount'), cat2.get('pagecount'), cat1.get('moresort')))
    check('2 分页：翻到末页后收口（pagecount == page）',
          int(cat_end.get('pagecount') or 0) == int(cat_end.get('page') or 0),
          'page=%s n=%d pagecount=%s' % (cat_end.get('page'), len(cat_end.get('list') or []), cat_end.get('pagecount')))
    check('2 封面：地址走 localProxy 解密通道',
          all(v['vod_pic'].startswith('proxy://') for v in cat1['list']),
          cat1['list'][0]['vod_pic'][:70] if cat1['list'] else '-')

    # 封面解密实打实校验：magic + 可解码
    img_ok = 0
    img_total = min(3, len(cat1.get('list') or []))
    img_info = ''
    for v in (cat1.get('list') or [])[:img_total]:
        lp = sp.localProxy({'url': v['vod_pic'], 'type': 'img'})
        body = lp[2] or b''
        good = (lp[0] == 200 and
                (body[:4] == b'RIFF' and body[8:12] == b'WEBP' or
                 body[:8] == b'\x89PNG\r\n\x1a\n' or
                 body[:3] == b'\xff\xd8\xff' or
                 body[:3] == b'GIF'))
        if good:
            img_ok += 1
        if not img_info:
            img_info = 'ctype=%s n=%d magic=%r' % (lp[1], len(body), body[:12])
    check('2 封面：解密后可解码为真实图片', img_total > 0 and img_ok == img_total,
          '%d/%d %s' % (img_ok, img_total, img_info))
    check('2 封面：旧中转 worker 已不再使用',
          'ccwu.cc' not in (cat1['list'][0]['vod_pic'] if cat1.get('list') else ''), '')

    if cat1.get('list'):
        vid = cat1['list'][0]['vod_id']
        det = sp.detailContent([vid])
        d = det['list'][0] if det.get('list') else {}
        check('3 详情：标题/简介/元数据', bool(d.get('vod_name')) and bool(d.get('vod_content')),
              d.get('vod_name', '')[:40])
        check('3 详情：多集播放源', bool(d.get('vod_play_url')),
              'from=%s eps=%d' % (d.get('vod_play_from', ''), len((d.get('vod_play_url') or '').split('#'))))
        first = (d.get('vod_play_url') or '').split('#')[0] if d.get('vod_play_url') else ''
        if first:
            ep_url = first.split('$')[-1]
            check('3 详情：播放走 localProxy', ep_url.startswith('proxy://'), ep_url[:60])

    sc = sp.searchContent('笑傲', False, '1')
    check('5 搜索：关键词命中', len(sc.get('list') or []) > 0,
          'n=%d 首条=%s' % (len(sc.get('list') or []), sc['list'][0]['vod_name'][:30] if sc.get('list') else '-'))
    check('5 搜索：封面随结果返回', all(v['vod_pic'].startswith('proxy://') for v in sc.get('list') or []))
    check('5 搜索：分页字段可用',
          int(sc.get('page') or 0) == 1 and int(sc.get('pagecount') or 0) >= 1,
          'page=%s pagecount=%s limit=%s' % (sc.get('page'), sc.get('pagecount'), sc.get('limit')))
    sc2 = sp.searchContent('笑傲', False, '2')
    check('5 搜索：第2页可继续（满页时）',
          len(sc.get('list') or []) < 20 or int(sc.get('pagecount') or 0) >= 2,
          'p1=%d p1_pc=%s p2=%d' % (len(sc.get('list') or []), sc.get('pagecount'), len(sc2.get('list') or [])))

    check('接口：图片解密函数可用',
          decrypt_image(b'\x60\x79\x74\x76' + bytes(96))[:4] == b'\x00\x00\x00\x00' or
          decrypt_image(bytes(100))[:4] != bytes(100)[:4], 'IMG_XOR_KEY=%s' % IMG_XOR_KEY)

    lp = sp.localProxy({'url': 'proxy://do=py&type=m3u8&url=' + base64.urlsafe_b64encode(
        (sp.base + '/api/m3u8/decode/byPath?path=jpd/20261029/0s/97/av/su/cbbdb25fa8c54b7a8fe5578780b06f97.m3u8').encode('utf-8')).decode('utf-8').rstrip('=')})
    check('6 播放：localProxy 返回 m3u8', lp[0] == 200 and lp[1].find('mpegurl') >= 0 and len(lp[2] or b'') > 50,
          'ct=%s bytes=%d' % (lp[1], len(lp[2] or b'')))

    check('接口：三端方法齐全',
          all(hasattr(sp, m) for m in ('init', 'getName', 'homeContent', 'homeVideoContent',
                                       'categoryContent', 'detailContent', 'playerContent',
                                       'searchContent', 'searchContentPage', 'action',
                                       'liveContent', 'localProxy', 'isVideoFormat',
                                       'manualVideoCheck', 'getDependence', 'destroy')), '')

    print('\n==== %s ====' % ('ALL PASS' if ok else 'HAS FAILURES'))


if __name__ == '__main__':
    _run_selftest()