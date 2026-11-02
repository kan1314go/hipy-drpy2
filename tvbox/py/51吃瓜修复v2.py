# -*- coding: utf-8 -*-
import json
import re
import sys
from urllib.parse import urlparse, quote, unquote, urljoin

import requests
from html import unescape as html_unescape
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider

PAGE_SIZE = 90


class Spider(Spider):

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.proxies = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                self.proxies = json.loads(extend)
            except Exception:
                self.proxies = {}
        else:
            self.proxies = {}

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
        }
        # 取得可用站點（若動態站點不可用，則自動回退至 51cg1.com）
        self.host = self.get_working_host()
        self.headers.update({'Origin': self.host, 'Referer': f"{self.host}/"})

    def getName(self):
        return "🌈 51吸瓜"

    def isVideoFormat(self, url):
        path = urlparse(str(url or '')).path.lower()
        return any(path.endswith(ext) for ext in ['.m3u8', '.mp4', '.ts', '.flv', '.mkv'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.proxies = {}

    def homeContent(self, filter):
        try:
            response = requests.get(self.host, headers=self.headers, proxies=self.proxies, timeout=10)
            if response.status_code != 200:
                return {'class': [], 'list': []}

            data = self.getpq(response.text)
            return {
                'class': self._collect_classes(data),
                'list': self.getlist(data)
            }
        except Exception:
            return {'class': [], 'list': []}

    def homeVideoContent(self):
        try:
            response = requests.get(self.host, headers=self.headers, proxies=self.proxies, timeout=10)
            if response.status_code != 200:
                return {'list': []}
            data = self.getpq(response.text)
            return {'list': self.getlist(data)}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page_num = max(1, int(pg)) if str(pg).isdigit() else 1
            tid = str(tid or '')

            if '@folder' in tid:
                folder_id = self._normalize_path(tid.replace('@folder', '')) or tid.replace('@folder', '')
                videos = self.getfod(folder_id)
                return {
                    'list': videos,
                    'page': page_num,
                    'pagecount': 1,
                    'limit': len(videos) or PAGE_SIZE,
                    'total': len(videos)
                }

            # type_id 可能是舊版存下的完整網址，先正規化成站內路徑再拼接，
            # 否則會出現 host + https://... 的錯誤網址，分類頁必然為空。
            path = self._normalize_path(tid) or '/'
            base_url = f"{self.host}{path}".rstrip('/')

            # 分頁格式不同主題不一致（/分類/2/ 與 /分類/page/2/），
            # 第一種取不到列表時自動嘗試第二種。
            if page_num > 1:
                candidate_urls = [f"{base_url}/{page_num}/", f"{base_url}/page/{page_num}/"]
            else:
                candidate_urls = [f"{base_url}/"]

            data = None
            videos = []
            for url in candidate_urls:
                response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=12)
                if response.status_code != 200:
                    continue
                data = self.getpq(response.text)
                videos = self.getlist(data, path)
                if videos:
                    break

            if data is None:
                return {'list': [], 'page': page_num, 'pagecount': 1, 'limit': PAGE_SIZE, 'total': 0}

            pagecount = self._pagecount(data, page_num, has_videos=bool(videos))
            return {
                'list': videos,
                'page': page_num,
                'pagecount': max(1, pagecount),
                'limit': PAGE_SIZE,
                'total': max(len(videos), page_num * PAGE_SIZE)
            }
        except Exception:
            return {'list': [], 'page': max(1, int(pg) if str(pg).isdigit() else 1), 'pagecount': 1, 'limit': PAGE_SIZE, 'total': 0}

    def detailContent(self, ids):
        try:
            if not ids or not ids[0]:
                return {'list': [], 'msg': '無效的影片 ID'}

            req_id = ids[0]
            url = req_id if req_id.startswith('http') else f"{self.host}{req_id}"
            response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=12)
            
            if response.status_code != 200:
                return {'list': [], 'msg': '頁面加載失敗'}
                
            data = self.getpq(response.text)
            vod = {
                'vod_id': req_id,
                'vod_name': self._safe_label(data('.post-title, h1, .entry-title').eq(0).text() or '51吸瓜视频'),
                'vod_pic': self._detail_pic(data),
                'vod_play_from': '51吸瓜'
            }
            
            try:
                clist = []
                if data('.tags .keywords a'):
                    for k in data('.tags .keywords a').items():
                        title = k.text().strip()
                        href = k.attr('href')
                        if title and href:
                            payload = json.dumps({'id': href, 'name': title, 'type_flag': '1'}, ensure_ascii=False)
                            clist.append(f"[a=cr:{payload}/]{title}[/a]")
                vod['vod_content'] = ' '.join(clist) if clist else (data('.post-title').text() or '')
            except Exception:
                vod['vod_content'] = data('.post-title').text() or ''
            
            plist = []
            used_names = set()
            if data('.dplayer'):
                for c, k in enumerate(data('.dplayer').items(), start=1):
                    config_attr = k.attr('data-config')
                    if not config_attr:
                        continue
                    try:
                        config = json.loads(config_attr)
                        video_url = config.get('video', {}).get('url', '')
                        if not video_url:
                            continue

                        ep_name = ''
                        try:
                            parent = k.parents().eq(0)
                            for _ in range(3):
                                if not parent: break
                                heading = parent.find('h2, h3, h4').eq(0).text() or ''
                                heading = heading.strip()
                                if heading:
                                    ep_name = heading
                                    break
                                parent = parent.parents().eq(0)
                        except Exception:
                            ep_name = ''

                        base_name = ep_name if ep_name else f"视频{c}"
                        name = base_name
                        count = 2
                        while name in used_names:
                            name = f"{base_name} {count}"
                            count += 1
                        used_names.add(name)
                        
                        safe_ep_name = self._safe_label(name)
                        plist.append(f"{safe_ep_name}${video_url}")
                    except Exception:
                        continue
            
            if plist:
                vod['vod_play_url'] = '#'.join(plist)
            else:
                return {'list': [], 'msg': '未找到有效視頻源'}
                    
            return {'list': [vod]}
        except Exception as e:
            return {'list': [], 'msg': f'詳情頁加載失敗: {type(e).__name__}'}

    def searchContent(self, key, quick, pg="1"):
        try:
            page_num = max(1, int(pg)) if str(pg).isdigit() else 1
            if page_num > 1:
                candidate_urls = [
                    f"{self.host}/search/{quote(key)}/{page_num}/",
                    f"{self.host}/search/{quote(key)}/page/{page_num}/",
                ]
            else:
                candidate_urls = [f"{self.host}/search/{quote(key)}/"]

            data = None
            videos = []
            for url in candidate_urls:
                response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=12)
                if response.status_code != 200:
                    continue
                data = self.getpq(response.text)
                videos = self.getlist(data)
                if videos:
                    break

            if data is None:
                return {'list': [], 'page': page_num, 'pagecount': 1, 'limit': PAGE_SIZE, 'total': 0}

            pagecount = self._pagecount(data, page_num, has_videos=bool(videos))

            return {
                'list': videos,
                'page': page_num,
                'pagecount': max(1, pagecount),
                'limit': PAGE_SIZE,
                'total': max(len(videos), page_num * PAGE_SIZE)
            }
        except Exception:
            return {'list': [], 'page': max(1, int(pg) if str(pg).isdigit() else 1), 'pagecount': 1, 'limit': PAGE_SIZE, 'total': 0}

    def playerContent(self, flag, id, vipFlags):
        url = str(id or '').strip()
        if not url:
            return {'parse': 0, 'msg': '無效的播放網址'}
            
        parse = 0 if self.isVideoFormat(url) else 1
        
        if parse == 0 and '.m3u8' in url and self.proxies:
            url = self.proxy(url)

        return {
            'parse': parse,
            'url': url,
            'header': self.headers
        }

    def localProxy(self, param):
        req_type = param.get('type')
        if req_type == 'img':
            img_url = unquote(str(param.get('url') or ''))
            if not img_url:
                return [404, 'text/plain', b'']
            res = requests.get(img_url, headers=self.headers, proxies=self.proxies, timeout=10)
            content = self.aesimg(res.content)
            return [200, self._img_content_type(content, res.headers.get('Content-Type')), content]
        elif req_type == 'm3u8':
            return self.m3Proxy(param['url'])
        else:
            return self.tsProxy(param['url'])

    def proxy(self, data, type='m3u8'):
        if data and self.proxies:
            return f"{self.getProxyUrl()}&url={self.e64(data)}&type={type}"
        return data

    def m3Proxy(self, url):
        url = self.d64(url)
        ydata = requests.get(url, headers=self.headers, proxies=self.proxies, allow_redirects=False)
        data = ydata.content.decode('utf-8', errors='ignore')
        if ydata.headers.get('Location'):
            url = ydata.headers['Location']
            data = requests.get(url, headers=self.headers, proxies=self.proxies).content.decode('utf-8', errors='ignore')
        lines = data.strip().split('\n')
        last_r = url[:url.rfind('/')]
        parsed_url = urlparse(url)
        durl = f"{parsed_url.scheme}://{parsed_url.netloc}"
        iskey = True
        for index, string in enumerate(lines):
            if iskey and 'URI' in string:
                pattern = r'URI="([^"]*)"'
                match = re.search(pattern, string)
                if match:
                    lines[index] = re.sub(pattern, f'URI="{self.proxy(match.group(1), "mkey")}"', string)
                    iskey = False
                    continue
            if '#EXT' not in string:
                if 'http' not in string:
                    domain = last_r if string.count('/') < 2 else durl
                    string = domain + ('' if string.startswith('/') else '/') + string
                lines[index] = self.proxy(string, string.split('.')[-1].split('?')[0])
        data = '\n'.join(lines)
        return [200, "application/vnd.apple.mpegurl", data]

    def tsProxy(self, url):
        url = self.d64(url)
        data = requests.get(url, headers=self.headers, proxies=self.proxies, stream=True)
        return [200, data.headers.get('Content-Type', 'video/MP2T'), data.content]

    @staticmethod
    def _safe_label(value):
        """清理標籤文字，避免破壞 Fongmi 播放分隔符 $ 與 #"""
        return str(value or '').replace('$', '＄').replace('#', '＃').strip()

    def get_working_host(self):
        """動態站點測試：若均不可用，直接使用 51cg1.com"""
        dynamic_urls = [
            'https://artist.vgwtswi.xyz',
            'https://ability.vgwtswi.xyz', 
            'https://am.vgwtswi.xyz'
        ]
        
        # 設定較短的 timeout(3秒)，避免 TV 端因超時卡死
        for url in dynamic_urls:
            try:
                response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=3)
                if response.status_code == 200:
                    data = self.getpq(response.text)
                    if len(data('article')) > 0 or len(data('#index a, #archive a')) > 0:
                        return url
            except Exception:
                continue
        
        # 動態站點全部連不上時，回退使用固定主站
        return "https://51cg1.com"

    # ---------- 路徑 / 分類 ----------

    @staticmethod
    def _normalize_path(href):
        """把導航 href 正規化成站內路徑：完整網址只取 path，去掉 query/fragment。"""
        href = str(href or '').strip()
        if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:')):
            return ''
        try:
            path = unquote(urlparse(href).path or '')
        except Exception:
            return ''
        if not path:
            return ''
        if not path.startswith('/'):
            path = '/' + path
        return re.sub(r'/+', '/', path)

    def _collect_classes(self, data):
        """收集分類（依 51cg1.com 真實首頁源碼修訂）。

        真實分類的路徑全都是 /category/<slug>/；導航裡混著大量站務
        頁（/telegram.html 官方TG群、/qun.html 官方QQ群、/twitter.html
        官方推特、/share.html、/archives/... 等）與外站推廣連結。
        所以主規則只認 /category/ 路徑，從根本上排除官方TG等條目；
        同一路徑出現長短兩種名稱時（如「今日吃瓜每日更新」與
        「今日吃瓜」）保留最短的乾淨名稱。
        只有完全找不到 /category/ 連結時（其他鏡像站結構不同）才
        回退到通用導航掃描，且回退時外站連結不剝域名硬轉站內路徑、
        .html 站務頁與社群連結一律排除。
        """
        found = {}
        order = []

        def clean_name(name):
            name = ' '.join(str(name or '').split())
            name = re.sub(r'\s*[\(（]\d+[\)）]\s*$', '', name).strip()
            name = re.sub(r'(每日更新|热播推荐|熱播推薦|热门推荐)$', '', name).strip()
            return name

        def is_social(name, path):
            low_name = str(name or '').lower()
            low_path = str(path or '').lower()
            return (
                'telegram' in low_path or 'telegram' in low_name
                or 'tg群' in low_name or '官方tg' in low_name
                or '电报' in str(name or '') or '電報' in str(name or '')
                or '推特' in str(name or '') or 'twitter' in low_name
                or 'qq群' in low_name or 'github' in low_name
            )

        def add_category(name, href):
            name = clean_name(name)
            path = self._normalize_path(href)
            if not name or len(name) > 20 or name.isdigit():
                return
            if not re.fullmatch(r'/category/[^/]+/?', path):
                return
            if not path.endswith('/'):
                path += '/'
            if is_social(name, path):
                return
            if path in found:
                if len(name) < len(found[path]):
                    found[path] = name
                return
            found[path] = name
            order.append(path)

        try:
            for k in data('a').items():
                href = k.attr('href') or ''
                if '/category/' in href:
                    add_category(k.text(), href)
        except Exception:
            pass

        if order:
            return [{'type_name': found[path], 'type_id': path} for path in order]

        # ---- 回退：沒有 /category/ 路徑時的通用導航掃描 ----
        bad_names = {
            '首页', '主頁', '主页', 'Home', 'HOME', '登录', '登陸', '注册',
            '搜索', '搜尋', '上一页', '下一页', '上一頁', '下一頁',
            'github', 'GitHub', 'twitter', 'Twitter', '菜单', '菜單', '更多',
        }
        bad_parts = (
            'QQ群', 'TG群', '電報群', '电报群', '官方群', '推特', '下載APP',
            '下载APP', 'APP下载', '用戶協議', '用户协议', '隱私', '隐私',
            'DMCA', '合規', '合规', 'RSS', '訂閱', '订阅',
        )
        bad_path_parts = (
            '/search/', '/login', '/register', '/feed', '/rss', '/usr/',
            '/admin', '/action/', '/author/', '/page/', '/user/',
            '/telegram', '/twitter', '/qun', '/github',
        )
        bad_exts = (
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico',
            '.css', '.js', '.apk', '.zip', '.xml', '.mp4', '.m3u8', '.html',
        )
        host_netloc = urlparse(str(getattr(self, 'host', '') or '')).netloc

        classes = []
        seen = set()

        def add(name, href):
            name = clean_name(name)
            if not name or name in bad_names or len(name) > 20:
                return
            if name.isdigit() or any(part in name for part in bad_parts):
                return
            if is_social(name, href):
                return
            # 外站連結直接排除，不再剝掉域名變成假的站內分類
            parsed = urlparse(str(href or ''))
            if parsed.netloc and host_netloc and parsed.netloc != host_netloc:
                return
            path = self._normalize_path(href)
            if not path or path == '/' or path in seen:
                return
            low = path.lower()
            if low.endswith(bad_exts) or any(part in low for part in bad_path_parts):
                return
            seen.add(path)
            classes.append({'type_name': name, 'type_id': path})

        containers = (
            'header a', 'nav a', '.category-list a', '.nav-menu a',
            '.menu a', '.navbar a', '.site-nav a', '.main-menu a',
            '#nav a', '#menu a', '.header a',
        )
        for selector in containers:
            try:
                for k in data(selector).items():
                    add(k.text(), k.attr('href'))
            except Exception:
                continue

        return classes

    def _pagecount(self, data, page_num, has_videos=False):
        numbers = []
        try:
            for selector in ('.pagination', '.page-nav', '.pager', '.nav-links', '.pages', 'nav'):
                for link in data(selector).find('a').items():
                    text = (link.text() or '').strip()
                    if text.isdigit():
                        numbers.append(int(text))
                    href_num = re.search(r'/(?:page/)?(\d+)/?$', (link.attr('href') or '').split('?')[0])
                    if href_num and text:
                        numbers.append(int(href_num.group(1)))
                if numbers:
                    break
        except Exception:
            numbers = []
        pagecount = max(numbers) if numbers else 1
        if pagecount <= page_num and has_videos:
            try:
                if data('a:contains("下一页"), a:contains("下頁"), a:contains("Next")'):
                    pagecount = page_num + 1
            except Exception:
                pass
        return max(1, pagecount)

    # ---------- 封面 ----------

    def _proxy_img(self, raw):
        """加密封面走本機代理（AES 解密）。網址先 quote，避免 & 截斷代理參數。"""
        raw = html_unescape(str(raw or '')).replace('\\/', '/').strip()
        if not raw:
            return ''
        if raw.startswith('//'):
            raw = 'https:' + raw
        elif not raw.startswith(('http://', 'https://')):
            raw = urljoin(f"{self.host}/", raw)
        try:
            return f"{self.getProxyUrl()}&url={quote(raw, safe='')}&type=img"
        except Exception:
            return raw

    def _direct_img(self, raw):
        raw = html_unescape(str(raw or '')).replace('\\/', '/').strip()
        if not raw or raw.startswith('data:'):
            return ''
        if raw.startswith('//'):
            return 'https:' + raw
        if raw.startswith(('http://', 'https://')):
            return raw
        return urljoin(f"{self.host}/", raw)

    @staticmethod
    def _looks_like_chrome_img(url):
        """站點外觀圖（logo/頭像/圖標/廣告橫幅）不是封面，跳過。"""
        low = str(url or '').lower()
        return any(x in low for x in (
            'logo', 'avatar', 'icon', 'sprite', 'loading', 'placeholder',
            'blank.gif', 'default.jpg', '/usr/themes/', 'favicon',
        ))

    def _extract_cover(self, unit):
        """從一個列表單元（article）裡提取封面（依真實源碼修訂）。

        51cg1.com（Mirages 主題）的真實封面寫法是：
            <div class="blog-background"
                 x-bg-loader-url="https://pic.gyezbp.cn/.../*.jpeg">
        而且該 CDN 回傳的是 AES 加密字節（Content-Type 為
        binary/octet-stream，魔數不是 JPEG），瀏覽器靠主題 JS 解密，
        App 直接拿原始網址必然加載不出來。所以取到的封面一律走
        本機代理 type=img，由 localProxy 下載後 AES 解密再回傳
        （localProxy 已改成先認魔數：明文圖原樣回傳，不會誤傷）。

        優先級：x-bg-loader-url / z-image-loader-url（主題加載器）
        > loadBannerDirect 加密圖 > data-xkrkllgl > 懶加載屬性
        > 普通 img（跳過 zw-1.png 等佔位圖）> background-image。
        """
        raw = ''

        try:
            for attr in ('x-bg-loader-url', 'z-bg-loader-url', 'z-image-loader-url'):
                for el in unit(f'[{attr}]').items():
                    value = el.attr(attr)
                    if value and not self._looks_like_chrome_img(value):
                        raw = value
                        break
                if raw:
                    break
        except Exception:
            pass

        try:
            html = html_unescape(unit.html() or '')
        except Exception:
            html = ''

        if not raw and html:
            match = re.search(r"loadBanner\w*\(\s*['\"]([^'\"]+)['\"]", html)
            if match:
                raw = match.group(1)

        if not raw:
            try:
                for img in unit('img').items():
                    custom = img.attr('data-xkrkllgl')
                    if custom and not self._looks_like_chrome_img(custom):
                        raw = custom
                        break
                if not raw:
                    for attr in ('data-src', 'data-original', 'data-lazy-src', 'data-url', 'src'):
                        for img in unit('img').items():
                            value = img.attr(attr)
                            if value and not self._looks_like_chrome_img(value):
                                raw = value
                                break
                        if raw:
                            break
            except Exception:
                pass

        if not raw and html:
            match = re.search(r"background(?:-image)?\s*:\s*url\(['\"]?([^'\")]+)", html)
            if match and not self._looks_like_chrome_img(match.group(1)):
                raw = match.group(1)
            else:
                match = re.search(r"(https?:)?//[^\s'\"<>]+?\.(?:jpg|jpeg|png|webp|gif)", html)
                if match and not self._looks_like_chrome_img(match.group(0)):
                    raw = match.group(0)

        if not raw or str(raw).startswith('data:'):
            return ''
        return self._proxy_img(raw)

    def _detail_pic(self, data):
        for selector in ('article', '.post-content', '.entry-content', '.post', '.content'):
            try:
                units = data(selector)
                if len(units):
                    pic = self._extract_cover(units.eq(0))
                    if pic:
                        return pic
            except Exception:
                continue
        return ''

    # ---------- 列表 ----------

    def getlist(self, data, tid=''):
        """data 為整頁 PyQuery 文件（修復版）。

        原寫法逐個遍歷 <article> 裡的 <a>，同一篇文章的封面連結
        （無標題）和標題連結（含 h2 但無封面）被拆成兩筆，只有
        標題那筆留下來且封面為空，還會產生重複。這裡以 <article>
        為一筆：連結、標題、日期、封面都在同一單元內提取並去重。
        頁面沒有 <article> 時回退到按 href 合併 <a> 的舊結構。
        """
        videos = []
        is_folder = '/mrdg' in str(tid or '')
        seen = set()

        def push(href, name, remarks, pic):
            href = str(href or '').strip()
            name = ' '.join(str(name or '').replace('\n', ' ').split())
            if not href or not name:
                return
            # <script> 的文本不是標題（例如封面腳本 loadBannerDirect(...)）
            if 'loadBanner' in name or 'function(' in name or '://' in name:
                return
            # 只有角標文字（如「熱門」圖卡）不是真標題，整筆丟棄
            if name in ('热门', '熱門', '热播', '推薦', '推荐', '置顶', '广告', 'HOT', 'NEW'):
                return
            key = href.split('#')[0]
            if key in seen:
                return
            seen.add(key)
            item = {
                'vod_id': f"{href}{'@folder' if is_folder else ''}",
                'vod_name': self._safe_label(name),
                'vod_pic': pic or '',
                'vod_remarks': self._safe_label(' '.join(str(remarks or '').split())),
                'style': {"type": "rect", "ratio": 1.33}
            }
            if is_folder:
                item['vod_tag'] = 'folder'
            videos.append(item)

        try:
            units = data('article')
        except Exception:
            units = []

        if len(units):
            for unit in units.items():
                # 跳過列表廣告位（外站推廣卡片，不是文章）
                try:
                    if len(unit('.post-card-ads, .tjtagmanager, a[data-ad_slot_key]')):
                        continue
                except Exception:
                    pass
                title_link = unit('h2 a').eq(0)
                href = title_link.attr('href')
                name = unit('h2').eq(0).text() or unit('h1, h3').eq(0).text()
                if not href:
                    # 找第一個帶文字或指向文章的連結
                    for a in unit('a').items():
                        if (a.text() or '').strip() or a('img'):
                            href = a.attr('href')
                            if href:
                                break
                if not name:
                    for a in unit('a').items():
                        if (a.text() or '').strip() and not len(a('script')):
                            name = a.text()
                            break
                remarks = (
                    unit('span[itemprop="datePublished"]').text()
                    or unit('time').eq(0).text()
                    or unit('time').eq(0).attr('datetime')
                    or unit('.post-meta, .entry-meta, .meta, .date').eq(0).text()
                )
                push(href, name, remarks, self._extract_cover(unit))
            return videos

        # 無 article 結構時：按 href 合併同一篇文章的封面連結與標題連結
        merged = {}
        order = []
        try:
            links = data('#index a, #archive a, main a, .post a, .list a')
            if not len(links):
                links = data('a')
            for k in links.items():
                href = (k.attr('href') or '').strip()
                if not href:
                    continue
                if href not in merged:
                    merged[href] = {'name': '', 'pic': '', 'remarks': ''}
                    order.append(href)
                entry = merged[href]
                text = (k('h2').text() or '').strip()
                if not text and not len(k('script')):
                    text = (k.text() or '').strip()
                if text and 'loadBanner' in text:
                    text = ''
                if text and not entry['name']:
                    entry['name'] = text
                if not entry['pic']:
                    entry['pic'] = self._extract_cover(k)
                if not entry['pic']:
                    try:
                        entry['pic'] = self._extract_cover(k.parent())
                    except Exception:
                        pass
        except Exception:
            pass
        for href in order:
            entry = merged[href]
            push(href, entry['name'], entry['remarks'], entry['pic'])
        return videos

    def getfod(self, folder_id):
        folder_id = str(folder_id or '')
        url = folder_id if folder_id.startswith('http') else f"{self.host}{folder_id}"
        response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=12)
        if response.status_code != 200:
            return []

        data = self.getpq(response.text)
        vdata = data('.post-content[itemprop="articleBody"]')
        if not len(vdata):
            vdata = data('article, .post-content, .entry-content').eq(0)
        for i in ['.txt-apps', '.line', 'blockquote', '.tags', '.content-tabs']:
            vdata.remove(i)

        p = vdata('p')
        videos = []
        for i, x in enumerate(vdata('h2').items()):
            c = i * 2
            name = p.eq(c).text()
            vod_id = p.eq(c)('a').attr('href') or ''
            if not vod_id or not (name or '').strip():
                continue
            pic = self._extract_cover(p.eq(c + 1)) if len(p) > c + 1 else ''
            videos.append({
                'vod_id': vod_id,
                'vod_name': self._safe_label(name),
                'vod_pic': pic,
                'vod_remarks': self._safe_label(x.text())
            })
        return videos

    def getimg(self, text):
        """兼容舊呼叫：從腳本文本裡找加密封面網址。"""
        text = html_unescape(str(text or ''))
        match = re.search(r"loadBanner\w*\(\s*['\"]([^'\"]+)['\"]", text)
        if not match:
            match = re.search(r"(https?:\\?/\\?/[^\s'\"]+?\.(?:jpg|jpeg|png|webp))", text)
        if match:
            return self._proxy_img(match.group(1))
        return ''

    @staticmethod
    def _img_content_type(content, fallback=None):
        """依解密後字節的魔數判斷真實圖片類型（上游只回 octet-stream）。"""
        if content[:3] == b'\xff\xd8\xff':
            return 'image/jpeg'
        if content[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if content[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
            return 'image/webp'
        if fallback and str(fallback).startswith('image/'):
            return fallback
        return 'image/jpeg'

    def aesimg(self, word):
        # 已是明文圖片（魔數正確）就原樣回傳，避免對普通圖做無謂解密
        if word[:3] == b'\xff\xd8\xff' or word[:8] == b'\x89PNG\r\n\x1a\n' \
                or word[:6] in (b'GIF87a', b'GIF89a') \
                or (word[:4] == b'RIFF' and word[8:12] == b'WEBP'):
            return word
        try:
            key = b'f5d965df75336270'
            iv = b'97b60394abc2fbe1'
            cipher = AES.new(key, AES.MODE_CBC, iv)
            return unpad(cipher.decrypt(word), AES.block_size)
        except Exception:
            return word

    def getpq(self, data):
        try:
            return pq(data)
        except Exception:
            return pq(data.encode('utf-8'))