# -*- coding: utf-8 -*-
import json
import re
import threading
import time
from urllib.parse import quote, urljoin

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider(object):
        def fetch(self, url, headers=None, timeout=15):
            pass

        def post(self, url, data=None, headers=None, timeout=15):
            pass

        def log(self, msg):
            pass

        def getProxyUrl(self, local=False):
            return "http://127.0.0.1:9978/proxy?"

UA = "Mozilla/5.0 (Linux; Android 14; 22127RK46C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

DEFAULT_SITES = ["https://pornavhd.com"]

EMBED_HOST_RE = r"(?:playrecord\.biz|recordplay\.biz|video\.playerrecord\.cfd|playerrecord\.cfd|wishfast\.top)"

AD_HOST_RE = r"(?:whitetrafsa|nettrck|magsrv|orbsrv|greentrafsa|tscprts|cloudflareinsights|yandex)"

_CATS = [
    {"type_id": "all", "type_name": "最新"},
    {"type_id": "hot", "type_name": "最热"},
    {"type_id": "viewed", "type_name": "最多观看"},
    {"type_id": "long", "type_name": "最长"},
    {"type_id": "cat:onlyfans", "type_name": "Onlyfans"},
    {"type_id": "cat:twitter", "type_name": "Twitter"},
    {"type_id": "cat:fc2", "type_name": "FC2"},
    {"type_id": "cat:myfans", "type_name": "MyFans"},
]

_FILTERS = {
    "all": [{"key": "sort", "name": "排序", "value": [
        {"n": "最新", "v": "latest"}, {"n": "最热", "v": "popular"},
        {"n": "最多观看", "v": "most-viewed"}, {"n": "最长", "v": "longest"},
        {"n": "随机", "v": "random"}]}],
}

_FILTER_MAP = {"all": "latest", "hot": "popular", "viewed": "most-viewed", "long": "longest"}


class Spider(BaseSpider):
    def getName(self):
        return "Pornavhd"

    def getDependence(self):
        return []

    def init(self, extend=""):
        cfg = {}
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else dict(extend)
            except Exception:
                cfg = {}
        sites = cfg.get("sites") or DEFAULT_SITES
        self.host = (cfg.get("site") or sites[0]).rstrip("/")
        self.sites = [s.rstrip("/") for s in sites]
        self.proxy = (cfg.get("proxy") or "").rstrip("/")
        self.headers = {"User-Agent": cfg.get("ua") or UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
        self.cookie = cfg.get("cookie") or ""
        if self.cookie:
            self.headers["Cookie"] = self.cookie
        self.play_headers = {"User-Agent": cfg.get("ua") or UA, "Referer": self.host + "/"}
        self.brandActor = cfg.get("brand_actor") or "蝴蝶影视"
        self.brandDirector = cfg.get("brand_director") or "🦋 TG群: @tvshare23"
        self._inflight = {}
        self.prefer = str(cfg.get("prefer") or "auto").lower()
        self.proxy_m3u8 = bool(cfg.get("proxy_m3u8", True))
        self.cache = {}
        self.timeout = int(cfg.get("timeout") or 15)

    def _cfg_proxy(self, url):
        if not url:
            return url
        if self.proxy and url.startswith("http") and not url.startswith(self.proxy):
            return self.proxy + "/" + url
        return url

    def _req(self, url, headers=None, retry=2, timeout=None):
        last = None
        for i in range(retry + 1):
            try:
                r = self.fetch(url, headers=headers or self.headers, timeout=timeout or self.timeout)
                code = getattr(r, "status_code", None)
                if code is None and isinstance(r, dict):
                    code = r.get("code")
                text = getattr(r, "text", None)
                if text is None and isinstance(r, dict):
                    text = r.get("content") or r.get("text")
                if code is not None and int(code) >= 400:
                    body = text or ""
                    if int(code) in (403, 503) and ("Just a moment" in body or "challenge-platform" in body):
                        raise RuntimeError("Cloudflare 挑战拦截，需要 cookie 字段填 cf_clearance 或换出口")
                    raise RuntimeError("HTTP %s" % code)
                return text or ""
            except Exception as e:
                last = e
        raise last if last else RuntimeError("fetch failed: %s" % url)

    def _cached(self, key, ttl, fn):
        now = time.time()
        hit = self.cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        val = fn()
        self.cache[key] = (now, val)
        return val

    def _parse_list(self, html):
        out = []
        blocks = re.findall(r"<article[\s\S]*?</article>", html)
        for b in blocks:
            m = re.search(r'<a[^>]+href="([^"]+)"[^>]*title="([^"]*)"', b)
            if not m:
                continue
            href, title = m.group(1), m.group(2).strip()
            if not re.search(r"/\d{4}/\d{2}/\d{2}/", href):
                continue
            pic = re.search(r'<img[^>]+src="([^"]+)"', b)
            dur = re.search(r'<span class="duration">([^<]*)</span>', b)
            pid = re.search(r'data-post-id="(\d+)"', b)
            vod = {
                "vod_id": pid.group(1) if pid else href,
                "vod_name": title or (pid.group(1) if pid else ""),
                "vod_pic": pic.group(1) if pic else "",
                "vod_remarks": (dur.group(1).strip() if dur else ""),
            }
            out.append(vod)
        return out

    def _pagecount(self, html):
        nums = [int(x) for x in re.findall(r"/page/(\d+)/", html)]
        return max(nums) if nums else 1

    def homeContent(self, filter):
        return {"class": _CATS, "filters": _FILTERS}

    def homeVideoContent(self):
        try:
            html = self._req(self.host + "/")
        except Exception as e:
            self.log("首页失败 %s" % e)
            return {"list": []}
        return {"list": self._parse_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        tid = str(tid or "all")
        if tid.startswith("cat:"):
            slug = tid.split(":", 1)[1]
            url = self.host + "/category/" + slug + "/"
            if pg > 1:
                url += "page/%d/" % pg
        else:
            flt = _FILTER_MAP.get(tid, "latest")
            if extend and extend.get("sort"):
                flt = extend["sort"]
            if pg > 1:
                url = self.host + "/page/%d/?filter=%s" % (pg, flt)
            else:
                url = self.host + "/?filter=" + flt
        try:
            html = self._req(url)
        except Exception as e:
            self.log("分类失败 %s %s" % (tid, e))
            return {"list": [], "page": pg, "pagecount": 1, "limit": 46, "total": 0}
        items = self._parse_list(html)
        pc = self._pagecount(html)
        return {"list": items, "page": pg, "pagecount": pc, "limit": 46, "total": pc * 46}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        kw = quote(key or "")
        if pg > 1:
            url = self.host + "/page/%d/?s=%s" % (pg, kw)
        else:
            url = self.host + "/?s=" + kw
        try:
            html = self._req(url)
        except Exception as e:
            self.log("搜索失败 %s" % e)
            return {"list": [], "page": pg, "pagecount": 1}
        return {"list": self._parse_list(html), "page": pg, "pagecount": self._pagecount(html)}

    def _pick_embed(self, html):
        cands = []
        for m in re.finditer(r"<iframe[^>]*>", html, re.I):
            tag = m.group(0)
            src = re.search(r'src="([^"]+)"', tag, re.I)
            if not src:
                continue
            u = src.group(1).strip()
            if not u.startswith("http"):
                continue
            if re.search(AD_HOST_RE, u):
                continue
            cands.append(u)
        for u in cands:
            if re.search(EMBED_HOST_RE, u):
                return u
        return cands[0] if cands else ""

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        vid = str(vid)
        url = vid if vid.startswith("http") else (self.host + "/?p=" + vid if vid.isdigit() else vid)
        try:
            html = self._req(url)
        except Exception as e:
            self.log("详情失败 %s" % e)
            return {"list": [self._diag("Pornavhd 详情请求失败", str(e), url)]}
        if "/?p=" in url:
            real = re.search(r'<link rel="canonical" href="([^"]+)"', html)
            if real:
                url = real.group(1)
                try:
                    html = self._req(url)
                except Exception:
                    pass
        h1 = re.search(r"<h1[^>]*>([\s\S]{0,200}?)</h1>", html)
        title = re.sub(r"\s+", " ", h1.group(1)).strip() if h1 else ""
        og = re.search(r'property="og:image" content="([^"]+)"', html)
        dur = re.search(r'<span class="duration">([^<]*)</span>', html)
        embed = self._pick_embed(html)
        if not title:
            ogt = re.search(r'property="og:title" content="([^"]+)"', html)
            title = ogt.group(1) if ogt else vid
        play_url = "正片$" + (embed if embed else url)
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": og.group(1) if og else "",
            "type_name": "Pornavhd",
            "vod_year": "",
            "vod_area": "",
            "vod_director": self.brandDirector,
            "vod_actor": self.brandActor,
            "vod_remarks": self._format_remarks(dur.group(1).strip() if dur else "", embed),
            "vod_content": title,
            "vod_play_from": "Pornavhd",
            "vod_play_url": play_url,
        }
        if embed:
            self._prefetch(embed)
        return {"list": [vod]}

    def _prefetch(self, embed):
        try:
            def run():
                self._prepare_cached(embed)

            t = threading.Thread(target=run)
            t.daemon = True
            t.start()
        except Exception:
            pass

    def _format_remarks(self, dur, embed):
        tag = "直链" if embed else "待解析"
        return ("%s · %s" % (dur, tag)) if dur else tag

    def _diag(self, name, reason, url=""):
        return {
            "vod_id": "diag",
            "vod_name": name,
            "vod_pic": "",
            "type_name": "诊断",
            "vod_year": "",
            "vod_area": "",
            "vod_director": self.brandDirector,
            "vod_actor": self.brandActor,
            "vod_remarks": "诊断卡",
            "vod_content": "原因: %s\n地址: %s" % (reason, url),
            "vod_play_from": "Pornavhd",
            "vod_play_url": "诊断$" + (url or self.host),
        }

    def _b36(self, n):
        d = "0123456789abcdefghijklmnopqrstuvwxyz"
        if n == 0:
            return "0"
        s = ""
        while n:
            s = d[n % 36] + s
            n //= 36
        return s

    def _unpack(self, html):
        i = html.find("eval(function(p,a,c,k,e,d)")
        if i < 0:
            return ""
        seg = html[i:]
        m = re.search(r"\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", seg, re.S)
        if not m:
            return ""
        payload = m.group(1).replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        count = int(m.group(3))
        table = m.group(4).split("|")
        mapping = {}
        for c in range(min(count, len(table)) - 1, -1, -1):
            if table[c]:
                mapping[self._b36(c)] = table[c]
        fast = re.sub(r"\b[0-9a-z]+\b", lambda mm: mapping.get(mm.group(0), mm.group(0)), payload)
        if "hls" in fast and ("links" in fast or "stream" in fast):
            return fast
        out = payload
        for c in range(count - 1, -1, -1):
            if c < len(table) and table[c]:
                out = re.sub(r"\b" + re.escape(self._b36(c)) + r"\b", table[c].replace("\\", "\\\\"), out)
        return out

    def _links(self, html):
        js = self._unpack(html)
        if not js:
            return {}
        m = re.search(r"var\s+links\s*=\s*(\{.*?\});", js, re.S)
        if not m:
            m = re.search(r'"links"\s*:\s*(\{.*?\})', js, re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception as e:
            self.log("links 解析失败 %s" % e)
            return {}

    def _variants(self, txt, base):
        out = []
        lines = [l.strip() for l in txt.split("\n")]
        for i, line in enumerate(lines):
            if not line.startswith("#EXT-X-STREAM-INF"):
                continue
            hv = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            height = int(hv.group(2)) if hv else 0
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith("#"):
                    out.append((height, urljoin(base, nxt)))
                    break
        return out

    def _first_seg(self, txt):
        for line in txt.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                return line
        return ""

    def _fast_url(self, master, height):
        if "?" not in master:
            return ""
        base, query = master.split("?", 1)
        d, name = base.rsplit("/", 1)
        if not name.startswith("master."):
            return ""
        idx = {"480": 1, "720": 2, "1080": 3}.get(str(height), 1)
        return d + "/index-f%d-v1-a1.m3u8?" % idx + query

    def _valid_variant(self, vurl, heads):
        try:
            vtxt = self._req(vurl, headers=heads, retry=0, timeout=10)
        except Exception as e:
            return "", str(e)
        if "#EXTM3U" not in vtxt:
            return "", "非m3u8"
        seg = self._first_seg(vtxt)
        if not seg:
            return "", "空子列表"
        if "tiktokcdn.com" in seg:
            return "", "广告占位"
        return vtxt, ""

    def _abs_master(self, mtxt, master):
        # 把 master 里相对地址全部转绝对，代理出去后播放器才能解析
        out = []
        for line in (mtxt or "").split("\n"):
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(urljoin(master, s))
                continue
            line = re.sub(r'URI="([^"]+)"',
                          lambda m: 'URI="%s"' % urljoin(master, m.group(1)), line)
            out.append(line)
        return "\n".join(out)

    def _app_api_play(self, embed):
        # 播放器前端已换成 Next.js 壳 + /app/v1/play/{code} 取流，
        # embed 页不再含 eval 打包的 var links，直接走官方 API。
        # 注意：tiktokcdn.com 在这里就是内容 CDN（分片实测 200 可播），
        # 不是广告占位，不得按广告过滤。
        m = re.search(r"/e/([A-Za-z0-9]+)", embed or "")
        if not m:
            return {}, "embed 无 file_code"
        code = m.group(1)
        parts = (embed or "").split("/")
        base = parts[0] + "//" + parts[2]
        heads = {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}
        api = (base + "/app/v1/play/" + code
               + "?embed=1&ref=" + quote(self.host + "/", safe=""))
        try:
            txt = self._req(api, headers=heads, retry=1, timeout=12)
        except Exception as e:
            return {}, "api 请求失败 %s" % e
        try:
            data = json.loads(txt)
        except Exception:
            return {}, "api 非 JSON"
        master = data.get("hls") or ""
        if not master.startswith("http"):
            return {}, "api 无 hls 字段"
        try:
            mtxt = self._req(master, headers={
                "User-Agent": self.headers["User-Agent"], "Referer": embed},
                retry=1, timeout=12)
        except Exception as e:
            return {}, "master 拉取失败 %s" % e
        if "#EXTM3U" not in mtxt:
            return {}, "master 非 m3u8"
        vs = self._variants(mtxt, master)
        want = self.prefer if self.prefer in ("480", "720", "1080") else None
        if vs:
            vs.sort(key=lambda x: x[0])
            target = vs[-1]
            for h, vu in vs:
                if want and str(h) == want:
                    target = (h, vu)
                    break
        else:
            target = (0, master)
        try:
            vtxt = self._req(target[1], headers=heads, retry=1, timeout=12)
        except Exception as e:
            return {}, "子列表拉取失败 %s" % e
        if not self._first_seg(vtxt):
            return {}, "子列表无分片"
        return {"master": master, "chosen": master,
                "chosen_height": target[0],
                "chosen_text": self._abs_master(mtxt, master),
                "key": "api"}, ""

    def _prepare(self, embed):
        heads = {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}
        info, why = self._app_api_play(embed)
        if info:
            return info, ""
        self.log("api 取流失败，回落 embed 页解析: %s" % why)
        html = self._req(embed, headers=heads, timeout=12)
        links = self._links(html)
        if not links:
            return {}, "embed 页未取到 links"
        base = embed.split("/")[0] + "//" + embed.split("/")[2]
        want = self.prefer if self.prefer in ("480", "720", "1080") else "480"
        why = []
        for key in ("hls2", "hls3", "hls4"):
            u = links.get(key) or ""
            if not u:
                continue
            if u.startswith("//"):
                u = "https:" + u
            elif u.startswith("/"):
                u = base + u
            if not u.startswith("http"):
                continue
            if key == "hls2":
                for h in (want, "480", "720", "1080"):
                    fast = self._fast_url(u, h)
                    if not fast:
                        break
                    vtxt, err = self._valid_variant(fast, heads)
                    if vtxt:
                        return {"master": u, "chosen": fast, "chosen_height": int(h), "chosen_text": vtxt, "key": key}, ""
                    why.append("fast%s:%s" % (h, err))
            try:
                txt = self._req(u, headers=heads, retry=1, timeout=12)
            except Exception as e:
                why.append("%s:%s" % (key, e))
                continue
            if "#EXTM3U" not in txt:
                why.append("%s:非m3u8" % key)
                continue
            vs = self._variants(txt, u)
            if not vs:
                why.append("%s:无清晰度" % key)
                continue
            vs.sort(key=lambda x: x[0])
            target = vs[0]
            for h, vu in vs:
                if str(h) == want:
                    target = (h, vu)
                    break
            vtxt, err = self._valid_variant(target[1], heads)
            if not vtxt:
                why.append("%s:%s" % (key, err))
                continue
            return {"master": u, "chosen": target[1], "chosen_height": target[0], "chosen_text": vtxt, "key": key}, ""
        return {}, "全部线路不可用 " + " | ".join(why)

    def _prepare_cached(self, embed, wait=15):
        key = "prep:" + embed
        hit = self.cache.get(key)
        if hit:
            ttl = 1800 if hit[1] else 120
            if time.time() - hit[0] < ttl:
                return hit[1], ("" if hit[1] else "上次解析失败，冷却中")
        ev = self._inflight.get(embed)
        if ev is not None:
            ev.wait(wait)
            hit = self.cache.get(key)
            if hit:
                return hit[1], ("" if hit[1] else "并发解析失败")
        ev = threading.Event()
        self._inflight[embed] = ev
        info, why = {}, ""
        try:
            info, why = self._prepare(embed)
        except Exception as e:
            why = str(e)
        finally:
            self.cache[key] = (time.time(), info)
            ev.set()
            self._inflight.pop(embed, None)
        return info, why

    def _proxy_m3u8(self, info, text):
        try:
            import hashlib
            key = hashlib.md5(text.encode("utf-8")).hexdigest()[:16]
            self.cache["m3u8:" + key] = (time.time(), text)
            url = self.getProxyUrl() or ""
            if not url.startswith("http"):
                return info.get("chosen") or ""
            sep = "&" if "?" in url else "?"
            return url + sep + "do=py&type=m3u8&key=" + key
        except Exception as e:
            self.log("生成代理地址失败 %s" % e)
            return info.get("chosen") or ""

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "")
        if raw.startswith("诊断$"):
            return {"parse": 1, "playUrl": "", "url": raw.split("$", 1)[1], "header": {}}
        target = raw.split("$")[-1]
        embed = target if re.search(EMBED_HOST_RE, target) else ""
        if not embed:
            try:
                html = self._req(target, headers=self.headers)
            except Exception as e:
                return {"parse": 1, "playUrl": "", "url": target, "header": {}, "msg": "详情页失败 %s" % e}
            embed = self._pick_embed(html)
        if not embed:
            return {"parse": 1, "playUrl": "", "url": target, "header": {}, "msg": "详情页无播放器 iframe"}
        info, why = self._prepare_cached(embed)
        heads = {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}
        if not info:
            self.log("解析失败，回落 embed: %s" % why)
            return {"parse": 1, "playUrl": "", "url": embed, "header": heads, "msg": why}
        if self.proxy_m3u8:
            url = self._proxy_m3u8(info, info.get("chosen_text") or "")
        else:
            url = info.get("chosen") or info.get("master")
        return {"parse": 0, "playUrl": "", "url": url, "header": heads, "msg": "line=%s h=%s" % (info.get("key"), info.get("chosen_height"))}

    def localProxy(self, param):
        p = param or {}
        if isinstance(p, str):
            p = {}
        if p.get("type") == "m3u8":
            hit = self.cache.get("m3u8:" + str(p.get("key") or ""))
            if hit:
                return [200, "application/vnd.apple.mpegurl", hit[1], {"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"}]
            return [404, "text/plain", "expired", {}]
        return [404, "text/plain", "", {}]

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return ""

    def destroy(self):
        return ""


if __name__ == "__main__":
    import time as _t

    class _Resp(object):
        def __init__(self, r):
            self.status_code = r.status_code
            self.text = r.text
            self.content = r.content
            self.headers = r.headers

    try:
        import requests
    except ImportError:
        requests = None

    _sess = requests.Session() if requests else None
    _sess.headers.update({"User-Agent": UA}) if _sess else None

    def _fetch(url, headers=None, timeout=15, **kw):
        if _sess is None:
            raise RuntimeError("需要 requests 才能脱离客户端自检")
        r = _sess.get(url, headers=headers or {}, timeout=timeout or 15)
        return _Resp(r)

    spider = Spider()
    spider.init("")
    spider.fetch = _fetch
    spider.log = lambda m: print("   [log]", m)

    print("=== 1. 分类 ===")
    home = spider.homeContent(True)
    print("分类数:", len(home.get("class", [])))
    print("筛选分类数:", len(home.get("filters") or {}))
    print("分类名:", ", ".join(c["type_name"] for c in home["class"]))

    print("=== 2. 首页 ===")
    t0 = _t.time()
    hv = spider.homeVideoContent()
    lst = hv.get("list") or []
    print("首页条数:", len(lst), "耗时 %.2fs" % (_t.time() - t0))
    if lst:
        print("首条:", lst[0]["vod_id"], lst[0]["vod_name"], lst[0]["vod_remarks"])

    print("=== 3. 分类页 ===")
    cat = spider.categoryContent("cat:onlyfans", "1", False, {})
    print("onlyfans 条数:", len(cat.get("list") or []), "总页:", cat.get("pagecount"))

    print("=== 4. 搜索 ===")
    t0 = _t.time()
    sr = spider.searchContent("kuzu", False, "1")
    print("搜索条数:", len(sr.get("list") or []), "耗时 %.2fs" % (_t.time() - t0))

    print("=== 5. 详情与取流 ===")
    seed = (sr.get("list") or []) + (cat.get("list") or []) + (lst or [])
    if not seed:
        print("无可用条目")
    else:
        v = seed[0]
        t0 = _t.time()
        det = spider.detailContent([v["vod_id"]])
        vod = (det.get("list") or [{}])[0]
        print("片名:", vod.get("vod_name"), "耗时 %.2fs" % (_t.time() - t0))
        print("线路:", vod.get("vod_play_from"), "备注:", vod.get("vod_remarks"))
        pid = (vod.get("vod_play_url") or "").split("$")[-1]
        print("prefer:", spider.prefer, "| proxy_m3u8:", spider.proxy_m3u8)
        t0 = _t.time()
        pr = spider.playerContent(vod.get("vod_play_from"), pid, [])
        dt_cold = _t.time() - t0
        t0 = _t.time()
        spider.playerContent(vod.get("vod_play_from"), pid, [])
        dt_hot = _t.time() - t0
        print("取流 parse=%s 冷 %.2fs / 热 %.3fs | %s" % (pr.get("parse"), dt_cold, dt_hot, pr.get("msg")))
        url = pr.get("url") or ""
        print("URL:", url[:120])
        if pr.get("parse") == 0:
            m3u8 = ""
            if spider.proxy_m3u8 and "key=" in url:
                lp = spider.localProxy({"type": "m3u8", "key": url.split("key=")[-1]})
                m3u8 = lp[2] or ""
                print("localProxy: %s %s 分片数=%d" % (lp[0], lp[1], m3u8.count("#EXTINF")))
            else:
                m3u8 = spider.fetch(url, headers=pr.get("header")).text or ""
                print("直链 m3u8 分片数=%d" % m3u8.count("#EXTINF"))
            seg = [l for l in m3u8.split("\n") if l.strip() and not l.startswith("#")]
            if seg:
                hh = dict(pr.get("header") or {})
                hh["Range"] = "bytes=0-262143"
                body = spider.fetch(seg[0], headers=hh, timeout=15).content or b""
                print("首片前256KB=%d bytes 同步字节=%s" % (len(body), hex(body[0]) if body else "无"))
