# coding=utf-8
# TVBox / CatVod Python 源 —— i68（i68q77.com，站点自称「Uu 主站」）
#
# ================== 实测硬结论（2026-10-29）==================
# 站点结构：Vue3 SPA + 独立 API 网关（端口 51000），三级反爬，全部已破
#
# 1) 网页层有 PoW 挑战（只有浏览器需要，源不需要）
#    /home 首次返回一张挑战页：/_view/challenge + token(JWT)
#    算法 = FNV-1a 32：h=2166136261; h=imul(h^charCode,16777619)；取 8 位 hex
#    找最小 i 使 fnv1a(seed+"|"+i) 前 difficulty(3) 位为 '000'，
#    POST /home  body: __viewChallenge={token,proof,meta{ua,lang,tz,screen,webdriver,framed},path,key}
#    key = fnv1a(join([token,ua,lang,tz,screen,str(proof)],"|"))
#    成功后发 cookie vv_challenge。
#    但 API 网关（下面 2 的域名）**不校验这个 cookie**，所以本源直接走 API。
#
# 2) API 网关（网页里 window.__API_URLS__ 解出来，XOR+base64 藏的）
#    https://7l8.7l81uq.com:51000        ← 默认，实测可用
#    https://14p.14pijq.com:51000
#    https://t6y.t6ypaf.com:51000
#    请求头建议带 channel: tz（网页里的 window._CHANNEL_DATA = 'tz'）
#
# 3) 所有响应体是「明文 JSON + data 字段加密」：
#    {code,message,data:<base64url>,key:"<32位随机串>"}
#    解密：data 先 base64url 解码，再按字节与 key 的 UTF-8 字节循环异或 → JSON
#    （不是 AES，纯异或，密钥随响应一起给，属于混淆）
#
# 4) 接口清单（全是 GET）
#    /api/v2/home/public/video/cate/list?type=long      分类，18 个
#    /api/v2/home/public/video/label/list?type=long     标签
#    /api/v2/home/public/video/home?videoType=long      首页板块
#    /api/v2/home/public/video/list                     列表：page/limit(≤100)/videoType=long
#                                                       type ∈ last|hot|good|cate|label|collect
#                                                       cate/label 时再带 typeId=<id>
#    /api/v2/home/public/video/long/detail?id=<id>      详情
#    /api/v2/home/public/video/search?keyword=&page=&limit=&videoType=long
#    /api/v2/home/public/cdn/index?channel=tz           线路表（videoUrl / picUrl / bucket）
#    /api/v2/home/user/video/play/url?id=<id>           播放地址（**要登录 token**）
#
# 5) 登录：POST /api-user/v2/login/fingerprint  body {"channel":"tz","fingerPrint":"fp-xxxxxxxx"}
#    免账号，直接按指纹建号，返回 accessToken（ttl≈1860s）+ refreshToken
#    之后请求头 Authorization: Bearer <accessToken>
#
# 6) 播放链路（已验证能拉到真分片）
#    play/url → {masterUrl,p480Url,p720Url}，都是 /api/v2/.../{sign}/{ts}/{idCode}_play?cdnId=&variant=
#    ★ 取 m3u8 必须带 Referer: <站点首页>，否则 403 Forbidden（token 反而不需要）
#    720p 播放单里 #EXT-X-KEY:AES-128 URI 指向 API 的 _key 端点，分片是 CDN 绝对签名地址
#    实测：key 16 字节正常、ts 200 / 1.8MB / video/mp2t
#
# 7) 封面是加密的：thumb 形如 /uploads/file/xxxx_compress.jpg.enc
#    完整地址 = 视频CDN + /encryption-ts + thumb
#    解密 = AES-256-CBC，key 固定 "H0Z%7n#k$H8*M7xSE^N@8xXZPG*RZ&wY"，
#           IV = 文件前 16 字节，密文 = 剩下部分，解出就是 JPEG（实测 ffd8ffdb）
#    ★ 注意 https://jrsb.aiide.online 是**反诈跳转型**域名（301 → www.js96110.com.cn），不能用；
#      排除后可用：jqsp.* / jqsp34.* / lmcsxdd.* 等 ...xn--xhq15jk0k96h.cn 家族
#    TVBox 不会自己解密。三种出图方式，自动化选，逐级回落：
#      remote：把「加密图地址 + key」交给公网解密代理 → 拿回普通 https 明文 JPEG
#              https://2.h8.ccwu.cc/?url=<加密图>&key=<AES密钥>
#              ★ 实测返回字节与源内本地 AES 解密**逐字节一致**，客户端零改造，首选
#      proxy ：http://127.0.0.1:<port>/proxy?do=py&u=<加密图>，源内 localProxy 解，省流量
#      data  ：源内解成 data:image/jpeg;base64 塞进 vod_pic（部分客户端不认 data:，留作兜底）
#    哪个能用是**源内自己探测**出来的（先验证解密代理真能吐 JPEG，再验本地代理端口），
#    全部失败也不至于空白：详情页正文会写一段【封面自检】，把每一步的实测结果列出来。
#    被墙时取图可走 https://1.h8.ccwu.cc/<目标地址>（URL 前缀式代理，实测字节完整），配置项 tunnel。
# ==========================================================
import json
import base64
import re
import ssl

# ★ Hawk/FongMi 的嵌入式 Python 常常没有 CA 证书包，https 会直接 CERTIFICATE_VERIFY_FAILED。
#   桌面/沙箱有系统证书，所以这个坑只在真机暴露（表现：完全没内容）。
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass
import socket
import time
import threading
import zlib
import gzip
import urllib.request
import urllib.parse

API_DEFAULT = "https://7l8.7l81uq.com:51000"
API_ALTS = [
    "https://7l8.7l81uq.com:51000",
    "https://14p.14pijq.com:51000",
    "https://t6y.t6ypaf.com:51000",
]
SITE_DEFAULT = "https://i68.i68q77.com:51888"
CHANNEL_DEFAULT = "tz"
UA_DEFAULT = ("Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

PIC_KEY = b"H0Z%7n#k$H8*M7xSE^N@8xXZPG*RZ&wY"   # 封面 AES-256 固定密钥
PIC_KEY_STR = "H0Z%7n#k$H8*M7xSE^N@8xXZPG*RZ&wY"
# 公网解密代理：把「加密图地址 + key」交给它，它直接吐明文 JPEG。
# ★ 这样 vod_pic 就是一个普通 https 图片，客户端既不需要 data URI 也不碰 127.0.0.1，
#   实测返回的字节与源内本地 AES 解密结果**逐字节一致**。
#   换站/换 key 时改 {"decrypt_api": "...?url="} + PIC_KEY 即可；填 "" 关闭。
DECRYPT_API_DEFAULT = "https://2.h8.ccwu.cc/?url="
PIC_BUCKET = "encryption-ts"                    # 对象存储 bucket 前缀
CDN_SKIP_HOST = "aiide.online"                  # 反诈跳转型域名，跳过

FIXED_TYPES = [("last", "最新更新"), ("hot", "热门"), ("good", "精选")]


# ============ 纯标准库 AES-256/128-CBC 解密（只解封面，去 PKCS7）============
_SB = [
0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16]
_ISB = [0] * 256
for _i, _v in enumerate(_SB):
    _ISB[_v] = _i
_RC = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36, 0x6c, 0xd8, 0xab, 0x4d]


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else a << 1
        b >>= 1
    return r


_M9 = [_gmul(x, 9) for x in range(256)]
_M11 = [_gmul(x, 11) for x in range(256)]
_M13 = [_gmul(x, 13) for x in range(256)]
_M14 = [_gmul(x, 14) for x in range(256)]
_T0 = [(_M14[x] << 24) | (_M9[x] << 16) | (_M13[x] << 8) | _M11[x] for x in range(256)]
_T1 = [(_M11[x] << 24) | (_M14[x] << 16) | (_M9[x] << 8) | _M13[x] for x in range(256)]
_T2 = [(_M13[x] << 24) | (_M11[x] << 16) | (_M14[x] << 8) | _M9[x] for x in range(256)]
_T3 = [(_M9[x] << 24) | (_M13[x] << 16) | (_M11[x] << 8) | _M14[x] for x in range(256)]


def _expand_key(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SB[b] for b in t]
            t[0] ^= _RC[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [_SB[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    flat = []
    for word in w:
        flat.extend(word)
    return [flat[16 * r:16 * r + 16] for r in range(nr + 1)], nr


def aes_cbc_decrypt(key, data, iv=None):
    if iv is None:
        if len(data) <= 16:
            return b""
        iv, data = data[:16], data[16:]
    rk, nr = _expand_key(key)
    out = bytearray()
    prev = iv
    n = len(data) // 16 * 16
    i = 0
    ISB = _ISB
    T0, T1, T2, T3 = _T0, _T1, _T2, _T3
    while i < n:
        blk = data[i:i + 16]
        k = rk[nr]
        s = [blk[j] ^ k[j] for j in range(16)]
        for r in range(nr - 1, -1, -1):
            a0 = ISB[s[0]]; a1 = ISB[s[13]]; a2 = ISB[s[10]]; a3 = ISB[s[7]]
            b0 = ISB[s[4]]; b1 = ISB[s[1]]; b2 = ISB[s[14]]; b3 = ISB[s[11]]
            c0 = ISB[s[8]]; c1 = ISB[s[5]]; c2 = ISB[s[2]]; c3 = ISB[s[15]]
            d0 = ISB[s[12]]; d1 = ISB[s[9]]; d2 = ISB[s[6]]; d3 = ISB[s[3]]
            k = rk[r]
            a0 ^= k[0]; a1 ^= k[1]; a2 ^= k[2]; a3 ^= k[3]
            b0 ^= k[4]; b1 ^= k[5]; b2 ^= k[6]; b3 ^= k[7]
            c0 ^= k[8]; c1 ^= k[9]; c2 ^= k[10]; c3 ^= k[11]
            d0 ^= k[12]; d1 ^= k[13]; d2 ^= k[14]; d3 ^= k[15]
            if r:
                v = T0[a0] ^ T1[a1] ^ T2[a2] ^ T3[a3]
                e = [v >> 24 & 255, v >> 16 & 255, v >> 8 & 255, v & 255]
                v = T0[b0] ^ T1[b1] ^ T2[b2] ^ T3[b3]
                f = [v >> 24 & 255, v >> 16 & 255, v >> 8 & 255, v & 255]
                v = T0[c0] ^ T1[c1] ^ T2[c2] ^ T3[c3]
                g = [v >> 24 & 255, v >> 16 & 255, v >> 8 & 255, v & 255]
                v = T0[d0] ^ T1[d1] ^ T2[d2] ^ T3[d3]
                h = [v >> 24 & 255, v >> 16 & 255, v >> 8 & 255, v & 255]
                s = e + f + g + h
            else:
                s = [a0, a1, a2, a3, b0, b1, b2, b3, c0, c1, c2, c3, d0, d1, d2, d3]
        out += bytes((s[j] ^ prev[j]) for j in range(16))
        prev = blk
        i += 16
    if out and 1 <= out[-1] <= 16:
        out = out[:-out[-1]]
    return bytes(out)


class Spider(object):
    def __init__(self):
        # ★ 2026-10-29 实测：专用网关 7l8.7l81uq.com:51000 成功率只有 1/8（随机 RemoteDisconnected），
        #   而**站点域名同路径也提供同一套 API**，8/8 全通、平均 0.8s。
        #   所以主入口用站点域名，网关降为备用。这是 Hawk 上「完全没内容」的真凶。
        self.api = SITE_DEFAULT
        self.site = SITE_DEFAULT
        self._bases = []
        self.channel = CHANNEL_DEFAULT
        self.ua = UA_DEFAULT
        # ★ Hawk/FongMi 对 py 源的方法调用只有 15s 级超时，超时就直接当「没内容」，
        #   连诊断卡都看不到。原来是 25s × 3 次重试，光首页就要 16s 以上，真机必被掐断。
        self.timeout = 8
        self.retry = 2
        self.budget = 12         # 单个契约方法允许花在网络上的总秒数（Hawk 掐断约 15s）
        self.lanes = 2           # 抢答并发路数
        self.rounds = 2          # 抢答轮数
        self._deadline = 0
        self._cls_cache = None
        self._net_err = ""
        self.pic_mode = "auto"      # auto | remote | proxy | data | off
        self._proxy_ok = None       # auto 模式下端口探测结果（None=未探测）
        self._http_ok = None        # HTTP 契约自检结果（仅诊断用）
        self.pic_limit = 10         # data 模式下每页最多解密几张（0=全部）
        self.proxy_port = 9978      # proxy 模式下 TVBox 本地代理端口
        self.cdn = ""               # 视频/图片 CDN，留空自动探测
        self.tunnel = "https://1.h8.ccwu.cc/"   # 取图被墙时的中转（URL 前缀式代理）
        self.decrypt_api = DECRYPT_API_DEFAULT  # 公网封面解密代理（首选出图方式）
        self._remote_ok = None                  # 解密代理可用性（None=未探测）
        self.diag_card = 1          # 详情页写入封面自检信息（排查用，1=开）
        # create_default_context 在无证书环境可能抛，抛了整只 Spider 实例化失败，
        # 客户端看到的就是「完全无内容」，所以必须兜住。
        try:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE
        except Exception:
            self.ctx = None
        self.token = ""
        self.token_exp = 0
        self.diag = ""
        self._bases = self._build_bases()
        self._good_base = ""
        self._pic_cache = {}
        self._cdns = []
        self._pic_budget = 0        # 当前这一页还能解几张

    def _build_bases(self):
        """入口池：站点域名优先 → 备用网关。每一路在抢答里各占一条 lane。"""
        out = []
        for b in [self.api, self.site] + list(API_ALTS):
            b = (b or "").rstrip("/")
            if b and b not in out:
                out.append(b)
        return out

    # ---------------- 基础 ----------------
    def getName(self):
        return "Uu影视"

    def init(self, extend=""):
        cfg = {}
        if extend:
            if isinstance(extend, dict):
                cfg = extend
            else:
                try:
                    cfg = json.loads(extend)
                except Exception:
                    cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        if cfg.get("api"):
            a = str(cfg["api"]).strip()
            self.api = a.rstrip("/")
        if cfg.get("site"):
            self.site = str(cfg["site"]).strip().rstrip("/")
        if cfg.get("channel"):
            self.channel = str(cfg["channel"]).strip()
        if cfg.get("cdn"):
            self.cdn = str(cfg["cdn"]).strip().rstrip("/")
        if "tunnel" in cfg:
            self.tunnel = str(cfg.get("tunnel") or "").strip()
            if self.tunnel and not self.tunnel.endswith("/"):
                self.tunnel += "/"
        if "decrypt_api" in cfg:
            self.decrypt_api = str(cfg.get("decrypt_api") or "").strip()
        if cfg.get("diag_card") is not None:
            self.diag_card = int(cfg["diag_card"])
        if cfg.get("pic_mode") in ("auto", "data", "proxy", "off"):
            self.pic_mode = cfg["pic_mode"]
        if cfg.get("pic_limit") is not None:
            self.pic_limit = int(cfg["pic_limit"])
        if cfg.get("proxy_port"):
            self.proxy_port = int(cfg["proxy_port"])
        if cfg.get("timeout"):
            self.timeout = int(cfg["timeout"])
        self._bases = self._build_bases()

    def _headers(self, token=False, json_body=False):
        h = {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "identity",
            "channel": self.channel,
            "Origin": self.site,
            "Referer": self.site + "/",
        }
        if json_body:
            h["Content-Type"] = "application/json"
        if token and self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    def _decode_body(self, resp):
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if "gzip" in enc:
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        elif "deflate" in enc:
            try:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            except Exception:
                pass
        return raw

    def _http_race(self, q, data=None, token=False, raw=False, referer=None,
                   timeout=5, lanes=None, rounds=None):
        """网关会**随机**断连（RemoteDisconnected / SSLError，实测单发成功率约五成，
        间隔 1 秒连发 10 次只过 3 次，冷却后照样断，并发也压不住）。
        唯一稳的办法是短超时 + 多轮抢答：每轮并发几路，任一成功即返回。
        2 路 × 2 轮 ≈ 6~8 秒、成功率 94%+，比串行等 25 秒超时快得多，
        也不会撑爆 Hawk 对 py 源的调用超时。"""
        lanes = lanes or self.lanes
        rounds = rounds or self.rounds
        bases = self._bases or [self.api]
        last = None
        for _ in range(max(1, rounds)):
            if self._deadline and time.time() > self._deadline:
                break
            box = {}
            lock = threading.Lock()

            def worker(idx):
                base = bases[idx % len(bases)]
                try:
                    res = self._http(base + q, data=data, token=token, raw=raw,
                                     referer=referer, retry=1, timeout=timeout)
                    with lock:
                        if "v" not in box:
                            box["v"] = res
                            box["base"] = base
                except Exception as e:
                    with lock:
                        box.setdefault("e", e)

            ts = [threading.Thread(target=worker, args=(i,)) for i in range(max(1, lanes))]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            if "v" in box:
                if box.get("base") and box["base"] != self._good_base:
                    self._good_base = box["base"]
                    self._bases = [box["base"]] + [b for b in self._bases if b != box["base"]]
                return box["v"]
            if "e" in box:
                last = box["e"]
        if last is not None:
            raise last
        raise TimeoutError("网关多次无响应")

    def _http(self, url, data=None, token=False, raw=False, referer=None, retry=None,
              timeout=None):
        last = None
        tries = retry if retry is not None else self.retry
        for attempt in range(max(1, tries)):
            # 预算用尽就别再耗了，直接抛出去让上层回落诊断卡
            if self._deadline and time.time() > self._deadline:
                raise TimeoutError("响应超时(预算%ss用尽)" % self.budget)
            try:
                h = self._headers(token=token, json_body=data is not None)
                if referer:
                    h["Referer"] = referer
                req = urllib.request.Request(url, data=data, headers=h)
                kw = {"timeout": timeout if timeout else self.timeout}
                if self.ctx is not None:
                    kw["context"] = self.ctx
                resp = urllib.request.urlopen(req, **kw)
                body = self._decode_body(resp)
                if raw:
                    return body
                return json.loads(body.decode("utf-8", "replace"))
            except Exception as e:
                last = e
                self._net_err = "%s: %s" % (type(e).__name__, str(e)[:70])
                if attempt + 1 < tries:
                    time.sleep(0.3 * (attempt + 1))
        raise last

    # ---------------- 响应解密（base64url + 与 key 循环异或）----------------
    @staticmethod
    def _unxor(text, key):
        s = str(text or "").strip().replace("-", "+").replace("_", "/")
        s += "=" * ((4 - len(s) % 4) % 4)
        try:
            buf = base64.b64decode(s)
        except Exception:
            return None
        kb = key.encode("utf-8")
        return bytes(b ^ kb[i % len(kb)] for i, b in enumerate(buf)).decode("utf-8", "replace")

    def _api(self, path, params=None, token=False, decrypt=True, retry=None, timeout=None,
             race=True, rounds=None):
        q = path
        if params:
            q += "?" + urllib.parse.urlencode(params)
        try:
            if race and retry is None:
                j = self._http_race(q, token=token, timeout=timeout or 8, rounds=rounds)
            else:
                j = self._http(self.api + q, token=token, retry=retry, timeout=timeout)
        except Exception as e:
            self.diag = "接口异常|%s|%s" % (type(e).__name__, str(e)[:60])
            raise
        if not isinstance(j, dict):
            self.diag = "结构异常"
            raise ValueError("接口结构异常")
        code = j.get("code")
        if code != 200:
            self.diag = "code%s|%s" % (code, str(j.get("message") or "")[:40])
            raise ValueError("code=%s %s" % (code, j.get("message")))
        data = j.get("data")
        if decrypt and isinstance(data, str) and j.get("key"):
            txt = self._unxor(data, j["key"])
            if txt:
                try:
                    data = json.loads(txt)
                except Exception:
                    data = txt
        self.diag = ""
        return data

    # ---------------- 登录（免账号指纹登录）----------------
    def _fingerprint(self):
        h = 2166136261
        for ch in (self.ua + self.channel):
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
        return "fp-%08x" % h

    def _login(self):
        for base in (self._bases or [self.api]):
            try:
                body = json.dumps({"channel": self.channel,
                                   "fingerPrint": self._fingerprint()}).encode()
                j = self._http(base + "/api-user/v2/login/fingerprint", data=body,
                               retry=2, timeout=5)
                dd = j.get("data") if isinstance(j, dict) else None
                if isinstance(dd, str) and j.get("key"):
                    dd = json.loads(self._unxor(dd, j["key"]) or "{}")
                tok = (dd or {}).get("accessToken")
                if tok:
                    self.api = base
                    self.token = tok
                    self.token_exp = time.time() + int((dd or {}).get("accessTokenTtl") or 1500) - 60
                    return tok
            except Exception as e:
                self.diag = "登录失败|%s" % str(e)[:50]
                continue
        return ""

    def _ensure_token(self):
        if self.token and time.time() < self.token_exp:
            return self.token
        return self._login()

    # ---------------- CDN / 封面 ----------------
    def _pick_cdn(self):
        if self.cdn:
            return self.cdn
        if not self._cdns:
            try:
                d = self._api("/api/v2/home/public/cdn/index", {"channel": self.channel}) or {}
                for it in (d.get("list") or []):
                    u = str(it.get("videoUrl") or "").rstrip("/")
                    if u.startswith("http") and CDN_SKIP_HOST not in u and u not in self._cdns:
                        self._cdns.append(u)
            except Exception:
                pass
            if not self._cdns:
                # 兜底：实测可用的图片/视频 CDN 家族
                self._cdns = ["https://jqsp.xn--xhq15jk0k96h.cn",
                              "https://lmcsxdd.xn--xhq15jk0k96h.cn",
                              "https://jqsp34.xn--xhq15jk0k96h.cn"]
        self.cdn = self._cdns[0]
        return self.cdn

    def _pic_url(self, thumb):
        """相对 thumb → CDN 上的加密图完整地址"""
        t = str(thumb or "").strip()
        if not t:
            return ""
        if t.startswith("http"):
            return t
        if not t.startswith("/"):
            t = "/" + t
        return "%s/%s%s" % (self._pick_cdn(), PIC_BUCKET, t)

    def _pic_bytes(self, url):
        """下载 .enc 并解密成 JPEG；带缓存 + 多线路故障转移 + 隧道兜底"""
        if not url:
            return b""
        hit = self._pic_cache.get(url)
        if hit:
            return hit
        # 候选顺序：原地址 → 同路径换 CDN → 隧道代理
        cands = [url]
        parts = url.split("/", 3)
        if len(parts) == 4:
            path = parts[3]
            base0 = "%s://%s" % (parts[0], parts[1])
            for base in self._cdns:
                if base and base != base0:
                    alt = base + "/" + path
                    if alt not in cands:
                        cands.append(alt)
        if self.tunnel:
            cands.append(self.tunnel + url)
        self.diag = ""
        for c in cands:
            try:
                raw = self._http(c, raw=True, retry=1)
            except Exception as e:
                self.diag = "取图失败|%s" % type(e).__name__
                continue
            if raw[:3] == b"\xff\xd8\xff":
                data = raw
            else:
                try:
                    data = aes_cbc_decrypt(PIC_KEY, raw)
                except Exception:
                    data = b""
            if data[:3] != b"\xff\xd8\xff":
                self.diag = "解密失败|%dB" % len(raw)
                continue
            end = data.rfind(b"\xff\xd9")
            if end > 0:
                data = data[:end + 2]
            if len(self._pic_cache) > 400:
                self._pic_cache.clear()
            self._pic_cache[url] = data
            self.diag = ""
            return data
        return b""

    def _proxy_url(self, url):
        return "http://127.0.0.1:%d/proxy?do=py&u=%s" % (
            self.proxy_port, urllib.parse.quote(url, safe=""))

    def _remote_pic(self, enc):
        """把加密图交给公网解密代理，拿回一个「普通 https 图片地址」"""
        api = self.decrypt_api or ""
        if not api:
            return ""
        return "%s%s&key=%s" % (api,
                                urllib.parse.quote(enc, safe=""),
                                urllib.parse.quote(PIC_KEY_STR, safe=""))

    def _probe_remote(self, enc):
        """源内先验一次：解密代理真能吐 JPEG 才用它"""
        url = self._remote_pic(enc)
        if not url:
            return False
        try:
            body = self._http(url, raw=True, retry=1)
            return body[:3] == b"\xff\xd8\xff"
        except Exception:
            return False

    def _port_alive(self):
        """只看端口在不在听。在客户端进程里跑时 127.0.0.1 一定可达，
        扫描只是把端口号试出来（9978 不是所有分支都用）。"""
        for port in [self.proxy_port, 9978, 9979, 1234, 8080, 10086]:
            if not port:
                continue
            sock = socket.socket()
            sock.settimeout(0.25)
            try:
                sock.connect(("127.0.0.1", port))
                self.proxy_port = port
                return True
            except Exception:
                continue
            finally:
                try:
                    sock.close()
                except Exception:
                    pass
        return False

    def _probe_port(self, enc_url):
        """HTTP 层自检：真的打一次本地代理，能拿回 JPEG 才算契约正确（仅诊断用）"""
        try:
            url = self._proxy_url(enc_url)
            req = urllib.request.Request(url, headers={"User-Agent": self.ua})
            resp = urllib.request.urlopen(req, timeout=6, context=self.ctx)
            head = resp.read(4)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            return head[:3] == b"\xff\xd8\xff" or "image" in ctype
        except Exception:
            return False

    def _pic(self, thumb):
        mode = self.pic_mode
        if mode == "off" or not thumb:
            return ""
        enc = self._pic_url(thumb)
        if not enc:
            return ""
        if mode == "auto":
            # 优先级：公网解密代理 → 本地代理 → data URI，逐级回落
            if self._remote_ok is None:
                self._remote_ok = self._probe_remote(enc)
            if self._remote_ok:
                mode = "remote"
            else:
                if self._proxy_ok is None:
                    self._proxy_ok = self._port_alive()
                    if self._proxy_ok:
                        self._http_ok = self._probe_port(enc)
                mode = "proxy" if self._proxy_ok else "data"
        if mode == "remote":
            return self._remote_pic(enc)
        if mode == "proxy":
            return self._proxy_url(enc)
        # data 模式：受 pic_limit 限流，避免首页一次性解密太多拖慢
        if self.pic_limit and self._pic_budget <= 0:
            return ""
        data = self._pic_bytes(enc)
        if not data:
            return ""
        if self.pic_limit:
            self._pic_budget -= 1
        return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")

    def _pic_diag(self, thumb):
        """把封面链路的自检结果写进详情页正文 —— 用户不用看日志就能反馈卡在哪一步"""
        out = ["【封面自检】"]
        out.append("模式=%s 解密代理=%s 端口=%s" % (
            self.pic_mode,
            {None: "未跑", True: "可用", False: "不可用"}[self._remote_ok],
            self.proxy_port))
        out.append("本地代理端口探测=%s HTTP自检=%s" % (
            {None: "未跑", True: "通", False: "不通"}[self._proxy_ok],
            {None: "未跑", True: "拿到JPEG", False: "没拿到JPEG"}[self._http_ok]))
        enc = self._pic_url(thumb) if thumb else ""
        if not enc:
            out.append("图地址=空（这条没 thumb）")
            return "\n".join(out)
        out.append("图源=%s" % enc[:78])
        try:
            raw = self._http(enc, raw=True, retry=1)
            out.append("直取=%d 字节 头=%s" % (len(raw), raw[:4].hex()))
            if raw[:3] != b"\xff\xd8\xff":
                try:
                    d = aes_cbc_decrypt(PIC_KEY, raw)
                    out.append("本地解密=%d 字节 头=%s" % (len(d), d[:4].hex()))
                except Exception as e:
                    out.append("本地解密异常=%s" % type(e).__name__)
        except Exception as e:
            out.append("直取异常=%s" % type(e).__name__)
        pic = self._pic(thumb) or ""
        out.append("最终vod_pic=%s" % (pic[:90] if pic else "(空)"))
        out.append("（{\"diag_card\":0} 可关闭本段）")
        return "\n".join(out)

    # ---------------- 数据映射 ----------------
    def _clean(self, s):
        s = str(s or "")
        s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
        s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
        return s.strip()

    def _html2text(self, s):
        s = str(s or "").replace("\r", "\n")
        s = re.sub(r"(?i)<br\s*/?>", "\n", s)
        s = re.sub(r"(?i)</p>", "\n", s)
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"[ \t]+", " ", self._clean(s))
        return re.sub(r"\n{3,}", "\n\n", s).strip()

    def _vod(self, it):
        vid = str(it.get("id") or "")
        name = self._clean(it.get("title")) or ("视频 " + vid)
        tags = self._clean(it.get("labelTitles") or it.get("classifyTitles"))
        remark = tags.replace(",", " · ")[:30] if tags else ""
        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": self._pic(it.get("thumb")),
            "vod_remarks": remark or self._clean(it.get("createdAt"))[:10],
            "type_name": tags,
        }

    def _classes(self):
        if self._cls_cache:
            return list(self._cls_cache)
        cls = [{"type_id": k, "type_name": n} for k, n in FIXED_TYPES]
        try:
            # 分类表只给一次机会、5 秒上限：它决定首页能不能及时出内容，
            # 拿不到就用 3 个固定分类顶上，不能把整个首页拖到超时。
            d = self._api("/api/v2/home/public/video/cate/list", {"type": "long"},
                          timeout=5, rounds=1) or {}
            items = d.get("list") or []
            items = [x for x in items if str(x.get("title") or "").strip()]
            items.sort(key=lambda x: (x.get("sort") or 999, x.get("id") or 0))
            for it in items:
                cls.append({"type_id": "c%s" % it.get("id"), "type_name": self._clean(it.get("title"))})
            self._cls_cache = list(cls)
        except Exception:
            pass
        return cls

    def _arm(self):
        """给本次契约方法调用装上网络预算，保证一定在 Hawk 掐断之前返回"""
        try:
            self._deadline = time.time() + self.budget
        except Exception:
            self._deadline = 0

    def _diag_card(self, where):
        extra = self.diag or "无数据"
        if self._net_err and self._net_err not in extra:
            extra += " | 网络:" + self._net_err
        return [{
            "vod_id": "diag",
            "vod_name": "[诊断] %s | %s" % (where, extra),
            "vod_pic": "",
            "vod_remarks": "网关抖动/稍后重试",
            "vod_content": "接口：%s\n原因：%s\n可在配置里覆盖：{\"api\":\"https://新域名:51000\"}\n可用网关见源码注释。"
                           % (self.api, extra),
        }]

    def _list(self, params, pg):
        d = self._api("/api/v2/home/public/video/list", params) or {}
        lst = d.get("list") or []
        total = int(d.get("total") or 0)
        limit = int(params.get("limit") or 20)
        self._pic_budget = self.pic_limit if self.pic_limit else 999
        return {
            "page": pg,
            "pagecount": max(1, (total + limit - 1) // limit) if total else pg,
            "limit": limit,
            "total": total,
            "list": [self._vod(it) for it in lst],
        }

    # ---------------- 契约方法 ----------------
    def homeContent(self, filter):
        self._arm()
        # 分类表 + 首页列表两条腿并行跑，冷启动从 9s 压到 5s 左右，
        # 避免 Hawk 的调用超时（约 15s）把首页整个掐掉。
        box = {}

        def work():
            try:
                box["list"] = self.categoryContent("last", 1, False, {}).get("list") or []
            except Exception:
                box["list"] = []

        th = threading.Thread(target=work)
        th.start()
        try:
            cls = self._classes()
        except Exception:
            cls = [{"type_id": k, "type_name": n} for k, n in FIXED_TYPES]
        th.join()
        res = {"class": cls, "filters": {}, "list": box.get("list") or []}
        if filter:
            # Hawk 部分版本会遍历 filters 的 value 数组，给 {tid: []} 反而让页面异常
            res["filters"] = {}
        if not res["list"]:
            res["list"] = self._diag_card("首页")
        return res

    def homeVideoContent(self):
        self._arm()
        try:
            lst = self.categoryContent("last", 1, False, {})["list"]
            return {"list": lst or self._diag_card("推荐")}
        except Exception:
            return {"list": self._diag_card("推荐")}

    def categoryContent(self, tid, pg, filter, extend):
        self._arm()
        try:
            pg = max(1, int(pg or 1))
        except Exception:
            pg = 1
        tid = str(tid or "last")
        params = {"page": pg, "limit": 20, "videoType": "long"}
        try:
            # 注意：last 也以 l 开头，必须先判固定类型再判前缀
            if tid in ("last", "hot", "good", "collect"):
                params["type"] = tid
            elif tid.startswith("c") and tid[1:].isdigit():
                params["type"] = "cate"
                params["typeId"] = tid[1:]
            elif tid.startswith("l") and tid[1:].isdigit():
                params["type"] = "label"
                params["typeId"] = tid[1:]
            else:
                params["type"] = "last"
            out = self._list(params, pg)
            # 站点把一部分分类（探花/新闻/VR 等）的数据挂在 label 表上，
            # cate 查出来是 0 条，这里自动降级到 label 再查一次
            if not out["list"] and params.get("type") == "cate":
                alt = dict(params)
                alt["type"] = "label"
                try:
                    out2 = self._list(alt, pg)
                    if out2["list"]:
                        out = out2
                except Exception:
                    pass
            # 真·空分类不算错误，返回空列表即可（诊断卡只留给接口报错）
            if not out["list"] and self.diag:
                out["list"] = self._diag_card("分类%s" % tid)
            return out
        except Exception:
            return {"page": pg, "pagecount": pg, "limit": 20, "total": 0,
                    "list": self._diag_card("分类%s" % tid)}

    def detailContent(self, ids):
        self._arm()
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        if not vid or vid == "diag":
            return {"list": []}
        try:
            it = self._api("/api/v2/home/public/video/long/detail", {"id": vid}) or {}
            self._pic_budget = self.pic_limit if self.pic_limit else 999
            v = self._vod(it)
            tags = self._clean(it.get("labelTitles") or it.get("classifyTitles"))
            content = self._html2text(it.get("content"))
            head = []
            if it.get("createdAt"):
                head.append("时间：%s" % it["createdAt"])
            if tags:
                head.append("标签：%s" % tags)
            if it.get("author"):
                head.append("作者：%s" % self._clean(it.get("author")))
            if it.get("viewCount"):
                head.append("播放：%s" % it.get("viewCount"))
            body = "\n".join(head)
            if content:
                body += ("\n\n" + content)
            v["vod_content"] = body.strip()
            if self.diag_card:
                v["vod_content"] = (v["vod_content"] + "\n\n" + self._pic_diag(it.get("thumb"))).strip()
            v["vod_actor"] = self._clean(it.get("actor"))
            v["vod_year"] = self._clean(it.get("createdAt"))[:4]
            # 线路 = 码率档位，id 里带档位，playerContent 再取流
            v["vod_play_from"] = "高清720P$$$标清480P"
            # 两条线路用 $$$ 分隔（同一线路内分集才用 #）
            v["vod_play_url"] = "第01集$%s@@720p$$$第01集$%s@@480p" % (vid, vid)
            return {"list": [v]}
        except Exception:
            return {"list": self._diag_card("详情%s" % vid)}

    def searchContent(self, key, quick, page="1"):
        self._arm()
        try:
            pg = max(1, int(page or 1))
        except Exception:
            pg = 1
        try:
            d = self._api("/api/v2/home/public/video/search",
                          {"page": pg, "limit": 20, "keyword": key, "videoType": "long"}) or {}
            lst = d.get("list") or []
            self._pic_budget = self.pic_limit if self.pic_limit else 999
            if not lst:
                return {"list": self._diag_card("搜索「%s」无结果" % key)}
            return {"list": [self._vod(it) for it in lst]}
        except Exception:
            return {"list": self._diag_card("搜索「%s」" % key)}

    def playerContent(self, flag, id, vipFlags):
        """★ 播放链路三大坑（2026-10-29 排查 OK影视/FongMi 播放失败所得）：
        1) 站点默认给 cdnId=2（jrsb.aiide.online）—— 那是**反诈跳转型 CDN**，
           分片请求 301 到 www.js96110.com.cn（反诈中心），播放器加载分片必失败。
           cdnId=1（jqsp.xn--xhq15jk0k96h.cn）才是真 CDN，分片 1.2MB 正常。
        2) m3u8 需要 Referer（403 Forbidden），但**分片不需要**。
           FongMi/OK影视 把 header 同时套在 m3u8 和分片上 → 分片被 Referer 挡。
           所以这里只给 m3u8 必需的 Referer，**不传多余 header**。
        3) 站点域名(51888) 证书合法（verify=0），网关(51000) 自签证书，
           ExoPlayer 严格校验会直接拒绝 → 必须用站点域名。
        """
        self._arm()
        raw = str(id or "").strip()
        vid, _, variant = raw.partition("@@")
        variant = variant or "720p"
        # 只给 m3u8 拉取必需的 header；分片和 key 都不需要 Referer
        header = {"User-Agent": self.ua, "Referer": self.site + "/"}
        try:
            self._ensure_token()
            d = self._api("/api/v2/home/user/video/play/url",
                          {"id": vid, "channel": self.channel}, token=True) or {}
            key = {"720p": "p720Url", "480p": "p480Url"}.get(variant, "masterUrl")
            url = str(d.get(key) or d.get("p720Url") or d.get("masterUrl") or "")
            if url:
                if url.startswith("/"):
                    url = self.api + url
                # 站点默认 cdnId=2 是反诈跳转域名，强制改成 cdnId=1（真 CDN）
                if "cdnId=2" in url:
                    url = url.replace("cdnId=2", "cdnId=1", 1)
                return {"parse": 0, "playUrl": "", "url": url, "header": header}
            self.diag = "取流为空"
        except Exception as e:
            self.diag = "取流失败|%s" % str(e)[:60]
        # 兜底：交给客户端外置解析，绝不返回空串
        return {"parse": 1, "playUrl": "", "url": "%s/video/player/embed?id=%s" % (self.site, vid),
                "header": header, "jx": 1}

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return ".m3u8" in u or ".mp4" in u

    def localProxy(self, param):
        """本地代理：把加密封面解成 JPEG 交给客户端。

        参数解析做了三重兜底 —— 有的客户端会把 vod_pic 再套一层自己的图片代理，
        导致 `u` 的键名被改、或者 `&` 被转义成 `&amp;`，不兜住就整页无图：
          1) 按常见键名取
          2) 任意键只要能组成 http 地址就用
          3) 直接在原始串里正则捞 http(s) 片段
        非 .enc 的资源（m3u8/分片）原样透传，顺便把 Referer 补齐。"""
        # Hawk 调用 localProxy 时 param 是 dict、返回体要 base64；FongMi/TVBox 传 query 串、要 bytes
        _hawk = isinstance(param, dict)

        def _pack(code, ctype, body):
            if _hawk and isinstance(body, (bytes, bytearray)):
                return [code, ctype, base64.b64encode(bytes(body)).decode("ascii")]
            return [code, ctype, body]

        try:
            if isinstance(param, dict):
                raw = urllib.parse.urlencode(param)
            else:
                raw = str(param or "")
            u = ""
            q = dict(urllib.parse.parse_qsl(raw.lstrip("?"), keep_blank_values=True))
            for k in ("u", "url", "src", "img", "image", "path", "p", "link"):
                v = q.get(k)
                if isinstance(v, str) and v.lower().startswith("http"):
                    u = v
                    break
            if not u:
                for v in q.values():
                    if isinstance(v, str) and v.lower().startswith("http"):
                        u = v
                        break
            if not u:
                m = re.search(r"https?%3A%2F%2F[^&\s\"']+", raw, re.I)
                if m:
                    u = urllib.parse.unquote(m.group(0))
                else:
                    m = re.search(r"https?://[^&\s\"']+", raw, re.I)
                    if m:
                        u = m.group(0)
            u = (u or "").strip()
            if not u:
                return _pack(404, "text/plain", b"no url")
            low = u.lower()
            if low.endswith(".enc") or "/encryption-ts/" in low:
                data = self._pic_bytes(u)
                if data:
                    return _pack(200, "image/jpeg", data)
                return _pack(404, "text/plain", b"decrypt failed")
            # 分片/key 不吃 Referer（实测给 Referer 反而被 CDN 挡），只透传 UA
            body = self._http(u, raw=True, retry=1)
            ctype = "application/vnd.apple.mpegurl" if low.endswith(".m3u8") else "application/octet-stream"
            return _pack(200, ctype, body)
        except Exception:
            return _pack(404, "text/plain", b"error")

    def destroy(self):
        pass


# ---------------- 自检 ----------------
if __name__ == "__main__":
    s = Spider()
    s.init({"pic_limit": 2})          # 自检只解 2 张封面，省时间
    print("网关:", s.api, "| 站点:", s.site, "| channel:", s.channel)

    h = s.homeContent(True)
    print("\n[首页] 分类数=%d 首页条数=%d" % (len(h["class"]), len(h["list"])))
    print("  封面模式=%s 公网解密代理=%s" % (s.pic_mode,
          {None: "未探测", True: "可用", False: "不可用"}[s._remote_ok]))
    print("  分类:", " ".join("%s=%s" % (c["type_id"], c["type_name"]) for c in h["class"]))
    if h["list"]:
        v = h["list"][0]
        print("  首条:", v["vod_name"][:40], "| 角标:", v["vod_remarks"])
        print("  封面:", (v["vod_pic"][:60] + "...") if v["vod_pic"] else "(空)")

    for tid in ("last", "hot", "good", "c262", "c360", "c357", "c346"):
        c = s.categoryContent(tid, 1, False, {})
        print("\n[分类 %-5s] 条数=%d pagecount=%s total=%s 首条=%s"
              % (tid, len(c["list"]), c["pagecount"], c["total"],
                 c["list"][0]["vod_name"][:26] if c["list"] else "-"))

    c2 = s.categoryContent("last", 2, False, {})
    print("[最新 第2页] 条数=%d 首条=%s" % (len(c2["list"]),
          c2["list"][0]["vod_name"][:26] if c2["list"] else "-"))

    if h["list"]:
        vid = h["list"][0]["vod_id"]
        d = s.detailContent([vid])
        if d["list"]:
            v = d["list"][0]
            print("\n[详情 %s] %s" % (vid, v["vod_name"][:36]))
            print("  线路:", v["vod_play_from"])
            print("  播放串:", v["vod_play_url"][:80])
            first = v["vod_play_url"].split("$$$")[0].split("$", 1)[1]
            p = s.playerContent(v["vod_play_from"], first, None)
            print("  playerContent: parse=%s" % p["parse"])
            print("  地址:", p["url"][:110])
            # 实测取 m3u8（必须带 Referer）
            try:
                body = s._http(p["url"], raw=True, referer=s.site + "/", retry=1)
                txt = body.decode("utf-8", "replace")
                print("  m3u8 前 90 字:", txt[:90].replace("\n", " / "))
                print("  含 EXT-X-KEY:", "EXT-X-KEY" in txt, "| 行数:", len(txt.splitlines()))
            except Exception as e:
                print("  m3u8 拉取失败:", type(e).__name__, str(e)[:60])

    sc = s.searchContent("国产", False, "1")
    print("\n[搜索 国产] 条数=%d 首条=%s" % (len(sc["list"]),
          sc["list"][0]["vod_name"][:30] if sc["list"] else "-"))
    sc2 = s.searchContent("国产", False, "2")
    print("[搜索 第2页] 条数=%d 首条=%s" % (len(sc2["list"]),
          sc2["list"][0]["vod_name"][:30] if sc2["list"] else "-"))

    # 封面解密自检
    try:
        raw_thumb = s._api("/api/v2/home/public/video/list",
                           {"page": 1, "limit": 1, "videoType": "long", "type": "last"})
        thumb = (raw_thumb.get("list") or [{}])[0].get("thumb")
        u = s._pic_url(thumb)
        print("\n[封面] 地址:", u[:100])
        data = s._pic_bytes(u)
        print("  解密后 %d 字节，JPEG 头: %s" % (len(data), data[:4].hex()))
    except Exception as e:
        print("\n[封面] 自检异常:", type(e).__name__, str(e)[:80])

    print("\n自检结束。diag=", s.diag or "无")
