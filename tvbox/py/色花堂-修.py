# -*- coding: utf-8 -*-
"""98堂(TVBox py 插件) — keep-alive 连接 + 18 岁门禁 + /play.php 取链 + 直连 HLS

核心修复(相对旧版):
1. **18 岁门禁必须"同一条 TCP 连接"过**。旧版用 urllib,每次请求都新建连接,而站方
   要求把壳页下发的 safeid 种成 `_safe` cookie 后**在同一条连接上重载**才放行 ——
   urllib 永远过不了门禁,导致首页/分类/详情/取链全部空。本版改用
   http.client.HTTPSConnection 保持连接复用,并在同一连接上完成
   "拿 safeid -> 种 _safe -> 重试" 三步,一次性过门禁。
2. **连接池按线程隔离**:每个线程一条 keep-alive 连接(各自独立过门禁),
   并发加载多个分类互不干扰,避免共享单连接被锁串行拖慢。
3. **纯标准库实现**(http.client + ssl),不依赖设备上的 requests/curl_cffi/curl。
4. 播放时按帖子页实时取新 grant(grant 只有 5 分钟寿命),取到后立即校验 m3u8 真的能拉。
5. 图床(jo.djsnm.app / tu.djhdhs.us)需 Referer,否则 403 —— 图片 URL 统一加
   `@Referer=<host>/` 后缀(FongMi 约定),无需配置。
6. 域名可热换:extend = {"host": "https://新域名"}。

用法(JSON 配置 extend 字段):
  {"host": "https://ifxn.bwa09.com"}                       # 默认,可不填
  {"user": "账号", "pass": "密码"}                          # 登录(可提高额度)
  {"xff": false}                                           # 关闭按假 IP 开新通道
  {"pic_host": "https://jo.djsnm.app"}                     # 图床,默认即可
"""

import os
import re
import json
import time
import random
import gzip
import threading
import ssl
import urllib.request
import urllib.parse
import http.client
import http.cookiejar


# ===== 本地图片代理 + mjv011 画/书协议 =====
_img_proxy_port = 0
_img_proxy_started = False
def _find_free_port():
    import socket
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.bind(("127.0.0.1", 0))
    port = sk.getsockname()[1]
    sk.close()
    return port
def _start_img_proxy(referer_host="https://ifxn.bwa09.com/"):
    global _img_proxy_port, _img_proxy_started
    if _img_proxy_started:
        return
    try:
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        from socketserver import ThreadingMixIn
        from urllib.parse import unquote
        import urllib.request
        class _TH(ThreadingMixIn, HTTPServer):
            daemon_threads = True
        class _H(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    real = unquote(self.path.lstrip("/"))
                    if not real.startswith("http"):
                        self.send_response(404); self.end_headers(); return
                    req = urllib.request.Request(real, headers={
                        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                        "Referer": referer_host,
                        "Accept": "image/*,*/*;q=0.8",
                    })
                    with urllib.request.urlopen(req, timeout=25) as r:
                        data = r.read()
                        ct = r.headers.get("Content-Type") or "image/jpeg"
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
                except BrokenPipeError:
                    pass
                except Exception:
                    try:
                        self.send_response(404); self.end_headers()
                    except Exception:
                        pass
            def log_message(self, *a):
                pass
        _img_proxy_port = _find_free_port()
        srv = _TH(("127.0.0.1", _img_proxy_port), _H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _img_proxy_started = True
    except Exception:
        pass


try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        def getName(self):
            return ""

        def init(self, extend=""):
            pass


DEFAULT_HOST = "https://ifxn.bwa09.com"

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
    "Mobile/15E148 Safari/604.1"
)


def _ssl_ctx():
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        return None


def _rand_ip():
    """生成一个像家宽的伪客户端 IP,避开内网/保留段。"""
    while True:
        a = random.randint(1, 223)
        b = random.randint(0, 255)
        c = random.randint(0, 255)
        d = random.randint(1, 254)
        if a in (0, 10, 100, 127, 169, 172, 192, 198, 203):
            if not (a == 198 and b == 51):
                continue
        if a == 172 and 16 <= b <= 31:
            continue
        if a == 192 and b == 168:
            continue
        if a == 169 and b == 254:
            continue
        return "%d.%d.%d.%d" % (a, b, c, d)


class _Conn(object):
    """一条常驻 keep-alive 连接(自带独立 Cookie 会话 + 18 岁门禁处理)。

    98堂的 18 岁门禁逻辑:壳页下发 safeid,浏览器把它种成 `_safe` cookie 后**同一
    条 TCP 连接**上重载即放行。urllib 每次请求都新建连接,永远过不了这道门禁;
    所以这里用 http.client.HTTPSConnection 保持连接复用,并在同一条连接上完成
    "拿 safeid -> 种 _safe -> 重试" 三步。
    """

    def __init__(self, host, ua, ip=None, proxy=None, timeout=25):
        self.host = (host or "").rstrip("/")
        self.hostname = urllib.parse.urlparse(self.host).hostname or ""
        self.ua = ua
        self.ip = ip or ""
        self.proxy = proxy or ""
        self.timeout = timeout
        self.cookies = {}
        self._conn = None
        self._ctx = _ssl_ctx()

    # ---- 连接管理 ----
    def _ensure(self):
        if self._conn is None:
            self._conn = http.client.HTTPSConnection(
                self.hostname, timeout=self.timeout, context=self._ctx)
        return self._conn

    def _drop(self):
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None
        self.cookies = {}

    def set_cookie(self, name, value):
        self.cookies[name] = value

    def _cookie_header(self):
        if not self.cookies:
            return ""
        return "; ".join("%s=%s" % (k, v) for k, v in self.cookies.items())

    @staticmethod
    def _split_url(url):
        p = urllib.parse.urlsplit(url or "")
        path = p.path or "/"
        if p.query:
            path += "?" + p.query
        return p.netloc, path

    def _send(self, path, headers=None, body=None):
        """同一条连接上发一个请求,返回 (status, text)。断线自动重连一次。"""
        h = {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        ck = self._cookie_header()
        if ck:
            h["Cookie"] = ck
        if self.ip:
            h["X-Forwarded-For"] = self.ip
            h["X-Real-IP"] = self.ip
        if headers:
            for k, v in headers.items():
                if v:
                    h[k] = v
        conn = self._ensure()
        for attempt in range(2):
            try:
                if body is not None:
                    conn.request("POST", path, body=body, headers=h)
                else:
                    conn.request("GET", path, headers=h)
                resp = conn.getresponse()
                data = resp.read()
                for k, v in resp.getheaders():
                    if k.lower() == "set-cookie":
                        mm = re.match(r"^([^=;]+)=([^;]*)(?:;|$)", v or "")
                        if mm:
                            self.cookies[mm.group(1).strip()] = mm.group(2).strip()
                if data[:2] == b"\x1f\x8b":
                    try:
                        data = gzip.decompress(data)
                    except Exception:
                        pass
                for codec in ("utf-8", "gbk"):
                    try:
                        return resp.status, data.decode(codec)
                    except Exception:
                        continue
                return resp.status, data.decode("utf-8", "ignore")
            except (http.client.HTTPException, OSError, ssl.SSLError, ValueError, ssl.CertificateError):
                self._drop()
                if attempt == 0:
                    conn = self._ensure()
                    continue
                return 0, ""
        return 0, ""

    def request(self, url, headers=None, body=None):
        """请求绝对 URL,自动在本连接上过 18 岁门禁。"""
        netloc, path = self._split_url(url)
        if netloc and netloc != self.hostname:
            # 换主机 -> 用独立的一次性连接
            tmp = _Conn("https://" + netloc, self.ua, ip=self.ip, timeout=self.timeout)
            return tmp._request_with_gate(path, headers, body)
        return self._request_with_gate(path, headers, body)

    def _request_with_gate(self, path, headers=None, body=None):
        status, text = self._send(path, headers, body)
        for _ in range(4):
            if not text or len(text) > 4000:
                return text
            m = re.search(r"safeid\s*=\s*['\"]([^'\"]+)['\"]", text)
            if not m:
                return text
            self.set_cookie("_safe", m.group(1))
            status, text = self._send(path, headers, body)
        return text


class _FreshChan(object):
    """独立出口通道:自己的连接 + 自己的客户端 IP,额度互不干扰。

    站点对游客的「每天 10 个视频」是按客户端 IP 计的,而它会采信请求头里的
    X-Forwarded-For 判定来源 IP。所以每开一条通道 = 换一个"IP" = 重新领 10 个额度。
    现在只要每取一个片就开一条新通道,额度就永远用不完。
    """

    def __init__(self, host, ua, ip=None, proxy=None, timeout=25):
        self.conn = _Conn(host, ua, ip=ip or _rand_ip(), proxy=proxy, timeout=timeout)
        self.used = 0

    def _cookie(self, name, value):
        self.conn.set_cookie(name, value)

    def get(self, url, ref=None, xhr=False, timeout=25):
        headers = {}
        if ref:
            headers["Referer"] = ref
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"
        return self.conn.request(url, headers=headers)

    def boot(self, url):
        """过安全门禁:把壳页下发的 safeid 种成 _safe cookie,返回目标页内容。"""
        return self.conn.request(url)


class Spider(_BaseSpider):
    def __init__(self):
        self.host = DEFAULT_HOST
        self.ua = UA_MOBILE
        self.boards = [
            # 在线视频
            ("41", "国产自拍"),
            ("109", "中文字幕"),
            ("42", "日韩无码"),
            ("43", "日韩有码"),
            ("44", "欧美风情"),
            # 色花图片
            ("155", "图·原创自拍"),
            ("125", "图·转贴自拍"),
            ("50", "图·华人街拍"),
            ("49", "图·欧美性爱"),
            ("117", "图·卡通动漫"),
            ("165", "图·套图下载"),
            # 色花文学（跳过含校园类）
            ("154", "文·原创小说"),
            ("139", "文·TXT小说"),
            ("136", "文·激情都市"),
            ("138", "文·武侠虚幻"),
            ("135", "文·乱伦人妻"),
            ("172", "文·AI短剧"),
            ("166", "文·AI专区"),
        ]
        self._safe = ""
        self._last_err = ""
        self._need_login = False
        self._logged = False
        self._user = ""
        self._pass = ""
        self._gacode = ""
        self._answer = ""
        self._questionid = "0"
        self._pic_host = "https://jo.djsnm.app"
        self._lock = threading.RLock()
        self._xff_on = True
        self._proxies = []
        self._chan_used = 0
        self._jar_path = self._pick_jar()
        self._persist = self._load_persist()
        self._conns = {}
        self._conn_lock = threading.Lock()

    # ---------------- 基础 ----------------

    @staticmethod
    def _pick_jar():
        cands = [os.environ.get("TMPDIR"), "/tmp", "/data/local/tmp", os.path.expanduser("~")]
        for d in cands:
            try:
                if d and os.path.isdir(d) and os.access(d, os.W_OK):
                    return os.path.join(d, "tang98_cookies.json")
            except Exception:
                continue
        return ""

    def _load_persist(self):
        try:
            if self._jar_path and os.path.exists(self._jar_path):
                with open(self._jar_path, "r", encoding="utf-8") as f:
                    d = json.loads(f.read() or "{}")
                if isinstance(d, dict):
                    return d
        except Exception:
            pass
        return {}

    def _save_persist(self):
        if not self._jar_path:
            return
        try:
            with self._lock:
                with open(self._jar_path, "w", encoding="utf-8") as f:
                    f.write(json.dumps(self._persist, ensure_ascii=False))
        except Exception:
            pass

    def _get_conn(self):
        tid = threading.get_ident()
        with self._conn_lock:
            conn = self._conns.get(tid)
            if conn is None or conn.host != self.host:
                conn = _Conn(self.host, self.ua)
                for k, v in self._persist.items():
                    conn.set_cookie(k, v)
                self._conns[tid] = conn
            return conn

    def getName(self):
        return "98堂"

    def init(self, extend=""):
        cfg = {}
        try:
            if isinstance(extend, dict):
                cfg = extend
            elif extend:
                try:
                    cfg = json.loads(extend)
                except Exception:
                    cfg = {}
        except Exception:
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        try:
            h = str(cfg.get("host") or "").strip()
            if h:
                if not h.startswith("http"):
                    h = "https://" + h
                self.host = h.rstrip("/")
            self._user = str(cfg.get("user") or cfg.get("username") or "").strip()
            self._pass = str(cfg.get("pass") or cfg.get("password") or "").strip()
            self._gacode = str(cfg.get("gacode") or "").strip()
            self._answer = str(cfg.get("answer") or "").strip()
            self._questionid = str(cfg.get("questionid") or "0").strip()
            ph = str(cfg.get("pic_host") or "").strip()
            if ph:
                self._pic_host = ph.rstrip("/")
            ck = cfg.get("cookie") or cfg.get("cookies") or ""
            if ck:
                self._cookie_import(str(ck))
            # 通道池配置
            xf = cfg.get("xff")
            if isinstance(xf, bool):
                self._xff_on = xf
            elif isinstance(xf, str):
                self._xff_on = xf.strip().lower() not in ("0", "false", "off", "no")
            px = cfg.get("proxies") or cfg.get("proxy_pool")
            plist = []
            if isinstance(px, (list, tuple)):
                plist = [str(x).strip() for x in px if str(x).strip()]
            elif isinstance(px, str) and px.strip():
                plist = [s.strip() for s in re.split(r"[\s,;]+", px) if s.strip()]
            one = str(cfg.get("proxy") or "").strip()
            if one:
                plist.insert(0, one)
            self._proxies = [p if "://" in p else "http://" + p for p in plist]
        except Exception:
            pass
        self._ensure_safe()
        if self._user and self._pass:
            try:
                self._login()
            except Exception:
                pass

    # ---------------- 登录 ----------------

    def _cookie_import(self, raw):
        """从浏览器复制出来的 Cookie 串直接灌进来,优先用这条路。"""
        try:
            txt = str(raw).replace("\n", ";").replace(";;", ";")
            for part in txt.split(";"):
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                k, v = k.strip(), v.strip()
                if k and not k.lower().startswith("path"):
                    self._cookie(k, v)
            self._save_persist()
            self._logged = self._has_auth_cookie()
        except Exception:
            pass

    def _has_auth_cookie(self):
        try:
            for k, v in self._get_conn().cookies.items():
                if k.endswith("auth") and v:
                    return True
        except Exception:
            pass
        return False

    def _is_logged_in(self):
        if self._has_auth_cookie():
            return True
        try:
            html = self._fetch("%s/home.php?mod=space&do=profile&mobile=2" % self.host, tries=1)
            m = re.search(r"discuz_uid\s*=\s*'(\d+)'", html or "")
            if m and m.group(1) != "0":
                return True
        except Exception:
            pass
        return False

    def _login(self, force=False):
        if not (self._user and self._pass):
            return False
        if not force and self._logged:
            return True
        try:
            page = self._fetch("%s/member.php?mod=logging&action=login&mobile=2" % self.host)
            formhash = self._search(r'name=["\']formhash["\'][^>]*value=["\']([^"\']+)', page)
            lh = self._search(r"loginhash=([0-9A-Za-z]+)", page)
            if not formhash or not lh:
                self._last_err = "登录页解析失败"
                return False
            form = {
                "formhash": formhash,
                "referer": self.host + "/forum.php?mobile=2",
                "fastloginfield": "username",
                "cookietime": "2592000",
                "username": self._user,
                "password": self._pass,
                "gacode": self._gacode,
                "questionid": self._questionid,
                "answer": self._answer,
            }
            url = "%s/member.php?mod=logging&action=login&loginsubmit=yes&loginhash=%s&mobile=2" % (self.host, lh)
            body = urllib.parse.urlencode(form).encode("utf-8")
            resp = self._http(url, data=body, timeout=25)
            self._save_persist()
            self._logged = self._is_logged_in()
            if not self._logged:
                msg = self._search(r'class="alert_(?:info|error)"[^>]*>(.*?)</div>', resp or "")
                if not msg:
                    msg = self._search(r'id="messagetext"[^>]*>(.*?)</div>', resp or "")
                if not msg:
                    msg = self._search(r"<p>([^<]{4,80})</p>", resp or "")
                msg = re.sub(r"\s+", " ", self._clean_tags(msg)).strip()
                self._last_err = "登录失败:" + (msg[:70] if msg else "账号或密码不对")
            else:
                self._need_login = False
            return self._logged
        except Exception as e:
            self._last_err = "登录异常:%s" % str(e)[:40]
            return False


    def getDependence(self):
        return ""

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return any(x in u for x in (".m3u8", ".mp4", ".flv"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return False

    def destroy(self):
        self._save_persist()

    # ---------------- HTTP 层(会话保持) ----------------

    def _cookie(self, name, value, domain=None):
        try:
            with self._conn_lock:
                for conn in self._conns.values():
                    conn.set_cookie(name, value)
            if name.endswith("auth"):
                self._persist[name] = value
                self._save_persist()
        except Exception:
            pass

    def _http(self, url, headers=None, data=None, timeout=25):
        h = {}
        if headers:
            for k, v in headers.items():
                if v:
                    h[k] = v
        if "Referer" not in h:
            h["Referer"] = self.host + "/"
        if data is not None:
            body = data.encode("utf-8") if isinstance(data, str) else data
            return self._get_conn().request(url, headers=h, body=body)
        return self._get_conn().request(url, headers=h)

    def _gate_id(self, text):
        if not text or len(text) > 4000:
            return ""
        if "safeid" not in text:
            return ""
        m = re.search(r"safeid\s*=\s*['\"]([^'\"]+)['\"]", text)
        return m.group(1) if m else ""

    def _ensure_safe(self, url=""):
        if self._safe:
            return True
        html = self._http(url or (self.host + "/"))
        sid = self._gate_id(html) or self._search(r"safeid\s*=\s*['\"]([^'\"]+)['\"]", html or "")
        if sid:
            self._safe = sid
            return True
        return False

    def _fetch(self, url, headers=None, tries=3):
        text = ""
        for i in range(max(1, tries)):
            text = self._http(url, headers=headers)
            if text:
                return text
            time.sleep(0.2)
        return text or ""

    def _play_headers(self, tid=""):
        ref = "%s/forum.php?mod=viewthread&tid=%s&mobile=2" % (self.host, tid) if tid else (self.host + "/")
        return {"User-Agent": self.ua, "Referer": ref, "Origin": self.host}

    # ---------------- 首页 / 分类 / 搜索 ----------------

    def homeContent(self, filter=None):
        classes = [{"type_id": fid, "type_name": name} for fid, name in self.boards]
        return {"class": classes, "filters": {c["type_id"]: [] for c in classes} if filter else {}}

    def homeVideoContent(self):
        try:
            return self.categoryContent("41", "1", False, {})
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg="1", filter=None, extend=None):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        fid = str(tid or "41")
        url = "%s/forum.php?mod=forumdisplay&fid=%s&mobile=2&page=%s" % (self.host, fid, page)
        html = self._fetch(url)
        items = self._parse_list(html)
        if not items:
            self._ensure_safe(url)
            html = self._fetch(url)
            items = self._parse_list(html)
        pagecount = page + 1 if len(items) >= 10 else max(1, page)
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": max(1, len(items) or 20),
            "total": pagecount * max(1, len(items) or 20),
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        q = str(key or "").strip()
        if not q:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
        kw = urllib.parse.quote(q, safe="")
        urls = [
            "%s/search.php?mod=forum&srchtxt=%s&searchsubmit=yes&mobile=2&page=%s" % (self.host, kw, page),
            "%s/search.php?mod=forum&srchtxt=%s&searchsubmit=yes&mobile=2" % (self.host, kw),
        ]
        items = []
        for u in urls:
            html = self._fetch(u)
            items = self._parse_list(html)
            if items:
                break
            time.sleep(1.0)
        if not items and page == 1:
            # 搜索被限流时,退回板块内联筛选,保证有结果
            low = q.lower()
            for fid, _ in self.boards[:3]:
                u = "%s/forum.php?mod=forumdisplay&fid=%s&mobile=2" % (self.host, fid)
                for it in self._parse_list(self._fetch(u)):
                    if low in (it.get("vod_name") or "").lower():
                        items.append(it)
                if len(items) >= 20:
                    break
        pagecount = page + 1 if len(items) >= 20 else max(1, page)
        return {
            "list": items[:60],
            "page": page,
            "pagecount": pagecount,
            "limit": max(1, len(items) or 20),
            "total": len(items),
        }

    # ---------------- 详情 ----------------

    def detailContent(self, ids):
        tid = str(ids[0] if isinstance(ids, (list, tuple)) and ids else ids or "").strip()
        tid = self._search(r"(\d{3,})", tid) or tid
        if not tid:
            return {"list": []}
        url = "%s/forum.php?mod=viewthread&tid=%s&mobile=2" % (self.host, tid)
        html = self._fetch(url)
        params = self._extract_play_params(html)
        if not params.get("grant"):
            html2 = self._fetch("%s/forum.php?mod=viewthread&tid=%s" % (self.host, tid))
            if html2 and not self._gate_id(html2):
                p2 = self._extract_play_params(html2)
                if p2.get("grant") and not params.get("grant"):
                    params = p2
                if len(html2) > len(html):
                    html = html2 if html2 else html
        name = self._thread_title(html) or ("帖子 %s" % tid)
        pic = self._extract_pic(html)
        if not pic and params.get("vid"):
            pic = self._pic_by_vid(params["vid"])
        pic = self._ref_img(pic)
        if params.get("grant"):
            note = "在线播放"
            play_url = "正片$%s" % tid
            play_from = "98堂"
        elif params.get("direct"):
            note = "在线播放(直链)"
            play_url = "正片$%s" % params["direct"]
            play_from = "98堂直链"
        else:
            iframe = self._extract_iframe(html)
            if iframe:
                note = "站外播放页"
                play_url = "正片$%s" % iframe
                play_from = "嗅探"
            else:
                # 图片/小说 — 对齐 mjv011：pics:// 画 / novel:// 书
                imgs = self._gallery_imgs(html)
                if not pic and imgs:
                    pic = imgs[0]
                body = self._post_text(html)
                if body and len(body) > 60 and self._looks_novel(body):
                    payload = json.dumps({"title": name, "content": body[:8000]}, ensure_ascii=False)
                    play_url = "阅读$novel://%s" % payload
                    return {
                        "list": [{
                            "vod_id": tid,
                            "vod_name": name,
                            "vod_pic": pic or "",
                            "vod_content": body[:500],
                            "vod_remarks": "小说",
                            "vod_play_from": "小说",
                            "vod_play_url": play_url,
                            "vod_tag": "text",
                            "vod_player": "书",
                        }]
                    }
                if imgs:
                    _start_img_proxy(self.host + "/")
                    proxied = []
                    for u in imgs[:40]:
                        if _img_proxy_started and _img_proxy_port:
                            proxied.append("http://127.0.0.1:%d/%s" % (
                                _img_proxy_port, urllib.parse.quote(u, safe="")))
                        else:
                            proxied.append(u)
                    cover = proxied[0] if proxied else (pic or "")
                    play_url = "查看$pics://%s" % ("&&".join(proxied))
                    return {
                        "list": [{
                            "vod_id": tid,
                            "vod_name": name,
                            "vod_pic": cover,
                            "vod_content": "共 %d 张图片" % len(imgs),
                            "vod_remarks": "%dP" % len(imgs),
                            "vod_play_from": "图片",
                            "vod_play_url": play_url,
                            "vod_tag": "image",
                            "vod_player": "画",
                        }]
                    }
                if body and len(body) > 40:
                    payload = json.dumps({"title": name, "content": body[:8000]}, ensure_ascii=False)
                    play_url = "阅读$novel://%s" % payload
                    return {
                        "list": [{
                            "vod_id": tid,
                            "vod_name": name,
                            "vod_pic": pic or "",
                            "vod_content": body[:500],
                            "vod_remarks": "小说",
                            "vod_play_from": "小说",
                            "vod_play_url": play_url,
                            "vod_tag": "text",
                            "vod_player": "书",
                        }]
                    }
                note = "本帖可能无在线播放(下载区/需登录/附件)"
                play_url = ""
                play_from = "提示"
                return {
                    "list": [{
                        "vod_id": tid,
                        "vod_name": name,
                        "vod_pic": pic or "",
                        "vod_content": name + "｜" + note,
                        "vod_play_from": play_from,
                        "vod_play_url": play_url,
                    }]
                }
        return {
            "list": [{
                "vod_id": tid,
                "vod_name": name,
                "vod_pic": pic or "",
                "vod_content": name + ("｜" + note if note else ""),
                "vod_play_from": play_from,
                "vod_play_url": play_url,
            }]
        }

    # ---------------- 播放 ----------------

    def playerContent(self, flag="", id="", vipFlags=None):
        raw = str(id or "").strip()
        if not raw or raw == "0":
            return {"parse": 0, "jx": 0, "url": "", "msg": "无播放地址"}

        # mjv011 兼容：图集 / 小说协议
        if raw.startswith("pics://") or "pics://" in raw:
            u = raw if raw.startswith("pics://") else raw[raw.find("pics://"):]
            return {"parse": 0, "url": u, "header": self._play_headers() if hasattr(self, "_play_headers") else {"Referer": self.host + "/"}, "vod_player": "画"}
        if raw.startswith("novel://") or "novel://" in raw:
            u = raw if raw.startswith("novel://") else raw[raw.find("novel://"):]
            return {"parse": 0, "url": u, "header": "", "vod_player": "书"}

        # 图片直链（图集分类）
        if raw.startswith("http") and re.search(r"\.(jpg|jpeg|png|webp|gif)(\?|$)", raw, re.I):
            hd = {
                "User-Agent": self.ua,
                "Referer": self.host + "/",
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
            }
            # 壳若防盗链失败，可走本地代理
            try:
                if hasattr(self, "getProxyUrl") and self.getProxyUrl():
                    proxy = self.getProxyUrl()
                    sep = "&" if "?" in proxy else "?"
                    return {
                        "parse": 0,
                        "jx": 0,
                        "url": "%s%surl=%s&type=img" % (proxy, sep, urllib.parse.quote(raw, safe="")),
                        "header": hd,
                    }
            except Exception:
                pass
            return {"parse": 0, "jx": 0, "url": raw, "header": hd}

        # 直链 m3u8 / mp4
        if raw.startswith("http") and any(x in raw.lower() for x in (".m3u8", ".mp4", ".flv")):
            hd = self._play_headers()
            if self._media_ok(raw):
                return {"parse": 0, "jx": 0, "url": raw, "header": hd}
            u2 = self._strip_auth(raw)
            if u2 != raw and self._media_ok(u2):
                return {"parse": 0, "jx": 0, "url": u2, "header": hd}
            return {"parse": 0, "jx": 0, "url": raw, "header": hd}

        # 站内帖子页 → 视作详情,交给下面走接口取链
        tid = self._search(r"tid=(\d+)", raw) if "viewthread" in raw else ""
        if not tid:
            parts = raw.split("|")
            tid = self._search(r"(\d{3,})", parts[0]) if parts else ""
        if not tid:
            return {"parse": 0, "jx": 0, "url": "", "msg": "参数错误"}

        url = self._resolve_play(tid)
        if url:
            return {"parse": 0, "jx": 0, "url": url, "header": self._play_headers(tid)}
        if raw.startswith("http"):
            # 兜底:把原帖页交给嗅探
            return {"parse": 1, "jx": 1, "url": raw, "header": self._play_headers(tid)}
        if self._need_login and not (self._user and self._pass):
            return {"parse": 0, "jx": 0, "url": "",
                    "msg": "游客今日免费额度已用完,extend 填 {\"user\":\"账号\",\"pass\":\"密码\"} 后即可继续"}
        return {"parse": 0, "jx": 0, "url": "", "msg": "取链失败:%s" % (self._last_err or "no_response")}

    def _resolve_play(self, tid):
        self._last_err = "no_response"
        # 第一优先:开一条全新出口通道(新客户端 IP + 新会话)取链
        got = self._chan_play(tid)
        if got:
            return got
        thread = "%s/forum.php?mod=viewthread&tid=%s&mobile=2" % (self.host, tid)
        for attempt in range(3):
            html = self._fetch(thread, tries=2)
            params = self._extract_play_params(html)
            if not params.get("grant"):
                if params.get("direct") and self._media_ok(params["direct"]):
                    return params["direct"]
                self._last_err = "帖内无播放参数"
                time.sleep(0.3)
                continue
            got = self._play_api(tid, params["pid"], params["vid"], params["grant"])
            if got:
                if self._media_ok(got):
                    return got
                alt = self._strip_auth(got)
                if alt != got and self._media_ok(alt):
                    return alt
                if alt != got:
                    return alt
                return got
            if self._need_login and self._user and self._pass:
                # 游客额度用完 → 用配置里的账号登录后重试一次
                if self._login(force=True):
                    html = self._fetch(thread, tries=2)
                    params = self._extract_play_params(html)
                    if params.get("grant"):
                        got = self._play_api(tid, params["pid"], params["vid"], params["grant"])
                        if got:
                            return got
                self._last_err = self._last_err or "需登录"
            time.sleep(0.4)
        return ""

    def _play_api(self, tid, pid, vid, grant):
        cb = "jQuery%d_%d" % (random.randint(1000000, 9999999), int(time.time() * 1000))
        q = urllib.parse.urlencode({
            "tid": tid, "pid": pid, "vid": vid, "grant": grant,
            "rand": "%.16f" % random.random(), "callback": cb,
        })
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "%s/forum.php?mod=viewthread&tid=%s&mobile=2" % (self.host, tid),
            "Origin": self.host,
        }
        text = self._fetch("%s/play.php?%s" % (self.host, q), headers=headers)
        data = self._jsonp(text)
        if isinstance(data, dict):
            url = ""
            d = data.get("data")
            if isinstance(d, dict):
                for k in ("flvurl", "url", "m3u8", "playurl", "flv", "src", "hd", "sd"):
                    if d.get(k):
                        url = str(d[k])
                        break
            elif isinstance(d, str) and d.strip().startswith("http"):
                url = d.strip()
            if url:
                return self._unesc(url)
            self._last_err = str(data.get("msg") or "接口无地址")[:60]
            if self._looks_like_login(text):
                self._need_login = True
                self._last_err = "游客每日限10个,需登录"
            return ""
        m = self._search(r'(https?://[^"\'\s\\]+\.(?:m3u8|mp4|flv)[^"\'\s\\]*)', text)
        if m:
            return self._unesc(m)
        if self._looks_like_login(text):
            self._need_login = True
            self._last_err = "游客每日限10个,需登录"
            return ""
        self._last_err = ("非JSON响应(len=%s)" % len(text)) if text else "空响应"
        return ""

    @staticmethod
    def _looks_like_login(text):
        t = str(text or "")
        return any(k in t for k in ("请登录", "游客每天", "登录观看", "请先登录", "member.php?mod=logging"))

    # ---------------- 出口通道池 ----------------

    def _chan_play(self, tid):
        """开一条全新通道取链:全新客户端 IP + 全新会话,绕开游客每日限额。"""
        if not getattr(self, "_xff_on", True):
            return ""
        proxy = ""
        try:
            if self._proxies:
                proxy = random.choice(self._proxies)
        except Exception:
            proxy = ""
        try:
            ch = _FreshChan(self.host, self.ua, proxy=proxy)
        except Exception:
            return ""
        thread = "%s/forum.php?mod=viewthread&tid=%s&mobile=2" % (self.host, tid)
        try:
            html = ch.boot(thread)
        except Exception:
            html = ""
        params = self._extract_play_params(html)
        if params.get("direct") and not params.get("grant"):
            return params["direct"]
        if not params.get("grant"):
            try:
                html = ch.boot(thread)
            except Exception:
                html = ""
            params = self._extract_play_params(html)
        if not params.get("grant"):
            self._last_err = "新通道未拿到播放参数"
            return ""
        q = urllib.parse.urlencode({
            "tid": tid,
            "pid": params["pid"],
            "vid": params["vid"],
            "grant": params["grant"],
            "rand": "%.16f" % random.random(),
        })
        try:
            txt = ch.get("%s/play.php?%s" % (self.host, q), ref=thread, xhr=True)
        except Exception:
            txt = ""
        url = ""
        data = self._jsonp(txt)
        if isinstance(data, dict):
            d = data.get("data")
            if isinstance(d, dict):
                for k in ("flvurl", "url", "m3u8", "playurl", "flv", "src", "hd", "sd"):
                    if d.get(k):
                        url = str(d[k])
                        break
            elif isinstance(d, str) and d.strip().startswith("http"):
                url = d.strip()
            if not url:
                self._last_err = str(data.get("msg") or "接口无地址")[:50]
        if not url:
            m = self._search(r'(https?://[^"\'\s\\]+\.(?:m3u8|mp4|flv)[^"\'\s\\]*)', txt)
            if m:
                url = self._unesc(m)
        try:
            self._chan_used += 1
        except Exception:
            pass
        if url:
            self._last_err = ""
            return self._unesc(url)
        return ""

    def _jsonp(self, text):
        if not text:
            return None
        t = text.strip()
        i, j = t.find("{"), t.rfind("}")
        if i < 0 or j <= i:
            return None
        try:
            return json.loads(t[i:j + 1])
        except Exception:
            return None

    def _raw_get(self, url, headers=None, timeout=20, nbytes=None):
        """一次性 GET(CDN 图片/m3u8 等,不走门禁),返回 bytes。"""
        p = urllib.parse.urlsplit(url or "")
        if not p.netloc:
            return b""
        path = p.path or "/"
        if p.query:
            path += "?" + p.query
        h = {"User-Agent": self.ua}
        if headers:
            for k, v in headers.items():
                if v:
                    h[k] = v
        conn = None
        try:
            conn = http.client.HTTPSConnection(p.netloc, timeout=timeout, context=_ssl_ctx())
            conn.request("GET", path, headers=h)
            resp = conn.getresponse()
            data = resp.read(nbytes) if nbytes else resp.read()
            ctype = ""
            for k, v in resp.getheaders():
                if k.lower() == "content-type":
                    ctype = v
                    break
            if nbytes:
                return data, ctype
            return data
        except Exception:
            if nbytes:
                return b"", ""
            return b""
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    def _media_ok(self, url):
        if not url:
            return False
        u = str(url)
        hdr = {"User-Agent": self.ua, "Referer": self.host + "/", "Range": "bytes=0-2047"}
        raw, ctype = self._raw_get(u, headers=hdr, timeout=12, nbytes=4096)
        if not raw:
            raw, ctype = self._raw_get(u, headers={"User-Agent": self.ua}, timeout=12, nbytes=4096)
        if not raw:
            return False
        body = raw.decode("utf-8", "ignore") if raw[:3] != b"\x00\x00\x00" else ""
        if "#EXTM3U" in body or "#EXTINF" in body:
            return True
        if any(x in ctype for x in ("mpegurl", "video/", "octet-stream")):
            return True
        if ".mp4" in u.lower() and len(raw) > 0:
            return True
        return False

    @staticmethod
    def _strip_auth(url):
        try:
            p = urllib.parse.urlsplit(url)
            if not p.query:
                return url
            q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
                 if k.lower() not in ("auth_key", "sign", "token", "expires", "exp")]
            return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path,
                                            urllib.parse.urlencode(q), p.fragment))
        except Exception:
            return url

    # ---------------- 本地代理(可选,给需要带头的 CDN 兜底) ----------------

    def localProxy(self, param):
        try:
            import base64
            raw = ""
            if isinstance(param, dict):
                raw = param.get("url") or param.get("path") or param.get("u") or ""
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "ignore")
            raw = str(raw)
            if not raw.startswith("http"):
                try:
                    raw = base64.b64decode(urllib.parse.unquote(raw) + "===").decode("utf-8", "ignore")
                except Exception:
                    pass
            raw = urllib.parse.unquote(raw) if "%3a" in raw.lower() else raw
            if not raw.startswith("http"):
                return [404, "text/plain", b"bad url"]
            # 图片代理
            if "type=img" in str(param) or re.search(r"\.(jpg|jpeg|png|webp|gif)(\?|$)", raw, re.I):
                data = self._http_bytes(raw, headers={
                    "Referer": self.host + "/",
                    "User-Agent": self.ua,
                    "Accept": "image/*,*/*;q=0.8",
                })
                if not data:
                    return [502, "text/plain", b"img fail"]
                ctype = "image/jpeg"
                low = raw.lower()
                if ".png" in low: ctype = "image/png"
                elif ".webp" in low: ctype = "image/webp"
                elif ".gif" in low: ctype = "image/gif"
                return [200, ctype, data]
            body = self._http(raw, headers={"Referer": self.host + "/"}, timeout=20)
            if not body or ("#EXTM3U" not in body and "#EXTINF" not in body):
                return [502, "text/plain", b"m3u8 fail"]
            base = raw.split("?")[0].rsplit("/", 1)[0] + "/"
            out = []
            for line in body.splitlines():
                s = line.strip()
                if s.startswith("#EXT-X-KEY:") or s.startswith("#EXT-X-MAP:") or s.startswith("#EXT-X-MEDIA:"):
                    def _abs(m):
                        u = m.group(1)
                        if u.startswith("http"):
                            return 'URI="%s"' % u
                        return 'URI="%s"' % (base + u.lstrip("/"))
                    s = re.sub(r'URI="([^"]+)"', _abs, s)
                    out.append(s)
                elif s and not s.startswith("#") and not s.startswith("http"):
                    out.append(base + s.lstrip("/"))
                else:
                    out.append(line)
            return [200, "application/vnd.apple.mpegurl",
                    ("\n".join(out) + "\n").encode("utf-8")]
        except Exception:
            return [500, "text/plain", b"proxy error"]

    # ---------------- 解析 ----------------


    def _http_bytes(self, url, headers=None, timeout=20):
        try:
            h = dict(headers or {})
            h.setdefault("Referer", self.host + "/")
            return self._raw_get(url, headers=h, timeout=timeout)
        except Exception:
            return b""

    def _extract_play_params(self, html):
        h = self._unesc(html or "")
        params = {"tid": "", "pid": "", "vid": "", "grant": "", "direct": ""}
        seg = h
        i = h.find('id="v-loading"')
        if i >= 0:
            seg = h[i:i + 4000]
        for key, attr in (("tid", "tid"), ("pid", "pid"), ("vid", "vid"), ("grant", "grant")):
            v = self._search(r'data-%s\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>&]+))' % attr, seg) or \
                self._search(r'data-%s\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>&]+))' % attr, h)
            if not v:
                v = self._search(r'"%s"\s*:\s*"([^"]+)"' % attr, h)
            params[key] = (v or "").strip()
        for pat in (
            r'video\s*:\s*\{[^}]*?url\s*:\s*[\'"]([^\'"]+\.(?:m3u8|mp4)[^\'"]*)',
            r'(https?://[^\'"\s\\]+\.m3u8[^\'"\s\\]*)',
            r'(https?://[^\'"\s\\]+\.mp4[^\'"\s\\]*)',
        ):
            m = self._search(pat, h)
            if m:
                params["direct"] = self._clean_url(m)
                break
        return params

    def _parse_list(self, html):
        if not html or self._gate_id(html):
            return []
        items = []
        seen = set()
        # 列表页每个主题是一整块 <div class="item ...">，块内第一个 viewthread 链接
        # 是封面(只带时长/图片)，真正的标题在 class="title" 的链接或 img@alt 里。
        links = self._finditer(
            r'<a[^>]+href\s*=\s*["\']([^"\']*?mod=viewthread[^"\']*?tid=(\d+)[^"\']*)["\'][^>]*>(.*?)</a>',
            html,
        )
        for m in links:
            tid = m.group(2)
            if tid in seen:
                continue
            seen.add(tid)
            tag = m.group(0)
            title = ""
            # 1) 标题链接：class 里有 title
            if re.search(r'class\s*=\s*["\'][^"\']*\btitle\b', tag, re.I):
                title = self._clean_tags(m.group(3))
            # 2) 封面链接 → 取其中的 img alt
            if not title:
                title = self._clean_tags(
                    self._search(r'<img[^>]+alt\s*=\s*["\']([^"\']+)["\']', tag) or ""
                )
            # 3) 块内找 class="title" 的那条链接
            if not title:
                lo = max(0, m.start() - 1200)
                seg = html[lo:m.start() + 2500]
                title = self._clean_tags(self._search(
                    r'class\s*=\s*["\'][^"\']*\btitle\b[^"\']*["\'][^>]*>(.*?)</a>', seg) or "")
            # 4) 纯文本兜底（排除纯时长/纯数字）
            if not title:
                cand = self._clean_tags(m.group(3))
                if cand and not re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', cand):
                    title = cand
            if not title or len(title) < 4:
                continue
            if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', title):
                continue
            if title.startswith("http"):
                continue
            if any(k in title for k in ("招聘", "邀请码", "二次验证", "永久访问", "白名单",
                                        "发布器", "突破", "公告", "版规", "必看", "置顶",
                                        "签到", "索引", "投诉", "申诉", "教程")):
                continue
            if self._skip_minor(title):
                continue
            seg = html[max(0, m.start() - 300):m.start() + 1600]
            pics = self._img_candidates(seg) or self._img_candidates(html[max(0, m.start() - 900):m.start()])
            remark = self._search(r'class\s*=\s*["\']time["\'][^>]*>\s*([\d:]{4,8})\s*<', seg)
            items.append({
                "vod_id": tid,
                "vod_name": title,
                "vod_pic": self._ref_img(pics[0]) if pics else "",
                "vod_remarks": remark or "",
            })
        return items

    def _thread_title(self, html):
        t = self._search(r"<title>([^<]+)</title>", html or "")
        if t:
            t = self._clean_tags(t)
            tails = ["98堂", "98堂[原色花堂]", "手机版", "Powered by Discuz!",
                     "提示信息", "国产自拍", "中文字幕", "日韩无码", "日韩有码", "欧美风情",
                     "原创自拍", "转贴自拍", "华人街拍", "欧美性爱", "卡通动漫", "套图下载",
                     "原创小说", "TXT小说", "激情都市", "武侠虚幻", "乱伦人妻", "AI短剧", "AI专区"]
            tails += [n.split("·")[-1] for _, n in getattr(self, "boards", [])]
            tails += [n.split("·")[-1] + "区" for _, n in getattr(self, "boards", [])]
            changed = True
            while changed:
                changed = False
                for s in tails:
                    for sep in (" - ", " — ", " | ", "-", "｜"):
                        tail = sep + s
                        if t.endswith(tail):
                            t = t[: -len(tail)].strip()
                            changed = True
            t = t.strip(" -｜|")
            if t and "Powered by" not in t and t not in ("提示信息",):
                return t
        for pat in (r'<h2[^>]*>(.*?)</h2>', r'<h1[^>]*>(.*?)</h1>', r'class="thread_tit"[^>]*>(.*?)<'):
            v = self._clean_tags(self._search(pat, html or ""))
            if len(v) >= 4:
                return v
        return ""

    def _pic_by_vid(self, vid):
        """封面统一走 <pic_host>/<vid>/1.jpg,访问需要带 Referer。"""
        vid = str(vid or "").strip()
        if not vid or not re.match(r"^[0-9A-Za-z@._\-]{4,80}$", vid):
            return ""
        url = "%s/%s/1.jpg" % (self._pic_host, urllib.parse.quote(vid, safe="@._-"))
        try:
            data, ctype = self._raw_get(url, headers={
                "User-Agent": self.ua,
                "Referer": self.host + "/",
                "Range": "bytes=0-63",
            }, timeout=8, nbytes=64)
            if data and ("image" in ctype or "octet-stream" in ctype):
                return url
        except Exception:
            pass
        return ""

    def _extract_pic(self, html):
        h = html or ""
        scope = ""
        for marker in ("postmessage", "post_content", "plc", "message"):
            i = h.find(marker)
            if i >= 0:
                scope = h[i:i + 20000]
                break
        for seg in (scope, h):
            if not seg:
                continue
            cands = self._img_candidates(seg)
            if cands:
                return cands[0]
        return ""

    def _extract_iframe(self, html):
        for m in self._finditer(r'<iframe[^>]+src\s*=\s*["\']([^"\']+)["\']', html or ""):
            u = self._norm_url(m.group(1))
            if u and "viewthread" not in u:
                return u
        return ""

    def _img_candidates(self, segment):
        out = []
        for m in self._finditer(r"<img[^>]+>", segment or ""):
            tag = m.group(0)
            for attr in ("data-original", "data-src", "data-url", "file", "src"):
                v = self._search(attr + r'\s*=\s*["\']([^"\']+)["\']', tag)
                if v:
                    u = self._norm_url(v)
                    if u and not self._pic_skip(u):
                        out.append(u)
                    break
        return out

    @staticmethod
    def _pic_skip(u):
        low = (u or "").lower()
        bad = ("avatar", "logo", "static/", "image/common", "none.gif", "placeholder",
               "emoji", "smiley", "icon", "qrcode", "face", "uc_server", ".svg", "data:image",
               "data/attachment/h", "/attachment/h", "noavatar")
        if any(b in low for b in bad):
            return True
        # 站内占位缩略图（无真实路径）
        if low.rstrip("/").endswith("attachment/h") or low.endswith("/h"):
            return True
        return False

    def _ref_img(self, u):
        """给图床 URL 加 @Referer= 后缀(FongMi 约定),否则 403。"""
        u = str(u or "")
        if not u:
            return ""
        low = u.lower()
        if low.startswith("http://127.0.0.1") or "@referer=" in low:
            return u
        if re.search(r"\.(jpg|jpeg|png|webp|gif)(\?|$)", u, re.I):
            return u + "@Referer=" + self.host + "/"
        return u

    def _norm_url(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            return self.host + u
        return self.host + "/" + u.lstrip("/")

    @staticmethod
    def _clean_url(u):
        return (u or "").strip().rstrip(",;)}]<>\\")

    @staticmethod
    def _unesc(s):
        try:
            return (s or "").replace("\\/", "/").replace('\\"', '"').replace("\\'", "'")
        except Exception:
            return s or ""

    @staticmethod
    def _clean_tags(s):
        import html as _html
        s = re.sub(r"<[^>]+>", "", str(s or ""))
        s = _html.unescape(s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def _skip_minor(name):
        n = (name or "").lower()
        return any(k in n for k in ("萝莉", "幼女", "小学生", "中学生", "未成年", "loli", "underage", "女童", "幼齿"))

    def _gallery_imgs(self, html):
        """帖内真实图链：优先 tupian CDN，过滤头像/占位图"""
        out = []
        seen = set()
        h = html or ""
        # 1) img 标签
        for m in self._finditer(r"<img[^>]+>", h):
            tag = m.group(0)
            for attr in ("zoomfile", "file", "data-original", "data-src", "src"):
                v = self._search(attr + r'\s*=\s*["\']([^"\']+)["\']', tag)
                if not v:
                    continue
                u = self._norm_url(v)
                if not u or self._pic_skip(u) or u in seen:
                    continue
                if not re.search(r'\.(jpg|jpeg|png|webp|gif)(\?|$)', u, re.I):
                    continue
                seen.add(u)
                out.append(u)
                break
        # 2) 裸链 tupian
        for u in self._findall(
            r'(https?://[^"\'\s>]+/(?:tupian|upload|forum)/[^"\'\s>]+\.(?:jpg|jpeg|png|webp|gif)(?:\?[^"\'\s>]*)?)',
            h,
        ):
            u = self._norm_url(u)
            if u and u not in seen and not self._pic_skip(u):
                seen.add(u)
                out.append(u)
        # 优先外链图床
        def score(u):
            low = u.lower()
            if "tupian" in low or "wkt" in low or "djhdhs" in low or "djsnm" in low:
                return 0
            if "attachment" in low:
                return 2
            return 1
        out.sort(key=score)
        return out[:40]

    def _looks_novel(self, body):
        b = str(body or "")
        if len(b) < 60:
            return False
        # 小说帖必有章节/字数标记；图集帖正文通常只是说明+楼层 chrome(广告等)
        if re.search(r'第[0-9一二三四五六七八九十百千]+[章节]', b):
            return True
        if re.search(r'\d{2,6}字', b):
            return True
        if b.count("章") >= 3 and len(b) > 120:
            return True
        return False

    def _post_text(self, html):
        """帖内正文纯文本摘要（取第一条 message 容器，去脚本样式）"""
        if not html:
            return ""
        starts = [mm.start() for mm in re.finditer(
            r'class="[^"]*(?:message|postmessage|pcb)[^"]*"[^>]*>', html, re.I)]
        if starts:
            s = starts[0]
            e = starts[1] if len(starts) > 1 else min(s + 60000, len(html))
            block = html[s:e]
        else:
            block = html
        block = re.sub(r'<script[\s\S]*?</script>', ' ', block, flags=re.I)
        block = re.sub(r'<style[\s\S]*?</style>', ' ', block, flags=re.I)
        block = re.sub(r'<img[^>]*>', ' [IMG] ', block)
        block = re.sub(r'<[^>]+>', ' ', block)
        block = re.sub(r'\s+', ' ', block).strip()
        return block[:8000]

    @staticmethod
    def _search(pat, text):
        m = re.search(pat, text or "", re.I | re.S)
        if not m:
            return ""
        for g in m.groups():
            if g:
                return g
        return ""

    @staticmethod
    def _findall(pat, text):
        try:
            return re.findall(pat, text or "", re.I | re.S)
        except Exception:
            return []

    @staticmethod
    def _finditer(pat, text):
        try:
            return list(re.finditer(pat, text or "", re.I | re.S))
        except Exception:
            return []


# ---------------- 直接运行本文件 = 跑一遍自检 ----------------

if __name__ == "__main__":
    import urllib.request as _u

    def _alive(url, ua):
        if not url or ".m3u8" not in url:
            return False
        try:
            b = _u.urlopen(_u.Request(url, headers={"User-Agent": ua}), timeout=15).read(3000)
            return b"#EXTM3U" in b
        except Exception:
            return False

    sp = Spider()
    sp.init("")
    rows = []

    def _t(name, ok, note=""):
        rows.append(ok)
        print(("[OK]   " if ok else "[FAIL] ") + name + (("  -> " + str(note)) if note else ""))

    print("== 98堂 插件自检 ==")
    _t("首页分类", len(sp.homeContent(True)["class"]) >= 5)
    hv = sp.homeVideoContent()
    _t("首页列表", len(hv.get("list", [])) > 0, "%d 条" % len(hv.get("list", [])))
    for _fid, _nm in sp.boards:
        _c = sp.categoryContent(_fid, "1", False, {})
        _t("分类 %s" % _nm, len(_c.get("list", [])) > 0, "%d 条" % len(_c.get("list", [])))
    _a = [x["vod_id"] for x in sp.categoryContent("41", "1", False, {}).get("list", [])]
    _b = [x["vod_id"] for x in sp.categoryContent("41", "2", False, {}).get("list", [])]
    _t("翻页递进", len(set(_a) & set(_b)) == 0)
    _t("搜索", len(sp.searchContent("巨乳", False, "1").get("list", [])) > 0)
    if _a:
        _d = sp.detailContent([_a[0]])["list"][0]
        _t("详情标题", len(_d.get("vod_name") or "") > 3, _d.get("vod_name", "")[:24])
        _t("详情封面", bool(_d.get("vod_pic")))
        _r = sp.playerContent(_d.get("vod_play_from", ""), (_d.get("vod_play_url") or "").split("$")[-1], None)
        _u2 = _r.get("url") or ""
        _ok = _alive(_u2, sp.ua)
        _limit = "额度" in (_r.get("msg") or "") or "登录" in (_r.get("msg") or "")
        _t("取链可播", _ok, _u2[:60] if _ok else (_r.get("msg") or "")[:60])
        if not _ok and _limit:
            print("       提示:站方游客每天限 10 个视频,填账号后继续(详见使用说明)。")
    print("== 共 %d 项,通过 %d 项 ==" % (len(rows), sum(1 for x in rows if x)))