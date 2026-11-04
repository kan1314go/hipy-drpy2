# -*- coding: utf-8 -*-
import sys, re, json, urllib.parse, os, time
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
U = "Mozilla/5.0 (Linux; Android 12; TFY-AN00 Build/HONORTFY-AN00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.105 Mobile Safari/537.36 uni-app Html5Plus/1.0 (Immersed/33.0)"
DOMAIN_API = "https://lwncnss3api.cc/api/getapi.php"
CACHE_FILE = "domain_cache.json"
CACHE_EXPIRE = 1800  # 缩短缓存有效期至30分钟，便于及时刷新可用域名

# 更全面的备用域名列表
BACKUP_DOMAINS = [
    "dag29jmgma1g.site",
    "ldngksapi.cc",
    "lagh23ksapi.cc",
    "ldagwhdgpi.cc",
    "lwetasdf3api.cc",
    "lwasga289api.cc",
    "lw2wthchhaapi.cc",
    "lwncnss3api.cc",
    "lw23412gaapi.cc"
]

class Spider(_B):
    def init(self, extend=""):
        """初始化方法，兼容主流影视壳子传参"""
        self.s = requests.Session() if requests else None
        if self.s:
            self.s.headers.update({
                "User-Agent": U, 
                "Accept-Encoding": "gzip",
                "Content-Type": "application/x-www-form-urlencoded"
            })
            self.s.verify = False
        
        self.token = ""
        self.domains = []
        self.working_domains = []
        self._load_domains()
        
        if len(self.domains) < 3:
            self.domains.extend(BACKUP_DOMAINS)
            self.domains = list(set(self.domains))
        
        self._register()

    def getName(self):
        return "萝莉岛"

    def isVideoFormat(self, u):
        return ".m3u8" in u or ".mp4" in u or "preview" in u

    def manualVideoCheck(self):
        return False

    def _get_cache_path(self):
        """获取缓存文件路径，适配沙盒或当前目录"""
        try:
            return os.path.join(os.path.dirname(__file__), CACHE_FILE)
        except:
            return CACHE_FILE

    def _load_domains(self):
        """加载域名列表"""
        cache_path = self._get_cache_path()
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if time.time() - cache_data.get('cache_time', 0) < CACHE_EXPIRE:
                        domains = cache_data.get('domains', [])
                        self.domains = [d for d in domains if d and isinstance(d, str) and '.' in d]
                        if self.domains:
                            return
            except Exception as e:
                print(f'[CACHE] Read cache failed: {e}')
        
        self._fetch_domains()

    def _fetch_domains(self):
        """从API获取域名列表，失败则启用备用域名"""
        if not self.s:
            self.domains = BACKUP_DOMAINS.copy()
            return
            
        try:
            r = self.s.get(DOMAIN_API, timeout=5)
            try:
                data = r.json()
            except:
                domains = re.findall(r'[\w\-\.]+\.(?:com|cc|net|org|site|top|xyz)', r.text)
                if domains:
                    self.domains = list(set(domains))
                    self._save_cache(self.domains, [])
                    return
                data = {}
            
            if data.get('code') == 200:
                domains = data.get('data', [])
                blacklist = data.get('blackdomain', [])
                
                if isinstance(domains, str):
                    try:
                        domains = json.loads(domains)
                    except:
                        domains = [domains]
                
                if not isinstance(domains, list):
                    domains = [str(domains)] if domains else []
                
                all_domains = list(set(domains + blacklist))
                self.domains = [d for d in all_domains if d and isinstance(d, str) and '.' in d]
                
                priority_domains = [d for d in domains if d and '.' in d]
                other_domains = [d for d in self.domains if d not in priority_domains]
                self.domains = priority_domains + other_domains
                
                if self.domains:
                    self._save_cache(all_domains, [])
                else:
                    self.domains = BACKUP_DOMAINS.copy()
            else:
                self.domains = BACKUP_DOMAINS.copy()
                self._save_cache(self.domains, [])
        except Exception as e:
            print(f'[DOMAIN] Fetch failed, using backup domains: {e}')
            self.domains = BACKUP_DOMAINS.copy()
            self._save_cache(self.domains, [])

    def _save_cache(self, domains, blacklist):
        try:
            cache_data = {
                'domains': domains,
                'blacklist': blacklist,
                'cache_time': time.time()
            }
            with open(self._get_cache_path(), 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[CACHE] Save failed: {e}')

    def _test_domain(self, domain):
        if not self.s:
            return False
        for protocol in ['https', 'http']:
            url = f"{protocol}://{domain}/api/setapp.php"
            try:
                r = self.s.get(url, timeout=3)
                if r.status_code == 200:
                    return True
            except:
                continue
        return False

    def _find_working_domain(self):
        if self.working_domains:
            for domain in self.working_domains[:]:
                if self._test_domain(domain):
                    return domain
                else:
                    self.working_domains.remove(domain)
        
        for domain in self.domains:
            if self._test_domain(domain):
                self.working_domains.append(domain)
                return domain
        
        # 如果常规列表没找到，强制用备用域名再试一次
        for domain in BACKUP_DOMAINS:
            if self._test_domain(domain):
                return domain
                
        return None

    def _request_api(self, path, method='post', data=None, params=None):
        if not self.s:
            return None
            
        domain = self._find_working_domain()
        if not domain:
            self._fetch_domains()
            domain = self._find_working_domain()
            if not domain:
                return None
        
        for protocol in ['https', 'http']:
            url = f"{protocol}://{domain}{path}"
            try:
                if method.lower() == 'get':
                    r = self.s.get(url, params=params, timeout=5)
                else:
                    r = self.s.post(url, data=data, params=params, timeout=5)
                
                if r.status_code == 200:
                    return r
            except:
                continue
        
        if domain in self.working_domains:
            self.working_domains.remove(domain)
        return self._request_api(path, method, data, params)

    def _register(self):
        try:
            r = self._request_api('/api/newreg.php', 'post', 
                data={"device": "android", "ntoken": "", "channel_code": "vbtQg9D8"}
            )
            if r:
                data = r.json()
                self.token = data.get("user", {}).get("token", "")
        except Exception as e:
            print('[REGISTER]', e)

    def homeContent(self, filter=False):
        try:
            r = self._request_api('/api/setapp.php', 'get')
            if r:
                data = r.json()
                classes = []
                filters = {}
                
                tabs = data.get("vodtab", []) + data.get("vodtaban", [])
                for tab in tabs:
                    tid = tab.get("type_id")
                    classes.append({
                        "type_id": tid,
                        "type_name": tab.get("type_name")
                    })
                    tags = tab.get("vodtags", [])
                    if tags:
                        tag_values = [{"n": "全部", "v": ""}]
                        for tag in tags:
                            tag_values.append({"n": tag.get("name"), "v": tag.get("name")})
                        filters[tid] = [{"key": "class", "name": "标签", "value": tag_values}]
                
                return {"class": classes, "filters": filters if filter else {}}
            
            return {"class": [], "filters": {}}
        except Exception as e:
            print('[HOME]', e)
            return {"class": [], "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        if not extend: extend = {}
        num = (int(pg) - 1) * 30
        payload = {
            "num": str(num),
            "pid": str(tid),
            "area": "全部",
            "vodclass": extend.get("class", ""),
            "vodyear": "全部",
            "sort": "1",
            "token": self.token
        }
        
        try:
            r = self._request_api('/api/vlist.php', 'post', data=payload)
            if r:
                data = r.json()
                videos = []
                for item in data.get("list", []):
                    videos.append({
                        "vod_id": str(item.get("vod_id", "")),
                        "vod_name": item.get("vod_name", ""),
                        "vod_pic": item.get("vod_pic", ""),
                        "vod_remarks": item.get("vod_class", "") or item.get("vod_remarks", "")
                    })
                return {"list": videos, "page": pg}
        except Exception as e:
            print('[CATEGORY]', e)
        
        return {"list": []}

    def detailContent(self, ids):
        payload = {
            "id": str(ids[0]),
            "token": self.token,
            "channel": ""
        }
        
        try:
            r = self._request_api('/api/Get_vod_list.php', 'post', data=payload)
            if r:
                data = r.json().get("data", {})
                
                play_url = data.get("vod_play_url", "")
                if not play_url:
                    play_url = "预览$" + data.get("preview_url", "")

                video = {
                    "vod_id": str(data.get("vod_id", ids[0])),
                    "vod_name": data.get("vod_name", ""),
                    "vod_pic": data.get("vod_pic", ""),
                    "vod_remarks": data.get("vod_remarks", ""),
                    "vod_content": data.get("vod_blurb", "暂无简介"),
                    "vod_play_from": "萝莉岛",
                    "vod_play_url": play_url
                }
                return {"list": [video]}
        except Exception as e:
            print('[DETAIL]', e)
        
        return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        return {
            "parse": 0,
            "url": id,
            "header": json.dumps({"User-Agent": U})
        }

    def searchContent(self, key, quick=False, pg=1):
        return {"list": []}

    def localProxy(self, param):
        pass
