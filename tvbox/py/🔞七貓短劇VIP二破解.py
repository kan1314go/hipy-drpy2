# coding=utf-8
# !/usr/bin/python
"""
FongMi / TVBox T3 (type=3) 爬虫源
站点：七猫短剧  https://7maoduanju.com   （标签：🔞七貓短劇VIP二破解）
类型：JSON API 短剧站（移植自 Zaka Engine ZakaQmdjAmns.java, 1000 行）

逆向要点（实测 2026-10-10，API 全部 HTTP 200 可用）：
- API 基址：https://7maoduanju.com/api/toc/v1  （HOST 同域；支持 init 传 host 覆盖）
- 媒体域：https://7cat-media.bedfpk.cn ；封面域另有 7cat-pic.bedfpk.cn
- 统一头：UA(Chrome131 Win) + Accept=application/json,text/plain,*/* + Referer=https://7maoduanju.com/
- 分类（静态硬编码，homeContent 不发额外网络，仅 lines() 拉 /categories 动态线路）：
    rank 🔥热门榜(/ranks/hot) / new 🆕最新上线(/browse sort=latest)
    all  📺全部短剧(/browse)  / wish ✨魔改愿望榜(/ranks/wish)
    line|{id} 动态线路(/browse&line={id})  / topic|{id} 专题(/topics)
  filters：all/new/rank 及各 line| 带 sort（最热 hot / 最新 latest）。
- 列表卡片字段：id/title/coverUrl/episodeCount/freeEpisodeCount/coinPricePerEpisode/isVipBadge/heat/tags
- 详情 /dramas/{id}：episodes[] 每集优先 seoContentUrl；否则由 mediaKey + indexNo 组
    https://7cat-media.bedfpk.cn/7cat/{key}/hls/ep{NN}/ep{NN}.m3u8（NN 补零两位）
  mediaKey 由 /7cat/([0-9a-zA-Z]{8,40})/hls/ 或 .../cover 抽取。
- 搜索 /search?q=词&limit=50，仅第 1 页返回。
- 播放直链 parse:0，带 UA + Referer=https://7maoduanju.com/ 实测可取（#EXTM3U）。
最后验证：2026-10-10
"""
import sys
import re
import json
import time
from urllib.parse import quote

sys.path.append('..')
try:
    from base.spider import Spider
except Exception:
    class Spider(object):
        def init(self, extend=""):
            pass


class Spider(Spider):

    # ---- 站点信息（换站只改这两行）----
    HOST = "https://7maoduanju.com"
    LABEL = "🔞七貓短劇VIP二破解"

    API_PATH = "/api/toc/v1"
    MEDIA = "https://7cat-media.bedfpk.cn"
    PAGE = 30
    TTL_LINES = 21600  # 6 小时（秒）

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

    T_RANK = "rank"
    T_NEW = "new"
    T_ALL = "all"
    T_WISH = "wish"
    T_LINE = "line|"
    T_TOPIC = "topic|"

    P_MEDIA_HLS = re.compile(r"/7cat/([0-9a-zA-Z]{8,40})/hls/")
    P_MEDIA_COVER = re.compile(r"/7cat/([0-9a-zA-Z]{8,40})/cover")

    def init(self, extend=""):
        self.extHost = ""
        self._lines = None
        self._lines_at = 0
        try:
            if extend and len(extend) > 4:
                obj = json.loads(extend)
                host = (obj.get("host") or "").strip() if isinstance(obj, dict) else ""
                if host and len(host) > 8:
                    if not host.startswith("http"):
                        host = "https://" + host
                    if host.endswith("/"):
                        host = host[:-1]
                    self.extHost = host
        except Exception:
            pass

    def getName(self):
        return self.LABEL

    def isVideoFormat(self, url):
        url = url or ""
        return ".m3u8" in url or ".mp4" in url

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---- 工具 ----
    def _base(self):
        return self.extHost if (self.extHost and len(self.extHost) > 8) else self.HOST

    def _hdr(self):
        return {
            "User-Agent": self.UA,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://7maoduanju.com/",
        }

    def _api(self, path):
        """对 base 与 canonical API 双 URL、各重试 2 次，返回文本或 None。"""
        if not path.startswith("/"):
            path = "/" + path
        url_base = self._base() + self.API_PATH + path
        url_canon = self.HOST + self.API_PATH + path
        urls = [url_base, url_canon]
        for i in range(2):
            for _ in range(2):
                try:
                    rsp = self.fetch(urls[i], headers=self._hdr(), timeout=20)
                    txt = rsp.text if rsp is not None else None
                    if txt is None:
                        continue
                    txt = txt.strip()
                    if len(txt) <= 1:
                        continue
                    return txt
                except Exception:
                    continue
        return None

    def _obj(self, txt):
        try:
            v = json.loads(txt)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}

    def _arr(self, txt):
        try:
            v = json.loads(txt)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for k in ("list", "items", "data", "dramas", "results"):
                    if isinstance(v.get(k), list):
                        return v[k]
            return []
        except Exception:
            return []

    @staticmethod
    def _enc(s):
        try:
            return quote(s, safe="")
        except Exception:
            return s

    # ---- 卡片映射 ----
    def _vod(self, j):
        out = {}
        try:
            out["vod_id"] = j.get("dramaId") or j.get("id") or ""
            out["vod_name"] = j.get("title", "") or ""
            cover = j.get("coverUrl", "") or ""
            if cover:
                out["vod_pic"] = cover
            n = int(j.get("episodeCount", 0) or 0)
            free = int(j.get("freeEpisodeCount", 9999) or 9999)
            coin = int(j.get("coinPricePerEpisode", 0) or 0)
            vip = bool(j.get("isVipBadge", False))
            if coin <= 0 and free >= 9999 and not vip:
                remarks = ("共%d集" % n) if n > 0 else ""
            else:
                remarks = "共%d集·解锁全片" % n
            out["vod_remarks"] = remarks
            tags = j.get("tags")
            tn = ""
            if isinstance(tags, list) and tags:
                arr = [str(t) for t in tags if t]
                tn = " · ".join(arr)
            if not tn:
                tn = "短剧"
            out["type_name"] = tn
        except Exception:
            pass
        return out

    def _vodList(self, arr):
        out = []
        if not isinstance(arr, list):
            return out
        for j in arr:
            if not isinstance(j, dict):
                continue
            if not (j.get("id") or j.get("dramaId")):
                continue
            out.append(self._vod(j))
        return out

    # ---- 动态线路 ----
    def _lines_fetch(self):
        now = time.time()
        if self._lines is not None and (now - self._lines_at) < self.TTL_LINES and len(self._lines) > 0:
            return self._lines
        txt = self._api("/categories")
        arr = self._arr(txt) if txt else []
        kept = []
        for j in arr:
            if not isinstance(j, dict):
                continue
            if j.get("status", "active") != "active":
                continue
            if not (j.get("name", "") or ""):
                continue
            kept.append(j)
        try:
            kept.sort(key=lambda x: int(x.get("sortOrder", 99) or 99))
        except Exception:
            pass
        if kept:
            self._lines = kept
            self._lines_at = now
        elif self._lines is not None:
            return self._lines
        return kept

    def _homeList(self):
        txt = self._api("/home")
        out = []
        seen = set()
        blocks = self._obj(txt).get("blocks") if txt else None
        if isinstance(blocks, list):
            for blk in blocks:
                if len(out) >= 40:
                    break
                if not isinstance(blk, dict):
                    continue
                items = blk.get("items")
                if not isinstance(items, list):
                    continue
                for k, it in enumerate(items):
                    if k >= 6 or len(out) >= 40:
                        break
                    if not isinstance(it, dict):
                        continue
                    vid = it.get("id", "") or ""
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)
                    out.append(self._vod(it))
        if not out:
            return self._vodList(self._rankList(self.T_RANK))
        return out

    def _rankList(self, tid):
        path = "/ranks/wish" if tid == self.T_WISH else "/ranks/hot"
        txt = self._api(path)
        return self._arr(txt) if txt else []

    def _topicList(self, tid):
        txt = self._api("/topics")
        arr = self._arr(txt) if txt else []
        out = []
        for j in arr:
            if not isinstance(j, dict):
                continue
            if tid and j.get("id", "") != tid:
                continue
            out.extend(self._vodList(j.get("dramas")))
        return out

    # ---- mediaKey / episodeUrl / buildPlay ----
    def _mediaKey(self, episodes, cover):
        try:
            for ep in (episodes or []):
                if not isinstance(ep, dict):
                    continue
                u = ep.get("seoContentUrl", "") or ""
                if len(u) < 10:
                    continue
                m = self.P_MEDIA_HLS.search(u)
                if m:
                    return m.group(1)
        except Exception:
            pass
        if cover:
            m = self.P_MEDIA_COVER.search(cover)
            if m:
                return m.group(1)
        return ""

    @staticmethod
    def _episodeUrl(key, n):
        if key and len(key) >= 6 and n > 0:
            nn = ("0%d" % n) if n < 10 else str(n)
            return "https://7cat-media.bedfpk.cn/7cat/%s/hls/ep%s/ep%s.m3u8" % (key, nn, nn)
        return ""

    def _buildPlay(self, episodes, cover):
        if not isinstance(episodes, list) or len(episodes) == 0:
            return ""
        key = self._mediaKey(episodes, cover)
        parts = []
        for i, ep in enumerate(episodes):
            if not isinstance(ep, dict):
                continue
            url = ep.get("seoContentUrl", "") or ""
            if len(url) < 10:
                url = ""
            if not url and key:
                url = self._episodeUrl(key, int(ep.get("indexNo", i + 1) or (i + 1)))
            if len(url) < 10:
                continue
            name = ep.get("title", "") or ""
            if not name:
                name = "第%d集" % int(ep.get("indexNo", i + 1) or (i + 1))
            parts.append("%s$%s" % (name, url))
        return "#".join(parts)

    # ---- 翻页封装 ----
    def _pageOf(self, arr, page, total):
        arr = arr or []
        lst = []
        start = (page - 1) * self.PAGE
        for idx in range(start, len(arr)):
            if len(lst) >= self.PAGE:
                break
            if idx < 0:
                continue
            lst.append(arr[idx])
        tot = max(total, len(arr))
        pagecount = max(1, (max(total, len(arr)) + self.PAGE - 1) // self.PAGE)
        return {
            "page": page, "pagecount": pagecount, "limit": self.PAGE,
            "total": tot, "list": self._vodList(lst), "parse": 0, "jx": 0,
        }

    def _page0(self):
        return {"page": 1, "pagecount": 1, "limit": self.PAGE,
                "total": 0, "list": [], "parse": 0, "jx": 0}

    # ---- 12 接口 ----
    def homeContent(self, filter):
        try:
            classes = [
                {"type_id": self.T_RANK, "type_name": "🔥 热门榜"},
                {"type_id": self.T_NEW, "type_name": "🆕 最新上线"},
                {"type_id": self.T_ALL, "type_name": "📺 全部短剧"},
                {"type_id": self.T_WISH, "type_name": "✨ 魔改愿望榜"},
            ]
            lines = self._lines_fetch()
            for ln in lines:
                if not isinstance(ln, dict):
                    continue
                classes.append({
                    "type_id": self.T_LINE + (ln.get("id", "") or ""),
                    "type_name": ln.get("name", "") or "",
                })

            sort_filter = [{
                "key": "sort", "name": "排序",
                "value": [{"n": "最热", "v": "hot"}, {"n": "最新", "v": "latest"}],
            }]
            filters = {self.T_ALL: sort_filter, self.T_NEW: sort_filter, self.T_RANK: sort_filter}
            for ln in lines:
                if not isinstance(ln, dict):
                    continue
                filters[self.T_LINE + (ln.get("id", "") or "")] = sort_filter

            return {
                "class": classes, "filters": filters, "list": self._homeList(),
            }
        except Exception:
            return {"class": [], "filters": {}, "list": []}

    def homeVideoContent(self):
        try:
            return {"list": self._homeList()}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            try:
                page = max(1, int(str(pg or "1").strip()))
            except Exception:
                page = 1
            sort = ""
            if isinstance(extend, dict):
                sort = extend.get("sort") or ""
            if not sort:
                sort = "hot"
            tid = (tid or "").strip()

            if tid == self.T_RANK:
                tid = self.T_ALL  # /ranks/hot 只有 50 筆，改走 /browse?sort=hot 可無限翻頁
            if tid == self.T_WISH:
                arr = self._rankList(self.T_WISH)
                return self._pageOf(arr, page, len(arr))
            if tid.startswith(self.T_TOPIC):
                arr = self._topicList(tid[len(self.T_TOPIC):])
                return self._pageOf(arr, page, len(arr))

            base = "/browse?offset=%d&limit=%d" % ((page - 1) * self.PAGE, self.PAGE)
            if tid == self.T_NEW:
                url = base + "&sort=latest"
            elif tid.startswith(self.T_LINE):
                sv = "latest" if sort == "latest" else "hot"
                url = base + "&line=" + self._enc(tid[len(self.T_LINE):]) + "&sort=" + sv
            else:
                sv = "latest" if sort == "latest" else "hot"
                url = base + "&sort=" + sv

            txt = self._api(url)
            if txt is None:
                return self._page0()
            obj = self._obj(txt)
            items = obj.get("items") or []
            total = int(obj.get("total", 0) or 0)
            has_more = bool(obj.get("hasMore", False))
            if total > 0:
                pagecount = (total + self.PAGE - 1) // self.PAGE
            else:
                pagecount = page + 1 if has_more else page
            if pagecount < page:
                pagecount = page
            result = {
                "page": page, "pagecount": pagecount, "limit": self.PAGE,
                "total": total if total > 0 else page * self.PAGE,
                "list": self._vodList(items), "parse": 0, "jx": 0,
            }
            return result
        except Exception:
            return self._page0()

    def detailContent(self, ids):
        if not ids or len(ids) == 0:
            return {"list": []}
        try:
            raw = ids[0]
            if raw is None:
                return {"list": []}
            # 归一化：含 | 且过长时取 | 之后部分
            bar = raw.find("|")
            vid = raw
            if bar > 0 and len(raw) > 36:
                vid = raw[bar + 1:]
            vid = vid.replace("qmdj:", "").strip()

            txt = self._api("/dramas/" + self._enc(vid))
            if txt is None:
                return {"list": []}
            obj = self._obj(txt)
            if not obj:
                return {"list": []}

            vod = {"vod_id": vid, "vod_name": obj.get("title", "") or ""}
            cover = obj.get("coverUrl", "") or ""
            if cover:
                vod["vod_pic"] = cover
            desc = obj.get("description", "") or ""
            tags = obj.get("tags")
            tag_list = []
            if isinstance(tags, list):
                tag_list = [str(t) for t in tags if t]
            tn = " · ".join(tag_list) if tag_list else "短剧"

            n2 = int(obj.get("episodeCount", 0) or 0)
            free = int(obj.get("freeEpisodeCount", 9999) or 9999)
            coin = int(obj.get("coinPricePerEpisode", 0) or 0)
            unlocked = True
            if coin <= 0 and free >= 9999:
                unlocked = bool(obj.get("isVipBadge", False))
            heat = int(obj.get("heat", 0) or 0)

            vod["type_name"] = tn
            prefix = "🔓已解锁全片 · " if unlocked else ""
            vod["vod_remarks"] = "%s共%d集" % (prefix, n2)
            vod["vod_actor"] = "七猫短剧"
            vod["vod_director"] = ""

            content = ""
            if unlocked:
                nf = str(free) if (0 < free < 9999) else "若干"
                content += ("【本线已解锁 VIP / 金币付费墙：本站收费片原只放前 %s 集，"
                            "本线直接取全片。】\n" % nf)
            if heat > 0:
                content += "热度：%d · " % heat
            content += "分类：%s\n%s" % (tn, desc)
            vod["vod_content"] = content

            vod["vod_play_from"] = "七猫短剧"
            vod["vod_play_url"] = self._buildPlay(obj.get("episodes"), cover)

            return {"list": [vod], "parse": 0, "jx": 0}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        try:
            if not key or not key.strip():
                return {"list": []}
            try:
                page = max(1, int((pg or "1").strip()))
            except Exception:
                page = 1
            if page > 1:
                return {"list": []}
            txt = self._api("/search?q=%s&limit=50" % self._enc(key.strip()))
            arr = self._arr(txt) if txt else []
            return {"list": self._vodList(arr)}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        try:
            s = (id or "").strip()
            i = s.find("http")
            url = s[i:] if i > 0 else s
        except Exception:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": ""}
        return {
            "parse": 0, "jx": 0, "playUrl": "", "url": url,
            "header": {"User-Agent": self.UA, "Referer": "https://7maoduanju.com/"},
        }

    def localProxy(self, param):
        return [404, "text/plain", {}, ""]
