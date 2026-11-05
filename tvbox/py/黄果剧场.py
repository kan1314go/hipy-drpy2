# -*- coding: utf-8 -*-
"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '黄果剧场',
  lang: 'hipy'
})
"""
import sys
import re
import json
import urllib.parse

sys.path.append('..')
try:
    from base.spider import Spider as _B
except ImportError:
    class _B: pass

try:
    import requests
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    requests = None

# 常量定义
U = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class Spider(_B):
    def init(self, extend=""):
        self.s = requests.Session() if requests else None
        if self.s:
            self.s.headers.update({
                "User-Agent": U,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Cookie": "hg_age=1"
            })
            self.s.verify = False

        self.siteName = "黄果剧场"
        self.siteUrl = "https://huangguo.video"

        self.categories = [
            {"type_id": "1", "type_name": "MV/音乐剧"},
            {"type_id": "2", "type_name": "短片"},
            {"type_id": "3", "type_name": "连续剧"},
            {"type_id": "4", "type_name": "片段"},
        ]

        self.tag_options = [
            {"n": "全部", "v": ""},
            {"n": "都市", "v": "1"},
            {"n": "人妻", "v": "2"},
            {"n": "校园", "v": "5"},
            {"n": "职场", "v": "6"},
            {"n": "古风", "v": "7"},
            {"n": "乱伦", "v": "8"},
            {"n": "NTR", "v": "9"},
            {"n": "玄幻", "v": "40"},
        ]

        self._play_url_cache = {}

    def getName(self):
        return self.siteName

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def _http_get(self, url, referer=None):
        if not self.s:
            return ""
        headers = {}
        headers["Referer"] = referer or (self.siteUrl + "/")
            
        try:
            r = self.s.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            print(f'[黄果剧场] 请求失败 {url}: {e}')
        return ""

    def _parse_list(self, html):
        if not html:
            return []

        items = []
        seen = set()

        # 兼容处理所有卡片样式 (video-card, search-content-card 等)
        for art in re.finditer(
            r'<article[^>]*class="[^"]*(?:video-card|search-content-card|card)[^"]*"[^>]*>(.*?)</article>',
            html, re.S
        ):
            block = art.group(1)

            # 同时匹配 /video/ 和 /series/ 路由
            link_m = re.search(r'<a\s+href="(/(?:video|series)/[^"]+)"', block)
            if not link_m:
                # 兜底：尝试匹配任意带 href 的链接
                link_m = re.search(r'href="(/(?:video|series)/[^"]+)"', block)
                if not link_m:
                    continue

            path = link_m.group(1).strip()

            if path.startswith('/video/'):
                vid = 'video:' + path[len('/video/'):].strip('/')
            elif path.startswith('/series/'):
                vid = 'series:' + path[len('/series/'):].strip('/')
            else:
                continue

            if vid in seen:
                continue

            img_m = re.search(r'<img[^>]+src="([^"]+)"', block)
            cover = img_m.group(1).strip() if img_m else ""
            if cover.startswith('/'):
                cover = self.siteUrl + cover

            title = ""
            alt_m = re.search(r'<img[^>]+alt="([^"]*)"', block)
            if alt_m:
                title = alt_m.group(1).strip()
            if not title:
                t_m = re.search(
                    r'<p[^>]*class="[^"]*(?:text-cream|font-display|title)[^"]*"[^>]*>([^<]+)</p>',
                    block
                )
                if t_m:
                    title = t_m.group(1).strip()

            tag = ""
            tag_m = re.search(r'<span[^>]*class="[^"]*absolute[^"]*">([^<]+)</span>', block)
            if tag_m:
                tag = tag_m.group(1).strip()

            sub = ""
            sub_m = re.search(r'<p[^>]*class="[^"]*meta[^"]*">(.*?)</p>', block, re.S)
            if sub_m:
                sub = re.sub(r'<[^>]+>', '', sub_m.group(1)).strip()

            parts = []
            if tag:
                parts.append(tag)
            if sub:
                parts.append(sub)

            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": title or "未知剧集",
                "vod_pic": cover,
                "vod_remarks": " · ".join(parts) if parts else "连续剧",
            })

        # 如果标准 article 没抓到，尝试宽松抓取所有带有 /series/ 或 /video/ 的超链接卡片
        if not items:
            for m in re.finditer(r'<a\s+href="(/(?:series|video)/([^"]+))"[^>]*>(.*?)</a>', html, re.S):
                path = m.group(1)
                sub_path = m.group(2)
                inner = m.group(3)
                
                vid = ('series:' if '/series/' in path else 'video:') + sub_path.strip('/')
                if vid in seen:
                    continue
                
                img_m = re.search(r'src="([^"]+)"', inner)
                cover = img_m.group(1) if img_m else ""
                if cover.startswith('/'):
                    cover = self.siteUrl + cover
                
                title_m = re.search(r'alt="([^"]+)"', inner) or re.search(r'>([^<]+)</p>', inner)
                title = title_m.group(1).strip() if title_m else sub_path
                
                seen.add(vid)
                items.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": cover,
                    "vod_remarks": "连续剧" if 'series' in path else "正片"
                })

        return items

    def _extract_title(self, html):
        t_m = re.search(r'<title>(.*?)</title>', html, re.S)
        if t_m:
            title = t_m.group(1).strip()
            title = re.sub(r'\s*[-–|·]\s*黄果剧场.*$', '', title).strip()
            return title
        return ""

    def _extract_cover(self, html):
        m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
        if m:
            return m.group(1).strip()
        m = re.search(r'data-poster="([^"]+)"', html)
        if m:
            pic = m.group(1).strip()
            return pic if pic.startswith('http') else self.siteUrl + pic
        return ""

    def _extract_intro(self, html):
        m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
        return m.group(1).strip() if m else ""

    def _extract_hls(self, html):
        if not html:
            return ""
        m = re.search(r'data-hls="([^"]+)"', html)
        if m:
            url = m.group(1).strip()
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('/'):
                url = self.siteUrl + url
            return url
        return ""

    def _extract_episodes(self, html):
        if not html:
            return []
        eps = []
        seen = set()

        # 宽松匹配连续剧选集列表链接
        for m in re.finditer(r'<a[^>]+href="(/video/[^"]+)"([^>]*)>(.*?)</a>', html, re.S):
            path = m.group(1).strip()
            inner_tag = m.group(2)
            inner_text = m.group(3)
            
            ep_id = path[len('/video/'):].strip('/')
            if ep_id in seen:
                continue
                
            # 提取集数名称
            name_m = re.search(r'>([^<]+)</p>', inner_text) or re.search(r'>([^<]+)</span>', inner_text)
            if name_m:
                name = name_m.group(1).strip()
            else:
                clean_text = re.sub(r'<[^>]+>', '', inner_text).strip()
                name = clean_text if clean_text and len(clean_text) < 20 else f"第{len(eps) + 1}集"
                
            seen.add(ep_id)
            eps.append({"name": name, "ep_id": ep_id, "url": self.siteUrl + path})

        return eps

    def _extract_series_url(self, html):
        m = re.search(r'data-series-url="([^"]+)"', html)
        if m:
            url = m.group(1).strip()
            return url if url.startswith('http') else self.siteUrl + url
        return ""

    def _resolve_mp4_from_m3u8(self, master_url, referer):
        if not master_url:
            return ""

        content = self._http_get(master_url, referer=referer)
        if not content:
            return ""

        m = re.search(r'https?://[^\s"\'<>\\]+\.mp4[^\s"\'<>\\]*', content)
        if m:
            return m.group(0)

        base = master_url.rsplit('/', 1)[0]
        sub_urls = []
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('http') and '.m3u8' in line:
                sub_urls.append(line)
            elif line.endswith('.m3u8'):
                sub_urls.append(base + '/' + line.lstrip('/'))

        for sub in sub_urls:
            sub_content = self._http_get(sub, referer=referer)
            if not sub_content:
                continue
            m = re.search(r'https?://[^\s"\'<>\\]+\.mp4[^\s"\'<>\\]*', sub_content)
            if m:
                return m.group(0)
        return ""

    def homeContent(self, filter=False):
        filters = {
            "1": self._build_filters(),
            "2": self._build_filters(),
            "3": self._build_filters(),
            "4": self._build_filters(),
        }
        return {"class": self.categories, "filters": filters if filter else {}}

    def _build_filters(self):
        return [
            {
                "key": "rating",
                "name": "尺度",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "安全", "v": "safe"},
                    {"n": "裸露", "v": "nude"},
                    {"n": "限制级", "v": "explicit"},
                ]
            },
            {
                "key": "tags",
                "name": "标签",
                "value": self.tag_options,
            },
            {
                "key": "sort",
                "name": "排序",
                "value": [
                    {"n": "最新发布", "v": "latest"},
                    {"n": "最热", "v": "hot"},
                ]
            },
        ]

    def homeVideoContent(self):
        html = self._http_get(f"{self.siteUrl}/videos")
        items = self._parse_list(html)
        return {"list": items[:20]}

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        page = int(pg or 1)
        extend = extend or {}

        params = [f"category={tid}"]
        if extend.get("rating"):
            params.append(f"rating={extend['rating']}")
        if extend.get("tags"):
            params.append(f"tags={extend['tags']}")
        if extend.get("sort"):
            params.append(f"sort={extend['sort']}")
        if page > 1:
            params.append(f"page={page}")

        url = f"{self.siteUrl}/videos?" + "&".join(params)
        html = self._http_get(url)
        items = self._parse_list(html)

        return {
            "list": items,
            "page": page,
            "pagecount": page + 1 if items else page,
            "limit": 20,
            "total": 999,
        }

    def searchContent(self, key, quick=False, pg=1):
        page = int(pg or 1)
        kw = str(key or "").strip()
        if not kw:
            return {"list": [], "page": page, "pagecount": 1}

        url = f"{self.siteUrl}/search?q={urllib.parse.quote(kw)}"
        if page > 1:
            url += f"&page={page}"

        html = self._http_get(url)
        items = self._parse_list(html)

        return {
            "list": items,
            "page": page,
            "pagecount": page + 1 if items else page,
            "limit": 20,
            "total": len(items),
        }

    def detailContent(self, ids):
        raw = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        if not raw:
            return {"list": []}

        if raw.startswith('video:'):
            kind, real_id = 'video', raw[len('video:'):]
        elif raw.startswith('series:'):
            kind, real_id = 'series', raw[len('series:'):]
        else:
            kind, real_id = 'video', raw

        url = f"{self.siteUrl}/{kind}/{real_id}"
        html = self._http_get(url)
        if not html:
            return {"list": []}

        title = self._extract_title(html) or real_id
        pic = self._extract_cover(html)
        intro = self._extract_intro(html)

        play_urls = []

        if kind == 'series':
            eps = self._extract_episodes(html)
            for ep in eps:
                play_urls.append(f"{ep['name']}${ep['url']}")
        else:
            series_url = self._extract_series_url(html)
            if series_url:
                shtml = self._http_get(series_url)
                eps = self._extract_episodes(shtml)
                if eps:
                    for ep in eps:
                        play_urls.append(f"{ep['name']}${ep['url']}")
            if not play_urls:
                eps = self._extract_episodes(html)
                if eps:
                    for ep in eps:
                        play_urls.append(f"{ep['name']}${ep['url']}")

            if not play_urls:
                vurl = self._extract_hls(html)
                if vurl:
                    play_urls.append(f"正片${vurl}")
                else:
                    play_urls.append(f"正片${url}")

        return {
            "list": [{
                "vod_id": raw,
                "vod_name": title,
                "vod_pic": pic,
                "vod_content": intro,
                "vod_remarks": f"共{len(play_urls)}集" if play_urls else "正片",
                "vod_play_from": "黄果" if play_urls else "",
                "vod_play_url": "#".join(play_urls),
            }]
        }

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "").strip()
        if not raw:
            return {"parse": 1, "url": raw}

        if raw in self._play_url_cache:
            cached = self._play_url_cache[raw]
            return {
                "parse": 0,
                "url": cached,
                "header": {"User-Agent": U, "Referer": self.siteUrl + "/"}
            }

        final_url = ""

        if raw.startswith('http') and ('/video/' in raw or '/series/' in raw) and not self.isVideoFormat(raw):
            html = self._http_get(raw)
            master = self._extract_hls(html)
            if master:
                mp4 = self._resolve_mp4_from_m3u8(master, referer=raw)
                if mp4:
                    final_url = mp4
                else:
                    self._play_url_cache[raw] = master
                    return {
                        "parse": 0,
                        "url": master,
                        "header": {
                            "User-Agent": U,
                            "Referer": raw,
                            "Origin": self.siteUrl,
                            "Cookie": "hg_age=1",
                        }
                    }

        elif self.isVideoFormat(raw) and '.m3u8' in raw:
            mp4 = self._resolve_mp4_from_m3u8(raw, referer=self.siteUrl + "/")
            if mp4:
                final_url = mp4
            else:
                return {
                    "parse": 0,
                    "url": raw,
                    "header": {
                        "User-Agent": U,
                        "Referer": self.siteUrl + "/",
                        "Cookie": "hg_age=1",
                    }
                }

        elif self.isVideoFormat(raw) and '.mp4' in raw:
            final_url = raw

        if final_url:
            self._play_url_cache[raw] = final_url
            return {
                "parse": 0,
                "url": final_url,
                "header": {"User-Agent": U, "Referer": self.siteUrl + "/"}
            }

        return {
            "parse": 1,
            "url": raw,
            "header": {
                "User-Agent": U,
                "Referer": self.siteUrl + "/",
                "Cookie": "hg_age=1",
            }
        }

    def localProxy(self, param):
        pass
