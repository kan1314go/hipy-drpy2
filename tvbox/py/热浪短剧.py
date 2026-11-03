"""
热浪短剧 TVBox Python Spider（精简版）
站点: asian.nhdtwcfn.cc (Nuxt 3 SSR)
数据来源: __NUXT_DATA__ JSON 结构化数据
图片: AES-128-CBC 加密，直接解密返回 data URI
播放: AES-128 HLS，parse=0 原生播放
"""
import re
import json
import base64
import requests
from urllib.parse import quote, urlparse, unquote

from base.spider import Spider as BaseSpider

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
HOSTS = ["https://asian.nhdtwcfn.cc", "https://also.ykyxzkqu.cc"]
MEDIA_KEY = "f5d965df75336270"
MEDIA_IV = "97b60394abc2fbe1"
MEDIA_HOSTS = ["pic.hdhwqx.cn", "pic.xustgq.cn", "imgpublic.ycomesc.live", "pic.sbhioa.cn"]


class Spider(BaseSpider):
    name = "热浪短剧"

    def init(self, extend=""):
        self.base_url = HOSTS[0]
        for h in HOSTS:
            try:
                r = requests.get(h + "/explore-drama/", timeout=10, headers={"User-Agent": UA})
                if r.status_code == 200 and "__NUXT_DATA__" in r.text:
                    self.base_url = h
                    break
            except Exception:
                pass

    def _request(self, path, timeout=15):
        url = path if path.startswith("http") else self.base_url + path
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=timeout,
                                 headers={"User-Agent": UA, "Referer": self.base_url + "/"})
                r.encoding = "utf-8"
                if r.status_code == 200:
                    return r.text
            except Exception:
                if attempt == 2:
                    raise
        return ""

    def _extract_nuxt(self, html):
        m = re.search(r'<script type="application/json" data-nuxt-data="nuxt-app" data-ssr="true" id="__NUXT_DATA__">(.*?)</script>', html, re.S)
        return json.loads(m.group(1)) if m else []

    def _r1(self, flat, val):
        """解引用一层"""
        if isinstance(val, int) and 0 <= val < len(flat):
            return flat[val]
        return val

    def _r(self, flat, val, depth=0):
        """递归解引用"""
        max_depth = depth if depth else 5
        for _ in range(max_depth):
            if isinstance(val, int) and 0 <= val < len(flat):
                val = flat[val]
            else:
                break
        return val

    def _str(self, flat, val):
        """解引用并返回字符串"""
        v = self._r(flat, val)
        if isinstance(v, str):
            return v.replace("\\u002F", "/")
        return str(v) if v is not None else ""

    def _add_vods(self, flat):
        result = []
        for item in flat:
            if not isinstance(item, dict) or "video_id" not in item:
                continue
            vid = self._r1(flat, item["video_id"])
            if not vid:
                continue
            name_raw = item.get("title", "")
            if isinstance(name_raw, int):
                name = self._r1(flat, name_raw)
                if isinstance(name, str):
                    name = name.replace("\\u002F", "/")
                else:
                    name = self._str(flat, name)
            else:
                name = self._str(flat, name_raw)
            cover = self._str(flat, item.get("cover", ""))
            remark = self._str(flat, item.get("serialize_status_text", ""))
            ep_raw = item.get("episodes", 0)
            ep_deref = self._r1(flat, ep_raw) if isinstance(ep_raw, int) else ep_raw
            if isinstance(ep_deref, list):
                ep = len(ep_deref)
            elif isinstance(ep_deref, int):
                ep = ep_deref
            else:
                ep = 0
            if isinstance(ep, int) and ep:
                remark = f"{remark} {ep}集" if remark else f"{ep}集"
            elif not remark and isinstance(ep, list):
                remark = f"{len(ep)}集"
            if cover and not cover.startswith("data:") and \
                    any(h in cover for h in MEDIA_HOSTS):
                cover = self.decrypt_pic(cover)
            result.append({"vod_id": vid, "vod_name": name,
                           "vod_pic": cover, "vod_remarks": remark})
        return result

    def homeContent(self, filter):
        html = self._request("/explore-drama/")
        flat = self._extract_nuxt(html)

        # 提取筛选配置
        filters = {}
        for item in flat:
            if isinstance(item, dict) and "video_filter" in item:
                vf = self._r(flat, item["video_filter"])
                if isinstance(vf, dict):
                    for dim_name, dim_ref in vf.items():
                        dim_val = self._r(flat, dim_ref)
                        if isinstance(dim_val, dict):
                            param = self._str(flat, dim_val.get("parameter", ""))
                            lst = self._r1(flat, dim_val.get("list", []))
                            opts = []
                            if isinstance(lst, list):
                                for opt_ref in lst:
                                    opt = self._r1(flat, opt_ref)
                                    if isinstance(opt, dict):
                                        n = self._str(flat, opt.get("name", ""))
                                        v = self._r1(flat, opt.get("value", ""))
                                        opts.append({"n": n, "v": str(v)})
                            filters[param] = opts
                break

        classes = [{"type_id": "explore", "type_name": "全部"}]
        vods = self._add_vods(flat)
        # 筛选配置挂到 explore 分类
        filters_list = []
        for param, opts in filters.items():
            filters_list.append({"key": param, "name": param, "value": opts})
        # 计算 pagecount
        total = 0
        limit = 20
        for item in flat:
            if isinstance(item, dict) and "total" in item:
                t = self._r(flat, item["total"])
                if isinstance(t, int) and t > 0:
                    total = t
                    break
        pagecount = max(1, (total + limit - 1) // limit) if total else 1
        
        return {"class": classes, "filters": {"explore": filters_list}, "list": vods,
                "page": 1, "pagecount": pagecount, "limit": limit, "total": total}

    def categoryContent(self, tid, pg, filter, ext):
        pg = str(pg) if pg else "1"

        if tid == "explore":
            # 用 ext 构造 6 维筛选 URL
            if ext and isinstance(ext, dict):
                vals = [ext.get(k, "0") for k in ["theme", "setting", "background", "audience", "time", "recommend"]]
                filter_id = "-".join(str(v) if v else "0" for v in vals)
            else:
                filter_id = "0-0-0-0-0-0"
            base = f"/explore-drama/{filter_id}/"
        elif tid.startswith("tag-"):
            tag = tid[4:]
            base = f"/tag/{quote(tag)}/"
        else:
            base = f"/explore-drama/{tid}/"

        path = base if pg == "1" else base + f"page/{pg}/"

        flat = self._extract_nuxt(self._request(path))
        vods = self._add_vods(flat)

        total = 0
        pagecount = 1
        for item in flat:
            if isinstance(item, dict) and "total" in item:
                t = self._r(flat, item["total"])
                if isinstance(t, int) and t > 0:
                    total = t
                    pagecount = max(1, (t + 19) // 20)
                break

        return {"list": vods, "page": int(pg) if pg.isdigit() else 1,
                "pagecount": pagecount, "limit": 20, "total": total}

    def detailContent(self, ids):
        vid = ids[0].strip().split("||||")[0]
        flat = self._extract_nuxt(self._request(f"/drama-detail/{vid}/"))
        name = self._str(flat, self._key(flat, "title"))
        cover = self._str(flat, self._key(flat, "cover"))
        desc = self._str(flat, self._key(flat, "description"))
        remark = self._str(flat, self._key(flat, "serialize_status_text"))
        ep_count = self._int(flat, "episode_count")
        if cover and not cover.startswith("data:") and \
                any(h in cover for h in MEDIA_HOSTS):
            cover = self.decrypt_pic(cover)
        episodes_info = []
        try:
            p_flat = self._extract_nuxt(self._request(f"/drama/video/{vid}/"))
            for item in p_flat:
                if isinstance(item, dict) and "episodeAll" in item:
                    ea = self._r1(p_flat, item["episodeAll"])
                    if isinstance(ea, list):
                        for i, ep_ref in enumerate(ea):
                            ep = self._r1(p_flat, ep_ref)
                            if isinstance(ep, dict):
                                title = self._str(p_flat, ep.get("episode_title", ""))
                                url = self._str(p_flat, ep.get("video_url", "")) if isinstance(ep.get("video_url", ""), str) else self._str(p_flat, self._r1(p_flat, ep.get("video_url", "")))
                                label = title or f"第{i+1}集"
                                episodes_info.append(f"{label}${url}" if url else f"{label}$")
                    break
        except Exception:
            pass
        play_url = "#".join(episodes_info) if episodes_info else self._str(flat, self._key(flat, "video_url"))
        return {"list": [{"vod_id": vid, "vod_name": name, "vod_pic": cover,
                          "vod_content": desc[:200], "vod_actor": "", "vod_year": "",
                          "vod_area": "", "vod_lang": "", "vod_type": "",
                          "vod_play_from": "热浪短剧", "vod_play_url": play_url,
                          "vod_remarks": remark}]}

    def _key(self, flat, key):
        for item in flat:
            if isinstance(item, dict) and key in item:
                return item[key]
        return ""

    def _int(self, flat, key):
        v = self._key(flat, key)
        if isinstance(v, int):
            return v
        v = self._r(flat, v)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return 0

    def playerContent(self, flag, id, vipFlags):
        url = id.split("$")[-1] if "$" in id else id
        if not url:
            return {"parse": 1, "url": "", "header": {}}
        p = urlparse(url)
        return {"parse": 0, "url": url,
                "header": {"User-Agent": UA, "Referer": p.scheme + "://" + p.netloc + "/"}}

    def searchContent(self, key, quick, pg="1"):
        pg = str(pg) if pg else "1"
        p = quote(key)
        path = f"/search-drama/{p}/" if pg == "1" else f"/search-drama/{p}/page/{pg}/"
        flat = self._extract_nuxt(self._request(path))
        vods = self._add_vods(flat)
        return {"list": vods, "page": int(pg) if pg.isdigit() else 1,
                "pagecount": 1, "limit": len(vods), "total": len(vods)}

    # ---- 图片解密 ----
    def _download_bytes(self, url):
        try:
            r = requests.get(url, timeout=15,
                             headers={"User-Agent": UA, "Referer": self.base_url + "/"})
            if r.status_code == 200:
                return r.content
        except Exception:
            pass
        return None

    def _pad16(self, data):
        if len(data) == 16:
            return data
        out = bytearray(16)
        out[:min(len(data), 16)] = data[:min(len(data), 16)]
        return bytes(out)

    def _aes_decrypt(self, data, key, iv):
        try:
            from Crypto.Cipher import AES
            pt = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
            return pt[:-pt[-1]]
        except ImportError:
            pass
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            pt = dec.update(data) + dec.finalize()
            return pt[:-pt[-1]]
        except ImportError:
            pass
        try:
            import subprocess
            r = subprocess.run(["openssl", "enc", "-d", "-aes-128-cbc",
                                "-K", key.hex(), "-iv", iv.hex()],
                               input=data, capture_output=True)
            if r.returncode == 0:
                pt = r.stdout
                return pt[:-pt[-1]]
        except Exception:
            pass
        return b""

    def _mime(self, data):
        if len(data) > 3 and data[0] == 0xFF and data[1] == 0xD8:
            return "jpeg"
        if len(data) > 4 and data[0] == 0x89 and data[1] == ord('P'):
            return "png"
        if len(data) > 6 and data[:6] in (b"GIF87a", b"GIF89a"):
            return "gif"
        return "jpeg"

    def decrypt_pic(self, url):
        if not url or url.startswith("data:"):
            return url
        try:
            enc = self._download_bytes(url)
            if not enc:
                return ""
            if len(enc) > 3 and ((enc[0] == 0xFF and enc[1] == 0xD8) or
                                  (enc[0] == 0x89 and enc[1] == ord('P'))):
                mime = self._mime(enc)
                return f"data:image/{mime};base64,{base64.b64encode(enc).decode()}"
            key = self._pad16(MEDIA_KEY.encode())
            iv = self._pad16(MEDIA_IV.encode())
            dec = self._aes_decrypt(enc, key, iv)
            mime = self._mime(dec)
            return f"data:image/{mime};base64,{base64.b64encode(dec).decode()}"
        except Exception:
            return ""
