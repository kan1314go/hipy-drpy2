# -*- coding: utf-8 -*-

import base64
import json
import re
import uuid
from urllib.parse import quote, unquote, urljoin

from Crypto.Cipher import AES

from base.spider import Spider as BaseSpider

UA = "Mozilla/5.0 (Linux; Android 14; 22127RK46C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

_CATS = [
    {"type_id": "ai_duanju", "type_name": "AI短剧"},
    {"type_id": "zrdj", "type_name": "真人短剧"},
    {"type_id": "ai_huanlian", "type_name": "AI换脸"},
    {"type_id": "ai_mogai", "type_name": "AI魔改"},
    {"type_id": "ai_manju", "type_name": "AI漫剧"},
]
_FILTER_SORT = [
    {"key": "sort", "name": "排序", "value": [{"n": "最新", "v": "latest"}]},
]


class Spider(BaseSpider):
    def getName(self):
        return "汽水短剧"

    def getDependence(self):
        return []

    def init(self, extend=""):
        self.host = "https://noyboiwy.com"
        self.headers = {"User-Agent": UA}
        self._ck = {}        # cookie 管理 (确认+游客会话)
        self._mkey = None    # 图片解密 key (public_media_cipher_key)
        self._cover_cache = {}  # drama_id -> cover URL (跨请求复用)
        self._cats = _CATS
        self._filters = {c["type_id"]: _FILTER_SORT for c in _CATS}

    # ---------- 网络与状态 ----------
    def _cook(self):
        return "; ".join("%s=%s" % (k, v) for k, v in self._ck.items())

    def _save_ck(self, r):
        try:
            cj = getattr(r, "cookies", None)
            if cj is not None:
                for c in cj:
                    if c.value:
                        self._ck[c.name] = c.value
                    else:
                        self._ck.pop(c.name, None)
                return
        except Exception:
            pass
        try:
            sc = r.headers.get("Set-Cookie", "")
            for chunk in re.split(r",(?=[A-Za-z_][A-Za-z0-9_]*=)", sc):
                m = re.match(r"\s*([^=;]+)=([^;]*)", chunk)
                if m:
                    k, v = m.group(1), m.group(2)
                    if v and "Max-Age=0" not in chunk:
                        self._ck[k] = v
                    else:
                        self._ck.pop(k, None)
        except Exception:
            pass

    def _req(self, url, headers=None, retry=2):
        h = dict(self.headers)
        if headers:
            h.update(headers)
        if self._ck:
            h["Cookie"] = self._cook()
        last = None
        for i in range(retry + 1):
            try:
                r = self.fetch(url, headers=h, timeout=15)
                self._save_ck(r)
                return r
            except Exception as e:
                last = e
                if i < retry:
                    continue
        raise last if last else Exception("fetch failed: %s" % url)

    def _post(self, url, data, headers=None):
        h = dict(self.headers)
        if headers:
            h.update(headers)
        if self._ck:
            h["Cookie"] = self._cook()
        r = self.post(url, data=data, headers=h, timeout=15)
        self._save_ck(r)
        return r

    def _ensure_account(self):
        """播放前置: 年龄确认 + 游客账号 (幂等)"""
        if self._ck.get("qishui_session"):
            return True
        if not self._ck.get("qishui_age"):
            try:
                r = self._req(self.host + "/api/age")
                j = json.loads(r.text)
                if not j.get("accepted"):
                    self._post(self.host + "/api/age",
                               json.dumps({"adult": True}),
                               {"Content-Type": "application/json", "Origin": self.host})
                    try:
                        self._req(self.host + "/api/age")  # 复查确认
                    except Exception:
                        pass
            except Exception as e:
                self.log("年龄确认失败 %s" % e)
        if not self._ck.get("qishui_session"):
            did = str(uuid.uuid4())
            body = json.dumps({
                "sid": str(uuid.uuid4()),
                "device": "Android",
                "device_id": did,
                "device_brand": "Xiaomi",
                "device_model": "22127RK46C",
                "system_name": "Android",
                "system_version": "14",
                "device_fingerprint": did,
                "fp_version": "1",
            })
            hdr = {
                "Content-Type": "application/json",
                "X-Qishui-Session-Scope": "web",
                "Origin": self.host,
            }
            try:
                # 第一段: prepared + 下发 qishui_bootstrap cookie
                self._post(self.host + "/api/account/bootstrap", body, hdr)
                # 第二段: 带 qishui_bootstrap 换发 qishui_session (signedIn:true)
                if self._ck.get("qishui_bootstrap"):
                    self._post(self.host + "/api/account/bootstrap", body, hdr)
            except Exception as e:
                self.log("游客账号创建失败 %s" % e)
        return bool(self._ck.get("qishui_session"))

    # ---------- 图片 (.bnc AES-ECB 解密) ----------
    def _media_key(self):
        if self._mkey:
            return self._mkey
        try:
            r = self._req(self.host + "/api/media-config")
            k = json.loads(r.text).get("public_media_cipher_key", "")
            if k and len(k) == 16:
                self._mkey = k.encode()
        except Exception as e:
            self.log("media-config 获取失败 %s" % e)
        return self._mkey

    def _dec_bnc(self, data):
        key = self._media_key()
        if not key:
            return None
        try:
            n = len(data) - len(data) % 16
            return AES.new(key, AES.MODE_ECB).decrypt(data[:n])
        except Exception as e:
            self.log("bnc 解密失败 %s" % e)
            return None

    def _mime_of(self, data):
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if data[:4] == b"\x89PNG":
            return "image/png"
        if data[:4] == b"GIF8":
            return "image/gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return ""

    def _fetch_img(self, url):
        try:
            r = self._req(url)
            data = r.content
        except Exception as e:
            self.log("图片下载失败 %s" % e)
            return None, ""
        if url.endswith(".bnc"):
            data = self._dec_bnc(data)
            if data is None:
                return None, ""
        mime = self._mime_of(data)
        if not mime:
            self.log("图片格式未知 %s %s" % (url, data[:16].hex() if data else ""))
            return None, ""
        return data, mime

    def _pic_proxy(self, url):
        """图片 URL -> 本机 localProxy 中转地址（localProxy 内下载密文并 AES 解密返回明文）
        对齐 91porna 交付版：getProxyUrl() 可能带 ? 参数，须补 & 分隔符"""
        if not url:
            return ""
        b64 = base64.b64encode(url.encode("utf-8")).decode()
        base = self.getProxyUrl()
        if "?" in base and not base.endswith(("&", "?")):
            base += "&"
        elif "?" not in base:
            base += "?"
        return base + "url=" + b64 + "&type=img"

    # ---------- 列表解析 ----------
    def _parse_list(self, html):
        covers = {}
        for m in re.finditer(r"https?://[^\"'\s]+/drama/cover/([0-9a-f-]{36})/[^\"'\s]+\.bnc", html):
            covers.setdefault(m.group(1), m.group(0))
        items, seen = [], set()
        for m in re.finditer(r"<article[^>]*>([\s\S]*?)</article>", html):
            tag, body = m.group(0), m.group(1)
            tm = re.search(r'data-sdk-name="([^"]+)"', tag)
            if not tm:
                continue
            dm = re.search(r'class="poster-main"[^>]*href="/drama/([0-9a-f-]{36})', body)
            if not dm:
                continue
            vid = dm.group(1)
            if vid in seen:
                continue
            title = tm.group(1).strip()
            if not title:
                continue
            st = re.search(r'poster-state[^>]*>([^<]+)<', body)
            remark = st.group(1).strip() if st else ""
            items.append({
                "vod_id": "/drama/" + vid,
                "vod_name": title,
                "vod_pic": self._pic_proxy(covers.get(vid, "")),
                "vod_remarks": remark,
                "vod_play_url": "",
                "vod_year": "",
                "vod_area": "",
                "vod_director": "",
                "vod_actor": "",
                "vod_content": "",
            })
            seen.add(vid)
        return items

    def _fill_covers(self, items, limit=8):
        """列表页 SSR 不给卡片封面 (占位 svg 懒加载), 用 /api/content/<id> 顺序补全前 N 张, 缓存复用。
        不用多线程: 沙盒 fetch 调度在子线程不稳定, 顺序 + 缓存足够。"""
        need = []
        for it in items:
            if it.get("vod_pic"):
                continue
            m = re.search(r"/drama/([0-9a-f-]{36})", it["vod_id"])
            if m:
                need.append(m.group(1))
        need = need[:limit]
        if not need:
            return items
        got = {}
        for uid in need:
            if uid in self._cover_cache:
                got[uid] = self._cover_cache[uid]
                continue
            try:
                r = self._req(self.host + "/api/content/" + uid)
                cv = json.loads(r.text).get("drama", {}).get("cover", "")
                if cv and not cv.startswith("http"):
                    cv = urljoin(self.host, cv)
            except Exception as e:
                self.log("封面补全失败 %s" % e)
                cv = ""
            self._cover_cache[uid] = cv
            got[uid] = cv
        for it in items:
            if it.get("vod_pic"):
                continue
            m = re.search(r"/drama/([0-9a-f-]{36})", it["vod_id"])
            if m and got.get(m.group(1)):
                it["vod_pic"] = self._pic_proxy(got[m.group(1)])
        return items

    # ---------- 首页/分类/搜索 ----------
    def homeContent(self, filter):
        return {"class": self._cats, "filters": self._filters}

    def homeVideoContent(self):
        try:
            html = self._req(self.host + "/").text
        except Exception as e:
            self.log("首页请求失败 %s" % e)
            return {"list": []}
        items = self._parse_list(html)
        return {"list": self._fill_covers(items)}

    def _maxpage(self, html):
        nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", html)]
        return max(nums) if nums else 1

    def categoryContent(self, tid, pg, filter, extend):
        url = self.host + "/category/" + str(tid)
        params = []
        if extend and extend.get("sort"):
            params.append("sort=" + quote(extend["sort"]))
        if str(pg) != "1":
            params.append("page=" + str(pg))
        if params:
            url += "?" + "&".join(params)
        try:
            html = self._req(url).text
        except Exception as e:
            self.log("分类请求失败 %s" % e)
            return {"list": [], "page": int(pg or "1"), "pagecount": 1, "limit": 30, "total": 0}
        if "暂时没有找到这个故事" in html:
            return {"list": [], "page": int(pg or "1"), "pagecount": 1, "limit": 30, "total": 0}
        items = self._fill_covers(self._parse_list(html))
        pc = self._maxpage(html)
        return {"list": items, "page": int(pg or "1"), "pagecount": pc, "limit": 30, "total": pc * 30}

    def searchContent(self, key, quick, pg="1"):
        # 站方搜索认 &page= 翻页 (实测 p2 与 p1 完全不同), 原版没传 pg 导致永远只有第一页 (2026-11-02 修)
        url = self.host + "/search?q=" + quote(key) + "&sid=" + str(uuid.uuid4())
        if str(pg) != "1":
            url += "&page=" + str(pg)
        try:
            html = self._req(url).text
        except Exception as e:
            self.log("搜索请求失败 %s" % e)
            return {"list": [], "page": int(pg or "1"), "pagecount": 1}
        if "暂时没有找到这个故事" in html:
            return {"list": [], "page": int(pg or "1"), "pagecount": 1}
        items = self._fill_covers(self._parse_list(html))
        pc = self._maxpage(html)
        # 页面自带页码可能只标到当前页 (p1 只标 1, 壳就不翻页了): 满页 (12 条) 时乐观 +1
        optimistic = int(pg or "1") + (1 if len(items) >= 12 else 0)
        if optimistic > pc:
            pc = optimistic
        return {"list": items, "page": int(pg or "1"), "pagecount": pc}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str(ids[0])
        if vid.startswith("http"):
            url = vid
        elif vid.startswith("/drama/"):
            url = self.host + vid
        else:
            url = urljoin(self.host, vid)
        uidm = re.search(r"/drama/([0-9a-f-]{36})", url)
        # 主路: /api/content/<uuid> — 站点改版后详情页已无 SSR 剧集网格 (episode-grid 消失),
        # 剧集/标题/简介/封面全在此接口里; 原 HTML 解析只作兜底 (2026-11-02 修)
        if uidm:
            try:
                r = self._req(self.host + "/api/content/" + uidm.group(1))
                d = json.loads(r.text).get("drama", {})
            except Exception as e:
                self.log("api/content 详情失败 %s" % e)
                d = {}
            if d:
                cv = d.get("cover", "") or ""
                pic = ""
                if cv:
                    if not cv.startswith("http"):
                        cv = urljoin(self.host, cv)
                    pic = self._pic_proxy(cv)
                    self._cover_cache[uidm.group(1)] = cv
                eps = []
                for e in d.get("episodes", []):
                    try:
                        num = int(e.get("number"))
                    except Exception:
                        continue
                    name = (e.get("title") or "").strip() or "第%s集" % num
                    eps.append((num, name))
                eps.sort(key=lambda x: x[0])
                parts = ["%s$%s" % (name, urljoin(self.host, "/drama/%s/%s" % (uidm.group(1), num)))
                         for num, name in eps]
                cnt = d.get("episodeCount") or len(eps)
                vod = {
                    "vod_id": "/drama/" + uidm.group(1),
                    "vod_name": d.get("title", "") or "未知",
                    "vod_pic": pic,
                    "type_name": "短剧",
                    "vod_year": "",
                    "vod_area": "",
                    "vod_director": "",
                    "vod_actor": "",
                    "vod_remarks": "共%s集" % cnt if cnt else "",
                    "vod_content": d.get("synopsis", "") or "",
                    "vod_play_from": "汽水短剧",
                    "vod_play_url": "#".join(parts),
                }
                return {"list": [vod]}
        # 兜底: 旧 HTML 解析 (接口不可用时才走)
        try:
            html = self._req(url).text
        except Exception as e:
            self.log("详情请求失败 %s" % e)
            return {"list": []}
        title, desc, remark = "", "", ""
        jm = re.search(r'<script type="application/ld\+json">([\s\S]*?)</script>', html)
        if jm:
            try:
                j = json.loads(jm.group(1))
                g = j.get("@graph") or []
                for n in g:
                    if n.get("@type") == "TVSeries":
                        title = n.get("name", "")
                        desc = n.get("description", "")
                        rem = n.get("numberOfEpisodes")
                        if rem:
                            remark = "共%s集" % rem
                        break
            except Exception:
                pass
        if not title:
            hm = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html)
            if hm:
                title = re.sub(r"<[^>]+>", "", hm.group(1)).strip()
        if not remark:
            rm = re.search(r"更新至\s*(\d+)\s*集", html)
            if rm:
                remark = "更新至%s集" % rm.group(1)
        cm = re.search(r'\\?"cover\\?"\s*:\s*\\?"((?:https?://)?[^\\"]+\.bnc)\\?"', html)
        pic = ""
        if cm:
            cv = cm.group(1)
            if not cv.startswith("http"):
                cv = urljoin(self.host, cv)
            pic = self._pic_proxy(cv)
            uidm = re.search(r"/drama/([0-9a-f-]{36})", url)
            if uidm:
                self._cover_cache[uidm.group(1)] = cv
        if not pic:
            vid_m = re.search(r"/drama/([0-9a-f-]{36})", url)
            if vid_m:
                cm2 = re.search(r"https?://[^\"'\s]+/drama/cover/" + re.escape(vid_m.group(1)) + r"/[^\"'\s]+\.bnc", html)
                if cm2:
                    pic = self._pic_proxy(cm2.group(0))
        eg = re.search(r'class="episode-grid"([\s\S]*?)</div>', html)
        eps = []
        if eg:
            eps = re.findall(r'href="(/drama/[0-9a-f-]+/\d+)"', eg.group(1))
        play_url = ""
        if eps:
            parts = []
            for i, u in enumerate(eps, 1):
                parts.append("第%s集$%s" % (i, urljoin(self.host, u)))
            play_url = "#".join(parts)
        uid_out = ""
        um = re.search(r"/drama/([0-9a-f-]{36})", url)
        if um:
            uid_out = "/drama/" + um.group(1)
        vod = {
            "vod_id": uid_out or vid,
            "vod_name": title or "未知",
            "vod_pic": pic,
            "type_name": "短剧",
            "vod_year": "",
            "vod_area": "",
            "vod_director": "",
            "vod_actor": "",
            "vod_remarks": remark,
            "vod_content": desc,
            "vod_play_from": "汽水短剧",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        m = re.search(r"/drama/([0-9a-f-]{36})/(\d+)", id)
        if not m:
            return {"parse": 1, "playUrl": "", "url": id, "header": {}}
        drama_id, ep = m.group(1), m.group(2)
        url = self.host + "/api/playback/%s/%s" % (drama_id, ep)
        j = None
        for attempt in range(3):
            try:
                r = self._req(url)
            except Exception as e:
                self.log("playback 请求失败 %s" % e)
                break
            code = r.status_code if hasattr(r, "status_code") else 200
            if code == 200:
                try:
                    j = json.loads(r.text)
                    break
                except Exception as e:
                    self.log("playback json 解析失败 %s" % e)
                    break
            elif code in (401, 403):
                # 未登录: 重建游客会话 (bootstrap 两段式换发 qishui_session) 后重试
                self.log("playback %s 未登录, 重建会话" % code)
                self._ensure_account()
                continue
            elif code == 428:
                # 年龄确认门禁
                self.log("playback 428 需年龄确认")
                self._ensure_account()
                continue
            else:
                self.log("playback 异常状态 %s" % code)
                break
        if j is None:
            return {"parse": 1, "playUrl": "", "url": id, "header": {}}
        u = j.get("url", "")
        if not u:
            self.log("playback 无 url: %s" % str(j)[:200])
            return {"parse": 1, "playUrl": "", "url": id, "header": {}}
        if u.startswith("/"):
            u = self.host + u
        elif not u.startswith("http"):
            u = urljoin(self.host, u)
        # 防盗链实测(debug12): 主 m3u8 必须带 qishui_session Cookie, 否则 428;
        # rvid.jsdets.cn 的 key/分片 UA-only 与带 Cookie 均 200, 可统一透传 Cookie。
        h = {"User-Agent": UA}
        if self._ck:
            h["Cookie"] = self._cook()
        return {"parse": 0, "playUrl": "", "url": u, "header": h}

    # ---------- localProxy (图片解密中转) ----------
    def localProxy(self, param):
        """图片中转: type=img -> 下载 AES 密文并解密返回明文图片 (对齐 91porna 交付版)"""
        url = ""
        tp = ""
        if isinstance(param, dict):
            url = param.get("url", "") or ""
            tp = param.get("type", "") or ""
        else:
            s = str(param)
            tp = "img" if "type=img" in s else ""
            m = re.search(r"(?:^|[?&])url=([^&]*)", s)
            if m:
                url = m.group(1)
        if tp != "img" or not url:
            return [404, "text/plain", "", {}]
        try:
            real = base64.b64decode(url).decode("utf-8", "ignore") if not url.startswith("http") else url
        except Exception:
            real = url
        if not real.startswith("http"):
            return [404, "text/plain", "", {}]
        try:
            data, mime = self._fetch_img(real)
            if data is None or not mime:
                return [200, "text/plain", "", {}]
            return [200, mime, data, {"Cache-Control": "no-store"}]
        except Exception as e:
            self.log("localProxy 失败 %s" % e)
            return [200, "text/plain", "", {}]

    # ---------- 模板兼容 ----------
    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return ""

    def destroy(self):
        return ""
