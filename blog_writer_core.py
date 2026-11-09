# -*- coding: utf-8 -*-
"""
BlogWriter 纯逻辑核心：命令解析、markdown 生成、请求构造、响应解析。
不依赖 AstrBot，可独立单元测试。
"""

import base64
import json
import mimetypes
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

SHANGHAI_TZ = timezone(timedelta(hours=8))


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)


SESSION_TIMEOUT = timedelta(minutes=30)
MAX_PATH_SUFFIX = 10

COMMANDS = ("动态", "笔记", "足迹", "友链", "相册", "账单", "存账", "记一笔", "查存账", "清存账", "撤回", "撤销", "日程", "生日", "纪念日", "影视", "书籍", "导航", "转载", "提醒", "发布", "取消", "状态", "帮助")

BILL_CATEGORIES = ["餐饮", "交通", "住房", "工资", "居家生活", "交流通讯", "食品酒水", "职业收入", "人情收礼", "还款", "休闲娱乐", "游戏", "医疗健康", "宠物", "其他"]
BILL_ACCOUNTS = ["微信", "支付宝", "银行卡", "现金", "其他"]
SCHEDULE_PRIORITIES = ["none", "low", "medium", "high"]

# ---------- 命令解析 ----------

Parsed = Tuple[Optional[str], List[str], str]


def parse_message(text: str) -> Parsed:
    """解析用户消息。返回 (命令名或 None, 参数列表, 原始正文)。"""
    text = (text or "").strip()
    if not text:
        return None, [], text
    if text.startswith("/"):
        text = text[1:].strip()
    parts = re.split(r"\s+", text)
    head = parts[0].lstrip("/")
    if head in COMMANDS:
        return head, parts[1:], text
    return None, [], text


def parse_dynamic(args: List[str]) -> Tuple[Optional[str], List[str]]:
    """/动态 内容 [#标签...] → (内容, 自定义标签列表)；内容为空返回 (None, [])。"""
    content = " ".join(args).strip()
    if not content:
        return None, []
    clean, tags = extract_tags(content)
    return (clean or None), tags


def parse_note(args: List[str], default_dir: str) -> Tuple[str, str]:
    """/笔记 [分类] 标题 → (分类, 标题)。一个参数时分类用默认。"""
    if len(args) >= 2:
        return args[0].strip(), " ".join(args[1:]).strip()
    if len(args) == 1:
        return default_dir, args[0].strip()
    return default_dir, ""


def parse_place(args: List[str]) -> Tuple[str, str, str, List[str]]:
    """/足迹 省 地点 体验 [#标签...] → (省, 地点, 体验, 自定义标签)。"""
    if len(args) == 0:
        return "", "", "", []
    if len(args) == 1:
        return "", args[0].strip(), "", []
    if len(args) == 2:
        return args[0].strip(), args[1].strip(), "", []
    province, city = args[0].strip(), args[1].strip()
    experience, tags = extract_tags(" ".join(args[2:]).strip())
    return province, city, experience, tags


def parse_album(args: List[str]) -> str:
    """/相册 相册名 → 相册名（args 拼接、去空白）。名字为空返回空串。"""
    return " ".join(a.strip() for a in args if a.strip()).strip()


def parse_album_frontmatter(md: str) -> Tuple[str, str]:
    """从相册 md 文本提取 (title, imgbedFolder)。行级正则解析，容错（引号可带可不带）。

    用于「按 title 判断相册是否存在」：博客相册文件名与 title 不一定相同（如
    xiangce1.md 的 title 是「测试相册」），必须读内容才能对齐。
    """
    title, folder = "", ""
    for line in (md or "").splitlines():
        s = line.strip()
        m = re.match(r"^title\s*:\s*(.*)$", s)
        if m:
            title = m.group(1).strip().strip("\"'")
        m2 = re.match(r"^imgbedFolder\s*:\s*(.*)$", s)
        if m2:
            folder = m2.group(1).strip().strip("\"'")
    return title, folder


def extract_tags(text: str) -> Tuple[str, List[str]]:
    """从文本中提取 #标签 并移除。返回 (清理后的文本, 标签列表，保持出现顺序去重)。"""
    if not text:
        return "", []
    pattern = re.compile(r"#([^\s#]+)")
    tags = []
    seen = set()
    for m in pattern.finditer(text):
        tag = m.group(1).strip()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    clean = pattern.sub("", text)
    # 清理因移除标签产生的多余空白与行内空白
    lines = [re.sub(r"\s{2,}", " ", ln).strip() for ln in clean.split("\n")]
    clean = "\n".join(ln for ln in lines if ln)
    return clean, tags


# ---------- 文件名与 id ----------

def gen_moment_id(now: datetime = None) -> str:
    now = now or now_shanghai()
    return "ext-" + str(int(now.timestamp() * 1000))


def format_moment_published(now: datetime = None) -> str:
    now = now or now_shanghai()
    return now.strftime("%Y-%m-%d %H:%M:%S")


def moment_filename(day: datetime) -> str:
    return day.strftime("%Y-%m-%d")


def note_filename(day: datetime) -> str:
    # 对齐现有数据：2026年6月1日（无补零）
    return "{}年{}月{}日".format(day.year, day.month, day.day)


def place_filename(day: datetime) -> str:
    return day.strftime("%Y-%m-%d")


def with_suffix(name: str, ext: str, index: int) -> str:
    """冲突后缀：xxx、xxx-1、xxx-2 ..."""
    if index == 0:
        return name + ext
    return "{}-{}{}".format(name, index, ext)


# ---------- markdown 生成 ----------

def _dump_yaml(
    data: Dict[str, Any],
    quote_all: bool = False,
    quote_keys: Optional[set] = None,
    inline_keys: Optional[set] = None,
) -> str:
    """生成 YAML frontmatter（仅支持本项目用到的简单类型）。

    - quote_all=True：所有字符串值强制双引号（date/datetime 形态除外），
      对齐博客 bills/schedules/places 最新文件风格（PagesCMS 生成格式）。
    - quote_keys：仅指定 key 强制双引号（quote_all 的按 key 版本）。
    - inline_keys：指定 key 的非空列表输出行内数组（如 tags: ["a", "b"]）。
    """
    quote_keys = quote_keys or set()
    inline_keys = inline_keys or set()

    def _quoted(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return '"{}"'.format(escaped)

    def _need_quote(key: str) -> bool:
        return quote_all or key in quote_keys

    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            if not value:
                lines.append("{}: []".format(key))
            elif key in inline_keys:
                items = []
                for item in value:
                    s = str(item)
                    items.append(_quoted(s) if _need_quote(key) else _yaml_str(s))
                lines.append("{}: [{}]".format(key, ", ".join(items)))
            else:
                lines.append("{}:".format(key))
                for item in value:
                    s = str(item)
                    rendered = _quoted(s) if _need_quote(key) else _yaml_str(s)
                    lines.append("  - {}".format(rendered))
        elif isinstance(value, bool):
            lines.append("{}: {}".format(key, "true" if value else "false"))
        elif isinstance(value, (int, float)):
            lines.append("{}: {}".format(key, value))
        elif isinstance(value, str):
            if _is_datetime_str(value):
                # date/datetime 形态一律不加引号（对齐现有数据：2024-10-02 14:19:00 / 2026-08-23）
                lines.append("{}: {}".format(key, value))
            elif _need_quote(key):
                lines.append("{}: {}".format(key, _quoted(value)))
            else:
                lines.append("{}: {}".format(key, _yaml_str(value)))
        else:
            lines.append("{}: {}".format(key, value))
    lines.append("---")
    return "\n".join(lines)


def _is_datetime_str(value: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?$", value.strip()))


def _is_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value.strip()))


def _yaml_str(value: str) -> str:
    value = value.strip()
    if not value:
        return '""'
    # 纯数字字符串（如 "2026"）必须加引号，否则 YAML 解析成 int 导致 zod string 校验失败
    if re.match(r"^-?\d+$", value):
        return '"{}"'.format(value)
    if _is_datetime_str(value):
        return value
    if _is_url(value):
        # URL 可裸写（对齐现有数据风格，如 - https://img.tsh520.cn/file/places/xxx.jpg）
        return value
    if re.search(r"[:#\"'\[\]\{\},&*!|>%@`]|\s|^[-?]", value) or value in ("true", "false", "null", "~"):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return '"{}"'.format(escaped)
    return value


def build_moment_md(
    content: str,
    image_urls: List[str],
    tags: List[str],
    now: datetime = None,
) -> str:
    """对齐现有 moments 格式：图片在 frontmatter 的 images 数组，正文只放文字。

    2026-08-13 起博客不再按条写 author/avatar（content.config.ts 已提供 schema 默认值，
    全部旧文件已清理），故这里不再生成这两个字段。
    """
    now = now or now_shanghai()
    fm = {
        "published": format_moment_published(now),
        "tags": tags,
    }
    if image_urls:
        fm["images"] = list(image_urls)
    return _dump_yaml(fm) + "\n\n" + content.strip() + "\n"


def build_note_md(name: str, content: str, image_urls: List[str], day: datetime = None) -> str:
    """对齐最新 notebooks 格式（2026-09-27）：图片进 frontmatter images 数组，正文只留文字，对齐 moments。"""
    day = day or now_shanghai()
    fm: Dict[str, Any] = {"date": day.strftime("%Y-%m-%d"), "name": name}
    if image_urls:
        fm["images"] = list(image_urls)
    body = content.strip()
    return _dump_yaml(fm) + "\n\n" + body + "\n"


def build_notebook_index_json(name: str) -> str:
    """新建笔记本时生成 _index.json（博客书架/归档页靠它识别笔记本，缺了整个文件夹不可见）。
    对齐现有文件风格：tab 缩进、中文字符不转义；封面留空由博客显示默认 emoji，用户可后续在 CMS 补。"""
    return json.dumps({"name": name}, ensure_ascii=False, indent="\t") + "\n"


def build_place_md(
    province: str,
    city: str,
    experience: str,
    photos: List[str],
    lat: float,
    lng: float,
    tags: List[str],
    day: datetime = None,
) -> str:
    """对齐博客最新足迹格式（2026-08-22 参照 src/content/life/places/）：
    新增 description 固定句式、不再写 visitCount（schema 默认 1）、
    字符串带引号、tags 行内数组、photos 多行带引号。
    """
    day = day or now_shanghai()
    fm: Dict[str, Any] = {
        "description": "记录在{}{}的足迹。".format(province, city),
        "province": province,
        "city": city,
    }
    if experience:
        fm["experience"] = experience
    fm["date"] = day.strftime("%Y-%m-%d")
    fm["lat"] = round(lat, 6)
    fm["lng"] = round(lng, 6)
    fm["tags"] = tags
    if photos:
        fm["photos"] = list(photos)
    return _dump_yaml(fm, quote_all=True, inline_keys={"tags"}) + "\n\n\n"


def build_album_md(title: str, folder: str, day: datetime = None) -> str:
    """对齐现有相册格式（2026-08-13 图床化惯例 + subtitle）：
    title/subtitle/date + imgbedFolder（带引号，对齐现有文件如 2026-spring.md）。
    照片不进 md：博客详情页运行时从图床目录动态拉图。
    """
    day = day or now_shanghai()
    fm = {
        "title": title,
        "subtitle": "记录{}".format(title),
        "date": day.strftime("%Y-%m-%d"),
        "imgbedFolder": folder,
    }
    return _dump_yaml(fm, quote_keys={"imgbedFolder"}) + "\n\n\n"


def _image_alt(url: str) -> str:
    return url.rsplit("/", 1)[-1][:40]


# ---------- GitHub 路径 ----------

def github_base(repo: str, path: str, branch: str) -> str:
    return "https://api.github.com/repos/{}/contents/{}?ref={}".format(repo, _quote_path(path), branch)


def github_put_url(repo: str, path: str) -> str:
    return "https://api.github.com/repos/{}/contents/{}".format(repo, _quote_path(path))


def _quote_path(path: str) -> str:
    import urllib.parse

    return urllib.parse.quote(path)


def build_github_put_body(message: str, content_bytes: bytes, branch: str) -> str:
    return json.dumps(
        {
            "message": message,
            "content": base64.b64encode(content_bytes).decode("ascii"),
            "branch": branch,
        }
    )


def parse_github_put_response(status: int, body: str) -> Tuple[bool, str]:
    """返回 (成功, 错误信息)。status 201/200 → 成功。"""
    if status in (200, 201):
        return True, ""
    if status == 409 or status == 422:
        return False, "CONFLICT"
    try:
        data = json.loads(body)
        msg = data.get("message", body[:200])
    except (ValueError, AttributeError):
        msg = body[:200]
    return False, msg


def github_ref_url(repo: str, branch: str) -> str:
    return "https://api.github.com/repos/{}/git/ref/heads/{}".format(repo, _quote_path(branch))


def github_refs_url(repo: str, branch: str) -> str:
    return "https://api.github.com/repos/{}/git/refs/heads/{}".format(repo, _quote_path(branch))


def github_commit_url(repo: str, commit_sha: str) -> str:
    return "https://api.github.com/repos/{}/git/commits/{}".format(repo, _quote_path(commit_sha))


def github_trees_url(repo: str) -> str:
    return "https://api.github.com/repos/{}/git/trees".format(repo)


def github_commits_url(repo: str) -> str:
    return "https://api.github.com/repos/{}/git/commits".format(repo)


def build_github_tree_body(files: List[Tuple[str, str]], base_tree: Optional[str] = None) -> str:
    """构造 POST /git/trees 请求体。files 为 [(path, content_str), ...]"""
    entries = []
    for path, content in files:
        entries.append(
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "content": content,
            }
        )
    data = {"tree": entries}
    if base_tree:
        data["base_tree"] = base_tree
    return json.dumps(data)


def build_github_commit_body(message: str, tree_sha: str, parent_sha: Optional[str] = None) -> str:
    """构造 POST /git/commits 请求体。"""
    data = {
        "message": message,
        "tree": tree_sha,
        "parents": [parent_sha] if parent_sha else [],
    }
    return json.dumps(data)


def build_github_ref_update_body(commit_sha: str, force: bool = False) -> str:
    """构造 PATCH /git/refs/heads/<branch> 请求体。"""
    return json.dumps({"sha": commit_sha, "force": force})


def build_github_delete_tree_body(paths: List[str], base_tree: Optional[str] = None) -> str:
    """构造 POST /git/trees 请求体用于删除文件。
    GitHub Git Data API 规范：设置 sha=None (JSON 序列化为 null) 通知 Git 从 base_tree 中删除该文件。
    """
    entries = []
    for path in paths:
        entries.append(
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": None,
            }
        )
    data = {"tree": entries}
    if base_tree:
        data["base_tree"] = base_tree
    return json.dumps(data)



# ---------- 图床 ----------

_MIME_MAP = {
    "webp": "image/webp",
    "heic": "image/heic",
    "heif": "image/heif",
    "ico": "image/x-icon",
    "svg": "image/svg+xml",
    "m4v": "video/x-m4v",
    "mov": "video/quicktime",
}


def _mime_for_filename(name: str) -> str:
    ext = (name.rsplit(".", 1)[-1].lower() if "." in name else "")
    if ext in _MIME_MAP:
        return _MIME_MAP[ext]
    guessed, _ = mimetypes.guess_type(name)
    if guessed and (guessed.startswith("image/") or guessed.startswith("video/")):
        return guessed
    return "image/jpeg"


def build_imgbed_upload(url: str, filename: str, data: bytes) -> Dict[str, Any]:
    """构造 multipart 上传请求（手写 boundary，不依赖 requests）。"""
    boundary = "----BlogWriterBoundary" + str(int(time.time() * 1000))
    lines = []
    lines.append("--" + boundary)
    lines.append('Content-Disposition: form-data; name="file"; filename="{}"'.format(filename))
    lines.append("Content-Type: {}".format(_mime_for_filename(filename)))
    lines.append("")
    body = ("\r\n".join(lines)).encode("utf-8") + b"\r\n" + data + b"\r\n"
    body += ("--" + boundary + "--\r\n").encode("utf-8")
    return {
        "url": url,
        "headers": {"Content-Type": "multipart/form-data; boundary=" + boundary},
        "body": body,
    }


def upload_url_with_return_format(url: str) -> str:
    """在 /upload 地址上追加 returnFormat=full，让服务端直接返回完整链接。"""
    url = (url or "").strip()
    sep = "&" if "?" in url else "?"
    return url + sep + "returnFormat=full"


def build_upload_url(url: str, folder: str = "") -> str:
    """构造上传地址：追加 returnFormat=full 与 uploadFolder（已存在的参数不重复追加）。"""
    import urllib.parse

    url = (url or "").strip()
    params = []
    if not re.search(r"[?&]returnFormat=", url):
        params.append("returnFormat=full")
    folder = (folder or "").strip().strip("/")
    if folder and not re.search(r"[?&]uploadFolder=", url):
        # 斜杠不编码，与官方文档示例 uploadFolder=img/test 一致
        params.append("uploadFolder=" + urllib.parse.quote(folder, safe="/"))
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + "&".join(params)
    return url


def upload_base_host(url: str) -> str:
    """从上传地址提取主机名，用于把 /file/xxx 拼成完整链接。"""
    import urllib.parse

    return urllib.parse.urlparse(url).netloc


def parse_imgbed_response(status: int, body: str, base_host: str = "") -> Tuple[bool, str]:
    """解析图床上传响应。返回 (成功, 图片 URL 或错误信息)。

    官方文档（src/api/upload.md）：成功响应为数组，如
    [{"src": "/file/abc123_image.jpg", "publicUrl": "https://img.example.com/..."}]
    """
    if status >= 400:
        return False, "图床返回 HTTP {}".format(status)
    try:
        data = json.loads(body)
    except ValueError:
        return False, "图床响应不是 JSON：{}".format(body[:120])
    # 数组格式（新版）
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            src = str(item.get("src") or item.get("publicUrl") or "").strip()
            if src:
                if src.startswith("http"):
                    return True, src
                if src.startswith("/") and base_host:
                    return True, "https://{}{}".format(base_host, src)
                if base_host:
                    return True, "https://{}/{}".format(base_host, src.lstrip("/"))
                return True, src
    # 兼容旧格式 {code, data:{url}}
    if isinstance(data, dict):
        code = data.get("code")
        if code is not None and code != 200:
            return False, "图床返回 code={}：{}".format(code, data.get("message", ""))
        d = data.get("data")
        if isinstance(d, str):
            return True, d
        if isinstance(d, dict):
            url = d.get("url") or d.get("link") or d.get("src")
            if url:
                return True, str(url)
    return False, "图床响应缺少文件地址：{}".format(body[:120])


# ---------- 高德 ----------

def build_amap_url(address: str, key: str) -> str:
    import urllib.parse

    return "https://restapi.amap.com/v3/geocode/geo?address={}&key={}".format(
        urllib.parse.quote(address), urllib.parse.quote(key)
    )


def parse_amap_response(status: int, body: str) -> Tuple[bool, Tuple[float, float]]:
    """返回 (成功, (lat, lng))。"""
    if status >= 400:
        return False, None
    try:
        data = json.loads(body)
    except ValueError:
        return False, None
    if data.get("status") != "1" or data.get("count", "0") == "0":
        return False, None
    geocodes = data.get("geocodes") or []
    if not geocodes:
        return False, None
    location = (geocodes[0].get("location") or "").strip()
    if not location:
        return False, None
    parts = location.split(",")
    if len(parts) != 2:
        return False, None
    try:
        lng, lat = float(parts[0]), float(parts[1])
    except ValueError:
        return False, None
    return True, (lat, lng)


# ---------- TMDB 影视 ----------

TMDB_API_BASE_DEFAULT = "https://api.themoviedb.org"
TMDB_IMAGE_BASE_DEFAULT = "https://image.tmdb.org/t/p"


def build_tmdb_search_url(query: str, api_key: str, api_base: str = "") -> str:
    """构造 TMDB /search/multi 搜索地址（电影+剧集一起搜，中文 zh-CN）。"""
    import urllib.parse

    base = (api_base or TMDB_API_BASE_DEFAULT).strip().rstrip("/")
    return "{}/3/search/multi?api_key={}&query={}&language=zh-CN&include_adult=false".format(
        base, urllib.parse.quote(api_key), urllib.parse.quote(query)
    )


def tmdb_poster_url(poster_path: str, image_base: str = "", size: str = "w500") -> str:
    """海报完整 URL：image_base 默认 https://image.tmdb.org/t/p，尺寸 w500。"""
    base = (image_base or TMDB_IMAGE_BASE_DEFAULT).strip().rstrip("/")
    path = (poster_path or "").strip()
    if not path.startswith("/"):
        path = "/" + path
    return "{}/{}/{}".format(base, size, path.lstrip("/")) if path != "/" else ""


def parse_tmdb_search_response(status: int, body: str) -> Tuple[Optional[Dict], str]:
    """解析 TMDB /search/multi 响应，取第一个 movie/tv 条目（跳过 person 等）。

    返回 (data, err)。data：
      media_type(movie/tv)、title(中文名，无则原名)、original_title、year、
      overview(截断)、vote_average、poster_path
    subcategory 映射：movie→movie、tv→tv。
    """
    if status == 401:
        return None, "TMDB 认证失败（HTTP 401）：请检查 tmdb_api_key"
    if status >= 400:
        return None, "TMDB 返回 HTTP {}".format(status)
    try:
        data = json.loads(body)
    except ValueError:
        return None, "TMDB 响应不是 JSON：{}".format((body or "")[:120])
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        media_type = str(item.get("media_type") or "")
        if media_type not in ("movie", "tv"):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        original = str(item.get("original_title") or item.get("original_name") or "").strip()
        date_str = str(item.get("release_date") or item.get("first_air_date") or "").strip()
        if not title and not original:
            continue
        return {
            "media_type": media_type,
            "title": title or original,
            "original_title": original,
            "year": date_str[:4],
            "overview": str(item.get("overview") or "").strip()[:60],
            "vote_average": item.get("vote_average"),
            "poster_path": str(item.get("poster_path") or "").strip(),
        }, ""
    return None, "TMDB 未找到该片（换个片名试试，或检查网络）"


def parse_media_score(text: str) -> Optional[int]:
    """解析会话内评分行：评分 8 / 打分 9 / 8分 / 十分制 8.5 → int(0-10)。非评分行返回 None。"""
    m = re.match(r"^(?:评分|打分|分数|得分)\s*[:：]?\s*(\d{1,2})(?:\.\d)?\s*(?:分|片|星)?\s*$", (text or "").strip())
    if not m:
        m = re.match(r"^(\d{1,2})(?:\.\d)?\s*分\s*$", (text or "").strip())
    if not m:
        return None
    try:
        score = int(m.group(1))
    except ValueError:
        return None
    return max(0, min(10, score))


def build_bangumi_md(
    title: str,
    image_url: str,
    score: Optional[int],
    tags: List[str],
    comment: str,
    name_cn: str = "",
    subcategory: str = "",
    category: str = "anime",
    now: datetime = None,
) -> str:
    """生成影视/书籍/游戏条目 md，对齐博客 bangumi 格式：
    title/name_cn/category/subcategory/status/image/score/tags/published + 评论正文。
    影视：category=anime + subcategory(movie/tv/anime/documentary)，放 anime/ 子目录（对齐现有数据）；
    游戏：category=game、无 subcategory，放 game/ 子目录（对齐现有 game/ 条目）；
    书籍：category=book、无 subcategory，放 book/ 根目录（手动书籍，区别于 weread 同步的分类子目录）。
    """
    now = now or now_shanghai()
    fm: Dict[str, Any] = {"title": title}
    if name_cn and name_cn != title:
        fm["name_cn"] = name_cn
    fm["category"] = category if category in ("anime", "book", "music", "game", "real") else "anime"
    if subcategory in ("movie", "tv", "anime", "documentary"):
        fm["subcategory"] = subcategory
    fm["status"] = 2  # 看过
    fm["image"] = image_url
    if score is not None:
        fm["score"] = score
    if tags:
        fm["tags"] = tags
    fm["published"] = now.strftime("%Y-%m-%d")
    body = (comment or "").strip()
    return _dump_yaml(fm) + "\n\n" + body + ("\n" if body else "")


_MEDIA_SUBCATEGORY_KEYWORDS = {"电影": "movie", "剧集": "tv", "电视剧": "tv", "电视": "tv", "movie": "movie", "tv": "tv"}


def parse_media_fields(text: str) -> Dict[str, str]:
    """解析影视/书籍会话内的键值对：名称: xxx（改标题）、类型: 电影|剧集（影视 subcategory）。

    返回 dict，可含 title / subcategory 键；非键值对返回空 dict。
    """
    result: Dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        m = re.match(r"^(名称|名字|标题|片名|书名)\s*[:：]\s*(.+)$", line)
        if m:
            result["title"] = m.group(2).strip()
            continue
        m2 = re.match(r"^(类型|分类名)\s*[:：]\s*(.+)$", line)
        if m2:
            token = m2.group(2).strip().lower()
            if token in _MEDIA_SUBCATEGORY_KEYWORDS:
                result["subcategory"] = _MEDIA_SUBCATEGORY_KEYWORDS[token]
    return result


# ---------- 导航网站（daohang）----------

XXAPI_ICO_BASE = "https://v2.xxapi.cn/api/ico"


def build_xxapi_ico_url(site_url: str) -> str:
    """构造 xxapi 图标获取地址（博客 scripts/添加导航/index.js 同款 API，无需 key）。"""
    import urllib.parse

    return "{}/api/ico?url={}".format(
        XXAPI_ICO_BASE.rsplit("/api/", 1)[0], urllib.parse.quote(site_url, safe="")
    )


def parse_xxapi_ico_response(status: int, body: str) -> Tuple[Optional[str], str]:
    """解析 xxapi ico 响应：{"code":200,"data":"<图标直链>"}。返回 (图标 URL, err)。"""
    if status >= 400:
        return None, "图标接口 HTTP {}".format(status)
    try:
        data = json.loads(body)
    except ValueError:
        return None, "图标接口响应异常"
    if data.get("code") == 200 and data.get("data"):
        icon_url = str(data["data"]).strip()
        if icon_url.startswith("http"):
            return icon_url, ""
        return None, "图标接口返回的不是链接"
    return None, "未获取到图标"


def site_host(url: str) -> str:
    """从网址提取域名：https://app.pagescms.org/x → app.pagescms.org"""
    u = (url or "").strip()
    m = re.match(r"^https?://([^/?#]+)", u)
    if m:
        return m.group(1).lower()
    # 无 scheme：取第一个 / 前的部分
    return u.split("/", 1)[0].lower()


def daohang_slug(url: str) -> str:
    """导航文件名：域名点转横线（对齐现有 app-pagescms-org.md / xxapi-cn.md 命名）。"""
    host = site_host(url)
    slug = host.replace(".", "-")
    return clean_filename_part(slug, fallback="site")


def parse_daohang_text(text: str) -> Dict[str, str]:
    """解析导航键值对文本（会话内逐行/多行发送）。

    别名：名称/名字/网站名/name/title→name；分类/类别/category→category（现为「文件夹名」）；
    描述/简介/介绍/description/desc→description。
    注：2026-09-21 博客导航精简为四字段（name/url/icon/description），color 已删除不再解析；
    同日 tags 又回归为可选字段，标签改走 #标签 收集，不经本函数。
    """
    aliases = {
        "name": ["名称", "名字", "网站名称", "网站名", "站点名称", "站点名", "标题", "name", "title"],
        "category": ["分类", "类别", "类目", "category"],
        "description": ["描述", "简介", "介绍", "描述信息", "description", "desc", "descr"],
    }
    result: Dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = re.match(r"^([^:：\s]{1,12})\s*[:：]\s*(.+)$", line)
        if not m:
            continue
        key_raw = m.group(1).strip().lower()
        value = m.group(2).strip()
        for field, keys in aliases.items():
            if key_raw in keys or key_raw in [k.lower() for k in keys]:
                if value:
                    result[field] = value
                break
    return result


def build_daohang_md(
    name: str,
    url: str,
    icon_url: str = "",
    description: str = "",
    body: str = "",
    tags: Optional[List[str]] = None,
) -> str:
    """生成导航条目 md，对齐博客最新格式（2026-09-21 v1.40.3 + tags 回归）：
    条目写 name/url + 可选 icon/description/tags（category 由文件夹决定，
    color/featured/order/image 已从 schema 删除，不再写入）。
    tags 非空时按块状列表输出（与 src/content/daohang 下现有条目一致）：
        tags:
          - API
    """
    fm: Dict[str, Any] = {"name": name, "url": url}
    if icon_url:
        fm["icon"] = icon_url
    if description:
        fm["description"] = description
    clean_tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
    if clean_tags:
        fm["tags"] = clean_tags
    return _dump_yaml(fm) + "\n\n" + (body or "").strip() + ("\n" if (body or "").strip() else "")


# ---------- 微信公众号文章转载 ----------

WX_ARTICLE_HOST = "mp.weixin.qq.com"
WX_IMG_PLACEHOLDER = "{{IMG_%d}}"
# 正文里需要排除的非内容图片（二维码/头像等页脚元素）
_WX_IMG_SKIP_MARKERS = ("qr_code", "qrcode", "jump_author_avatar", "js_pc_weapp_code")


def extract_wx_url(text: str) -> Optional[str]:
    """从消息文本提取微信公众号文章链接；非 mp.weixin.qq.com 的链接返回 None。"""
    m = re.search(r"https?://mp\.weixin\.qq\.com/[^\s]+", text or "")
    if not m:
        return None
    return m.group(0).rstrip(".,;:!?，。；：！？)）]】>\"'")


def _html_unescape(text: str) -> str:
    import html as _html

    return _html.unescape(text or "")


def _strip_tags(fragment: str) -> str:
    """剥掉剩余标签（含 script/style）并解码实体，压缩空白。"""
    s = re.sub(r"<script[\s\S]*?</script>", "", fragment or "", flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", "", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html_unescape(s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    return s.strip()


def _wx_content_img_src(tag: str) -> str:
    """从 <img> 标签提取正文图片 URL（data-src 懒加载优先）；页脚二维码/头像返回空串。"""
    low = (tag or "").lower()
    if any(marker in low for marker in _WX_IMG_SKIP_MARKERS):
        return ""
    src = ""
    m = re.search(r'data-src=["\']([^"\']+)["\']', tag, flags=re.I)
    if m:
        src = m.group(1)
    else:
        m = re.search(r'\ssrc=["\']([^"\']+)["\']', tag, flags=re.I)
        if m:
            src = m.group(1)
    src = _html_unescape(src).strip()
    if not src or src.startswith("data:") or not src.lower().startswith(("http://", "https://")):
        return ""
    # mmbiz 图片统一升级 https（博客混合内容安全）
    if src.startswith("http://mmbiz.qpic.cn"):
        src = "https://" + src[len("http://"):]
    return src


def _img_tag_to_md(tag: str) -> str:
    """<img ...> → Markdown 图片（先落 __WXIMG__ 标记，稍后统一换占位符）。"""
    src = _wx_content_img_src(tag)
    if not src:
        return ""
    return "\n\n[__WXIMG__]({})\n\n".format(src)


def html_to_markdown(fragment: str) -> str:
    """微信正文 HTML 片段 → Markdown。

    实测（2026-09-16）：微信正文段落靠 <section> 分隔（不是 <p>），
    文字在 <span leaf> 里；因此 </section> 必须作为段落边界，否则整篇挤成一行。
    另覆盖 img(data-src 优先)/br/h1-h4/blockquote/li/strong/em/a 与实体解码。
    """
    if not fragment:
        return ""
    s = re.sub(r"<!--[\s\S]*?-->", "", fragment)
    s = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", "", s, flags=re.I)
    s = re.sub(r"<img[^>]*?>", lambda m: _img_tag_to_md(m.group(0)), s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    for level in (1, 2, 3, 4):
        s = re.sub(
            r"<h%d[^>]*>([\s\S]*?)</h%d>" % (level, level),
            lambda m, lv=level: "\n\n" + "#" * lv + " " + _strip_tags(m.group(1)) + "\n\n",
            s,
            flags=re.I,
        )
    s = re.sub(
        r"<blockquote[^>]*>([\s\S]*?)</blockquote>",
        lambda m: "\n\n> " + _strip_tags(m.group(1)).replace("\n", "\n> ") + "\n\n",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"<li[^>]*>([\s\S]*?)</li>",
        lambda m: "- " + _strip_tags(m.group(1)) + "\n",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"<(?:strong|b)[^>]*>([\s\S]*?)</(?:strong|b)>",
        lambda m: ("**" + _strip_tags(m.group(1)) + "**") if _strip_tags(m.group(1)) else "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"<(?:em|i)[^>]*>([\s\S]*?)</(?:em|i)>",
        lambda m: ("*" + _strip_tags(m.group(1)) + "*") if _strip_tags(m.group(1)) else "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>",
        lambda m: "[{}]({})".format(_strip_tags(m.group(2)) or m.group(1), _html_unescape(m.group(1))),
        s,
        flags=re.I,
    )
    # 段落边界：</section> 与 <p> 都算（实测微信主体用 section）
    s = re.sub(r"</section>", "\n\n", s, flags=re.I)
    s = re.sub(r"<section[^>]*>", "", s, flags=re.I)
    s = re.sub(r"<p[^>]*>", "\n\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html_unescape(s)
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in s.split("\n")]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _wx_publish_date(html: str, shanghai_tz) -> str:
    """解析原文发布日期（YYYY-MM-DD）：优先 publish_time 文本，其次 var ct 时间戳（实测页面用 ct）。"""
    m = re.search(r'id="publish_time"[^>]*>\s*([^<]+?)\s*<', html or "")
    if m:
        t = m.group(1).strip()
        m2 = re.search(r"(\d{4})\D{1,2}(\d{1,2})\D{1,2}(\d{1,2})", t)
        if m2:
            return "{}-{:02d}-{:02d}".format(m2.group(1), int(m2.group(2)), int(m2.group(3)))
    m3 = re.search(r'var\s+(?:ct|create_time)\s*=\s*"(\d{9,12})"', html or "")
    if m3:
        try:
            ts = int(m3.group(1))
            return datetime.fromtimestamp(ts, shanghai_tz).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            return ""
    return ""


def extract_wx_article(html: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """解析微信公众号文章页 HTML。

    返回 (data, err)：data = {title, author, publish_date, digest, image_urls, body_md}
    （body_md 中图片为 {{IMG_i}} 占位符，由 assemble_article_body 替换为图床 URL）。
    检测微信「环境异常/完成验证」验证页并返回明确错误。
    """
    if not html:
        return None, "抓取内容为空"
    if ("环境异常" in html) or ("完成验证" in html and "js_content" not in html):
        return None, "微信要求环境验证（服务器 IP 可能被风控拦截），请稍后重试或更换文章"
    m = re.search(r'id="js_content"', html)
    if not m:
        return None, "未找到文章正文（可能不是图文消息，或页面结构已变化）"
    # 正文范围：js_content 起，到工具条/推荐区/脚本前的最近边界为止（实测 <script 边界最靠前）
    tail = html[m.end():]
    end_idx = len(tail)
    for marker in ('<div class="rich_media_tool"', 'id="js_sg_bar"', "rich_media_area_extra", "<script"):
        pos = tail.find(marker)
        if pos != -1 and pos < end_idx:
            end_idx = pos
    content_html = tail[:end_idx]
    gt = content_html.find(">")
    if gt != -1:
        content_html = content_html[gt + 1:]
    content_html = re.sub(r"</div>\s*$", "", content_html.strip(), count=1)

    # 标题：h1#activity-name → og:title → var msg_title
    title = ""
    m_title = re.search(r'id="activity-name"[^>]*>([\s\S]*?)</h1>', html)
    if m_title:
        title = _strip_tags(m_title.group(1))
    if not title:
        m_og = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
        if m_og:
            title = _html_unescape(m_og.group(1)).strip()
    if not title:
        m_var = re.search(r'var\s+msg_title\s*=\s*"([^"]+)"', html)
        if m_var:
            title = _html_unescape(m_var.group(1)).strip()
    if not title:
        return None, "未解析到文章标题"

    # 公众号名：js_name 锚文本 → var nickname
    author = ""
    m_auth = re.search(r'id="js_name"[^>]*>([\s\S]*?)</a>', html)
    if m_auth:
        author = _strip_tags(m_auth.group(1))
    if not author:
        m_var2 = re.search(r'var\s+nickname\s*=\s*(?:htmlDecode\()?"([^"]+)"', html)
        if m_var2:
            author = _html_unescape(m_var2.group(1)).strip()

    digest = ""
    m_desc = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
    if m_desc:
        digest = _html_unescape(m_desc.group(1)).strip()

    image_urls: List[str] = []
    for m_img in re.finditer(r"<img[^>]*?>", content_html, flags=re.I):
        src = _wx_content_img_src(m_img.group(0))
        if src:
            image_urls.append(src)

    body_md = html_to_markdown(content_html)
    img_iter = iter(range(len(image_urls)))

    def _ph(_m):
        return "\n\n{}\n\n".format(WX_IMG_PLACEHOLDER % next(img_iter, 0))

    body_md = re.sub(r"\[__WXIMG__\]\([^)]+\)", _ph, body_md)
    body_md = re.sub(r"\n{3,}", "\n\n", body_md).strip()
    text_only = re.sub(r"\{\{IMG_\d+\}\}", "", body_md).strip()
    if len(text_only) < 10 and not image_urls:
        return None, "正文内容为空或过短（可能不是可直接转载的图文消息）"
    if not digest:
        # 实测：部分文章 description meta 为空 → 用正文首段截取兜底
        digest = re.sub(r"\s+", " ", text_only)[:60]

    data = {
        "title": title,
        "author": author,
        "publish_date": _wx_publish_date(html, SHANGHAI_TZ),
        "digest": digest,
        "image_urls": image_urls,
        "body_md": body_md,
    }
    return data, ""


def assemble_article_body(body_md: str, uploaded_urls: List[str]) -> str:
    """把正文中的 {{IMG_i}} 占位符按序替换为图床 URL；未解析到的占位符直接清除。"""
    out = body_md or ""
    for idx, url in enumerate(uploaded_urls or []):
        out = out.replace(WX_IMG_PLACEHOLDER % idx, url)
    out = re.sub(r"\{\{IMG_\d+\}\}", "", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def build_article_md(
    title: str,
    body_md: str,
    image_urls: List[str],
    tags: List[str],
    description: str = "",
    source_link: str = "",
    author: str = "",
    publish_date: str = "",
    now: datetime = None,
) -> str:
    """生成转载文章（posts 集合）markdown。

    对齐博客 posts schema（src/content.config.ts）：title/published/tags/description/
    image/sourceLink；不写已废弃的 category（分类=目录路径）。
    正文开头自动加转载声明引用块（对齐现有转载文惯例）。
    """
    now = now or now_shanghai()
    fm: Dict[str, Any] = {
        "title": title,
        "published": now.strftime("%Y-%m-%d"),
    }
    if description:
        fm["description"] = description
    if image_urls:
        fm["image"] = image_urls[0]
    fm["tags"] = list(tags or [])
    if source_link:
        fm["sourceLink"] = source_link

    if author:
        credit = "> 本文转载自微信公众号「{}」".format(author)
    else:
        credit = "> 本文转载自微信公众号文章"
    if publish_date:
        credit += "（原文发布于 {}）".format(publish_date)
    if source_link:
        credit += "\n> 原文链接：{}".format(source_link)

    body = (body_md or "").strip()
    return _dump_yaml(fm) + "\n\n" + credit + "\n\n" + body + "\n"


# ---------- 友链解析 ----------

FRIEND_KEY_ALIASES = {
    "title": [
        # 中文
        "站点名称", "网站名称", "名称", "名字", "昵称", "站点名", "网站名", "博客名",
        "博客名称", "博主", "博主名", "博主名称", "网站名字", "站点名字", "网站昵称",
        # 英文（Butterfly 等主题格式）
        "name", "title", "blogname", "blog_name", "site_name", "nickname",
    ],
    "desc": [
        # 中文
        "描述", "简介", "站点描述", "网站描述", "介绍", "站点介绍", "网站介绍",
        "一句话介绍", "签名", "标语", "说明", "备注", "博主简介", "博客简介", "描述文字",
        # 英文
        "desc", "descr", "description", "intro", "introduction", "slogan", "about",
    ],
    "siteurl": [
        # 中文
        "链接", "地址", "网址", "站点链接", "网站链接", "站点地址", "网站地址",
        "博客链接", "博客地址", "主页", "主页链接", "域名", "网站", "站点",
        # 英文
        "link", "url", "siteurl", "site_url", "website", "homepage", "blog_url", "href",
    ],
    "imgurl": [
        # 中文
        "头像", "头像链接", "头像地址", "头像图片", "图标", "图标链接", "图片",
        "图片链接", "头像url", "头像图片链接", "头像地址链接",
        # 英文
        "avatar", "imgurl", "img_url", "icon", "logo", "image", "picture", "avatar_url",
    ],
}

_IMAGE_URL_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def parse_friend_text(text: str) -> Dict[str, str]:
    """解析友链键值对文本（兼容多种键名、多种分隔符、乱序、缺字段）。

    支持：
      站点名称: 团子和蛋糕
      站点描述：如果你喜欢那么欢迎来到我的世界！
      站点链接 https://blog.tsh520.cn
    也支持无键名行：纯 URL 行按 链接/头像 自动归类。
    """
    result: Dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip().rstrip("，,")
        if not line:
            continue

        def lookup(key: str) -> Optional[str]:
            kl = key.lower()
            for f, aliases in FRIEND_KEY_ALIASES.items():
                if kl in aliases or kl in [a.lower() for a in aliases]:
                    return f
            return None

        field, value = None, ""
        # 形式 1：key: value / key：value
        m = re.match(r"^([^:\s：]{1,24})\s*[:：]\s*(.+)$", line)
        if m:
            field = lookup(m.group(1).strip())
            value = m.group(2).strip()
        else:
            # 形式 2：key value（单空格分隔，仅当 key 命中别名表时）
            m2 = re.match(r"^([^\s]{1,24})\s+(.+)$", line)
            if m2:
                field = lookup(m2.group(1).strip())
                if field:
                    value = m2.group(2).strip()
        if field and value:
            result[field] = value
            continue
        # 形式 3：未知键名但冒号后是完整 URL —— 按值特征归类（键名别名未收录也能兜住）
        m3 = re.match(r"^[^:\s：]{1,24}\s*[:：]\s*(.+)$", line)
        if m3:
            v3 = m3.group(1).strip()
            if v3.startswith(("http://", "https://")):
                line = v3
        # 无键名行：按内容特征归类
        if line.startswith(("http://", "https://")):
            if any(line.lower().endswith(e) for e in _IMAGE_URL_EXTS):
                result.setdefault("imgurl", line)
            else:
                result.setdefault("siteurl", line)
        elif line.startswith("/"):
            result.setdefault("imgurl", line)
        else:
            result.setdefault("title", line)
    return result


def validate_friend_data(data: Dict[str, str]) -> Tuple[bool, str]:
    """校验友链字段。返回 (是否通过, 缺失字段提示)。"""
    title = (data.get("title") or "").strip()
    siteurl = (data.get("siteurl") or "").strip()
    if not title:
        return False, "缺少「站点名称」"
    if not siteurl:
        return False, "缺少「站点链接」（https:// 开头的地址）"
    if not siteurl.startswith(("http://", "https://")):
        return False, "站点链接必须以 http:// 或 https:// 开头"
    return True, ""


def build_friend_md(
    title: str,
    desc: str,
    siteurl: str,
    imgurl: str,
    tags: List[str],
    weight: int = 0,
    enabled: bool = True,
    added: Optional[str] = None,
) -> str:
    """对齐现有友链文件格式：weight 0、末尾 group 字段（schema enum friend/other，默认 other）。
    字符串不加引号（对齐现有 friends 文件风格）。"""
    if added is None:
        added = now_shanghai().strftime("%Y-%m-%d")
    fm = {
        "title": title,
        "imgurl": imgurl,
        "desc": desc,
        "siteurl": siteurl,
        "tags": tags,
        "weight": weight,
        "enabled": enabled,
        "added": added,
        "group": "other",
    }
    return _dump_yaml(fm) + "\n\n\n"


def clean_filename_part(name: str, fallback: str = "friend") -> str:
    """清洗用于文件名的名称：去掉非法字符与首尾空白。"""
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\s]+', "-", name)
    name = name.strip("-.")
    return name or fallback


def next_friend_index(existing_names: List[str]) -> int:
    """根据现有友链文件名（NN-name.md）计算下一个编号。"""
    max_index = 0
    for name in existing_names or []:
        m = re.match(r"^(\d+)", str(name))
        if m:
            max_index = max(max_index, int(m.group(1)))
    return max_index + 1


# ---------- 向导常量 ----------

WIZARD_CANCEL_KEYWORDS = ("取消", "cancel", "退出", "exit", "q")
WIZARD_SKIP_KEYWORDS = ("跳过", "skip", "无", "不要", "none")
WIZARD_NEW_KEYWORDS = ("新建", "new", "创建")

MEDIA_WIZARD_CATEGORIES = [
    ("电影", "movie"),
    ("电视剧", "tv"),
    ("动漫", "anime"),
    ("纪录片", "documentary"),
    ("游戏", "game"),
]
# 信用账户（作为普通账户选项供向导选择；账户只是记账口径，不再关联负债类型）
BILL_WIZARD_CREDIT_ACCOUNTS = ["花呗", "白条", "信用卡", "京东白条", "抖音月付", "微信分付"]


def is_wizard_cancel(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in WIZARD_CANCEL_KEYWORDS


def is_wizard_skip(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in WIZARD_SKIP_KEYWORDS


def is_wizard_new(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in WIZARD_NEW_KEYWORDS


def parse_choice(text: str, n: int) -> Optional[int]:
    """解析数字选择 1..n，支持 '1' / '1.' / '1、' / '1。'。非数字返回 None。"""
    t = (text or "").strip()
    if not t:
        return None
    m = re.match(r"^(\d+)\s*[.、。]?\s*$", t)
    if not m:
        m2 = re.match(r"^(\d+)\b", t)
        if not m2:
            return None
        m = m2
    try:
        v = int(m.group(1))
    except ValueError:
        return None
    if 1 <= v <= n:
        return v
    return None


def format_choices(title: str, items: List[str], extra: Optional[List[str]] = None, with_skip_cancel: bool = True) -> str:
    """生成编号选择文本。items 为选项列表，extra 追加到末尾（如 ['新建笔记本']）。"""
    lines = [title]
    for idx, item in enumerate(items, 1):
        lines.append(f"{idx}. {item}")
    if extra:
        start = len(items) + 1
        for j, e in enumerate(extra):
            lines.append(f"{start + j}. {e}")
    if with_skip_cancel:
        lines.append("")
        lines.append("回复数字选择，回复“取消”退出" + ("、“跳过”跳过" if with_skip_cancel else ""))
    return "\n".join(lines)


# ---------- 会话 ----------

class Session:
    def __init__(
        self,
        kind: str,
        meta: Dict[str, Any],
        created_at: datetime = None,
    ):
        self.kind = kind  # moment | note | place | friend | album
        self.meta = meta
        self.text_parts: List[str] = []
        # 元素为 (来源引用, 图片字节)。图片在收到消息时立即读取，避免临时文件被清理。
        self.images: List[Tuple[str, bytes]] = []
        self.wizard: Optional[Dict[str, Any]] = None  # 向导状态 {step, data}
        self.created_at = created_at or now_shanghai()
        self.last_active = self.created_at

    def touch(self, now: datetime = None) -> None:
        self.last_active = now or now_shanghai()

    def expired(self, now: datetime = None, timeout: timedelta = None) -> bool:
        now = now or now_shanghai()
        return now - self.last_active > (timeout or SESSION_TIMEOUT)

    def add_text(self, text: str) -> None:
        self.text_parts.append(text)

    def add_image(self, ref: str, data: bytes) -> None:
        self.images.append((ref, data))

    def full_text(self) -> str:
        return "\n".join(p.strip() for p in self.text_parts if p.strip())


# ---------- 账单 / 日程 ----------

# 分类关键词映射（用于白名单分类匹配）
_BILL_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "餐饮": [
        "餐饮", "午餐", "晚餐", "早餐", "早饭", "午饭", "晚饭", "夜宵", "吃饭", "外卖", "食堂", "餐厅", "饮食", "聚餐",
        "肯德基", "麦当劳", "汉堡", "套餐", "夜市", "火锅", "烧烤", "小吃", "炒面", "炒饭", "拉面", "米线", "螺蛳粉",
        "黄焖鸡", "快餐", "便当", "料理", "披萨", "牛肉面", "麻辣烫", "堂食", "下馆子", "烤肉", "自助餐",
    ],
    "交通": [
        "交通", "打车", "地铁", "公交", "出行", "机票", "火车", "高铁", "出租", "滴滴", "通勤", "车费", "路费",
        "加油", "停车", "洗车", "修车", "过路费", "高速费", "共享单车", "单车", "电动车", "换零件", "保养",
    ],
    "住房": [
        "住房", "房租", "房贷", "物业", "水电", "房费", "电费", "水费", "燃气费", "暖气费",
    ],
    "工资": [
        "工资",
    ],
    "居家生活": [
        "居家", "家用", "日用", "家居", "生活费", "居家生活",
        "剪头发", "理发", "洗护", "洗发水", "沐浴露", "洗衣液", "抽纸", "洗洁精", "卫生纸",
        "衣服", "裤子", "鞋子", "短袖", "T恤", "外套", "内衣", "袜子", "服饰",
        "护肤", "洗面奶", "防晒霜", "化妆品", "屈臣氏", "面霜", "面膜",
        "充电宝", "数据线", "电池", "排插", "五金", "工具",
        "书籍", "买书", "图书", "教材", "书本",
    ],
    "交流通讯": [
        "交流", "通讯", "话费", "流量", "宽带", "手机费", "充值卡",
    ],
    "食品酒水": [
        "食品", "酒水", "零食", "饮料", "酒", "水果", "买菜", "超市",
        "绿茶", "红茶", "乌龙茶", "奶茶", "咖啡", "果汁", "可乐", "雪碧", "矿泉水", "苏打水", "冰红茶",
        "雪糕", "冰淇淋", "冰棒", "冰棍",
        "酸奶", "牛奶", "面包", "吐司", "蛋糕", "饼干", "巧克力", "薯片", "坚果", "糖果",
        "香烟", "包烟", "买烟", "抽烟", "卷烟", "烟",
        "啤酒", "白酒", "红酒", "洋酒",
        "西瓜", "草莓", "车厘子", "苹果", "香蕉", "葡萄", "水果店", "便利店",
    ],
    "职业收入": [
        "职业收入", "奖金", "绩效", "提成", "收入", "兼职", "稿费", "劳务费", "分红",
    ],
    "人情收礼": [
        "人情", "收礼", "红包", "礼金", "请客", "随礼", "送礼", "份子钱", "贺礼",
    ],
    "还款": [
        "还款", "还信用卡", "还花呗", "还白条",
    ],
    "休闲娱乐": [
        "娱乐", "休闲", "电影", "电影票", "看电影", "影院", "游乐园", "门票", "KTV", "密室", "剧本杀", "展览", "演唱会",
    ],
    "游戏": [
        "游戏", "Steam", "网吧", "上网", "手游", "充值", "点券", "皮肤", "PlayStation", "PS5", "Switch", "Xbox", "任天堂",
    ],
    "医疗健康": [
        "医疗", "医药", "买药", "看病", "挂号", "医院", "诊所", "药房", "药店", "感冒药", "退烧药", "消炎药", "止痛药", "体检", "就医",
    ],
    "宠物": [
        "宠物", "猫粮", "狗粮", "猫咪", "小狗", "猫罐头", "狗罐头", "猫砂", "宠物医院", "猫条", "宠物店", "驱虫",
    ],
    "其他": [],
}

# 账单类型关键词
_BILL_EXPENSE_KEYWORDS = ["花了", "支出", "花费", "付款", "消费", "支付", "扣款", "买"]
_BILL_INCOME_KEYWORDS = ["工资", "收入", "到账", "收款", "入账", "奖金", "发工资"]
# 还款本质是资金流出，记为普通支出（对齐博客去负债后的模型：type 仅 expense/income）
_BILL_REPAY_KEYWORDS = ["还款", "偿还", "还了", "已还"]
# 借款/欠款类（负债快照）已不再支持，命中即报错
_BILL_BORROW_KEYWORDS = ["借款", "欠款", "欠了", "负债"]
# 账户别名（不在白名单但博客已有数据使用，如 account: 花呗）
_BILL_ACCOUNT_ALIASES = ["花呗", "白条", "信用卡"]
# 显式类型前缀（/账单 支出|收入|还款 <内容>）
_BILL_TYPE_PREFIX = {
    "支出": "expense",
    "消费": "expense",
    "花费": "expense",
    "收入": "income",
    "还款": "expense",
}


def _parse_bill_date(text: str, now: datetime) -> datetime:
    """从文本中提取日期关键词，返回对应的 datetime（00:00:00）。"""
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    s = text or ""
    # 1. 相对天数
    if "大前天" in s:
        return base - timedelta(days=3)
    if "前天" in s:
        return base - timedelta(days=2)
    if "昨天" in s:
        return base - timedelta(days=1)
    if "今天" in s:
        return base
    if "后天" in s:
        return base + timedelta(days=2)
    if "明天" in s:
        return base + timedelta(days=1)

    # 2. 完整年月日：2026-10-08 / 2026.10.08 / 2026/10/08 / 2026年10月8日
    m_full = re.search(r"(\d{4})[年.\-/](\d{1,2})[月.\-/](\d{1,2})[日号]?", s)
    if m_full:
        try:
            return datetime(int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3)))
        except ValueError:
            pass

    # 3. 月日：10月8日 / 10月8号 / 10月8
    m_md = re.search(r"(\d{1,2})月(\d{1,2})[日号]?", s)
    if m_md:
        try:
            return datetime(now.year, int(m_md.group(1)), int(m_md.group(2)))
        except ValueError:
            pass

    # 4. 开头简写月日（避免误判 10.8元 为日期，必须位于行首且后跟空格或结束）：10-08 / 10.8 / 10/8
    m_short = re.search(r"^\s*(\d{1,2})[.\-/](\d{1,2})(?:\s+|$)", s)
    if m_short:
        try:
            m = int(m_short.group(1))
            d = int(m_short.group(2))
            if 1 <= m <= 12 and 1 <= d <= 31:
                return datetime(now.year, m, d)
        except ValueError:
            pass

    # 5. 星期/周/礼拜
    m_week = re.search(r"(上)?(?:周|星期|礼拜)([一二三四五六日天])", s)
    if m_week:
        is_last = bool(m_week.group(1))
        w_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        target_weekday = w_map.get(m_week.group(2))
        if target_weekday is not None:
            cur_weekday = base.weekday()
            diff = cur_weekday - target_weekday
            if diff <= 0:
                diff += 7
            if is_last:
                diff += 7
            return base - timedelta(days=diff)

    return base


def _strip_bill_date(text: str) -> str:
    """去除文本中的日期表达，避免干扰金额提取与标题生成。"""
    t = text or ""
    t = re.sub(r"\d{4}[年.\-/]\d{1,2}[月.\-/]\d{1,2}[日号]?", " ", t)
    t = re.sub(r"\d{1,2}月\d{1,2}[日号]?", " ", t)
    t = re.sub(r"^\s*\d{1,2}[.\-/]\d{1,2}(?:\s+|$)", " ", t)
    t = re.sub(r"(大前天|前天|昨天|今天|后天|明天)", " ", t)
    t = re.sub(r"(?:上)?(?:周|星期|礼拜)[一二三四五六日天]", " ", t)
    return t


# 时间表达：14:30 / 14：30 / 下午3点 / 3点半 / 12点30分 / 9点
_BILL_TIME_RE = re.compile(
    r"(凌晨|早上|上午|中午|午后|下午|傍晚|晚上|夜里)?\s*(\d{1,2})[点时](?:\s*(\d{1,2})\s*分?|\s*(半))?"
    r"|\s*(\d{1,2})\s*[:：]\s*(\d{2})\s*(?:分)?"
)


def _parse_bill_time(text: str, now: datetime):
    """从文本提取时刻，返回 'HH:mm'；识别不到返回 None（调用方回退当前时刻）"""
    m = _BILL_TIME_RE.search(text or "")
    if not m:
        return None
    try:
        if m.group(5) is not None:
            # 冒号形态 14:30
            hour, minute = int(m.group(5)), int(m.group(6))
        else:
            hour = int(m.group(2))
            if m.group(4) == "半":
                minute = 30
            elif m.group(3) is not None:
                minute = int(m.group(3))
            else:
                minute = 0
            tag = m.group(1) or ""
            if hour < 12 and tag in ("午后", "下午", "傍晚", "晚上", "夜里"):
                hour += 12
            elif hour == 12 and tag in ("凌晨", "早上", "上午"):
                hour = 0
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return "{:02d}:{:02d}".format(hour, minute)


def _detect_bill_category(text: str) -> str:
    # 优先精确命中分类名本身
    for cat in BILL_CATEGORIES:
        if cat in text:
            return cat
    # 再通过关键词映射
    for cat, keywords in _BILL_CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw and kw in text:
                return cat
    # 词尾后缀智能兜底
    clean_words = re.findall(r"[\u4e00-\u9fa5]{2,6}", text)
    for w in clean_words:
        if w.endswith(("茶", "咖", "水", "酒", "汁", "奶", "糕")):
            if w not in ("薪水", "潜水", "试水", "水房", "跳水", "喝茶"):
                return "食品酒水"
        if w.endswith(("面", "粉", "饭", "餐", "肉", "菜", "羹", "粥", "饼")):
            if w not in ("下半场", "开饭", "买菜"):
                return "餐饮"
        if w.endswith(("车", "票")):
            if w not in ("水票", "门票", "发票", "退票", "彩票"):
                return "交通"
        if w.endswith(("药", "剂")):
            if w not in ("农药", "炸药"):
                return "医疗健康"
        if w.endswith(("粮", "罐头", "猫条")):
            if w not in ("粮食", "干粮"):
                return "宠物"
    return "其他"


def _detect_bill_account(text: str) -> str:
    for acc in BILL_ACCOUNTS:
        if acc in text:
            return acc
    # 别名（信用账户：花呗/白条/信用卡），对齐博客现有数据 account: 花呗
    for alias in _BILL_ACCOUNT_ALIASES:
        if alias in text:
            return alias
    return "其他"


def parse_bills_batch(text: str, now=None) -> Tuple[List[Dict], str]:
    """批量解析多条账单（用于一句含多个金额的口语，如“午餐30晚餐45打车12”）。"""
    now = now or now_shanghai()
    raw = (text or "").strip()
    if not raw:
        return [], "内容为空"

    # 去掉日期和时间后检查有效金额数量（若只有1个或0个金额，直接走单条账单解析，避免如 2026-10-08 中的数字被拆成多笔）
    clean_raw = _strip_bill_date(raw)
    clean_raw = _BILL_TIME_RE.sub(" ", clean_raw)
    clean_amounts = list(re.finditer(r"-?\d+(?:\.\d+)?\s*(?:块钱|元钱|块|元|￥)?", clean_raw))
    if len(clean_amounts) <= 1:
        data, err = parse_bill(raw, now)
        return ([data] if data else []), err

    # 检查整体文本头部是否有公共日期定义（如“昨天 午餐30 晚餐45” 或 “2026-10-08 午餐30 晚餐45”）
    global_date = _parse_bill_date(raw, now)
    base_now = now.replace(hour=0, minute=0, second=0, microsecond=0)
    has_global_date = (global_date != base_now)

    # 去掉整体日期，避免日期里的数字在后续拆分时被误当成切片
    content_to_split = _strip_bill_date(raw)

    # 按常见分隔符拆分：， 、 。 ； 换行 以及“和/与/ plus”
    parts = re.split(r"[，。,；;、\n]+", content_to_split)
    # 若只有一段但含多个金额，按金额切分
    expanded: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # 若一段含多个金额，按金额切（每个条目取到该金额结束，最后一个金额取到剩余末尾）
        amounts = list(re.finditer(r"-?\d+(?:\.\d+)?\s*(?:块钱|元钱|块|元|￥)?", p))
        if len(amounts) > 1:
            last = 0
            for idx, m in enumerate(amounts):
                if idx == len(amounts) - 1:
                    seg = p[last:].strip(" ，,。 ")
                else:
                    seg = p[last:m.end()].strip(" ，,。 ")
                if seg:
                    expanded.append(seg)
                last = m.end()
            if len(expanded) <= 1:
                expanded = [p]
        else:
            expanded.append(p)
    # 若拆分后仍只有1段但含多个金额，尝试按“和/与/，”再拆
    if len(expanded) == 1 and len(re.findall(r"-?\d+(?:\.\d+)?\s*(?:块钱|元钱|块|元|￥)?", content_to_split)) > 1:
        # 按金额直接拆全文
        expanded = []
        for m in re.finditer(r"([^，。,；;、\n]*?-?\d+(?:\.\d+)?\s*(?:块钱|元钱|块|元|￥)?[^，。,；;、\n]*)", content_to_split):
            seg = m.group(1).strip(" ，,。")
            if seg:
                expanded.append(seg)
    results: List[Dict] = []
    for seg in expanded:
        seg = seg.strip()
        if not seg:
            continue
        # 必须含金额才算一条账单
        if not re.search(r"-?\d+(?:\.\d+)?\s*(?:块钱|元钱|块|元|￥)?", seg):
            continue
        data, err = parse_bill(seg, now)
        if data:
            # 若单条未显式指定自身日期且整体有公共日期，则继承公共日期
            if has_global_date:
                seg_date = _parse_bill_date(seg, now)
                if seg_date == base_now:
                    data["date"] = global_date
            results.append(data)
    if not results:
        return [], "未识别到账单信息"
    return results, ""


def parse_bill(text: str, now=None) -> Tuple[Optional[Dict], str]:
    """解析账单自然语言。返回 (data, err)，err 为空表示成功。

    data 包含：title, amount, type(expense/income), category, account, date(datetime), time(HH:mm), description

    类型判定（显式优先）：
    1. 首词为类型前缀（支出/消费/花费/收入/还款）+ 空格 → 显式指定
    2. 收入关键词（工资/收入/到账…）→ income
    3. 还款关键词（还款/偿还/还了…）→ expense（分类固定「还款」，金额为负）
    4. 支出关键词或默认 → expense
    5. 借款/欠款/负债 → 报错（负债类型已下线，博客账单仅支持 支出/收入）
    """
    now = now or now_shanghai()
    raw = (text or "").strip()
    if not raw:
        return None, "内容为空"

    # 显式前缀（首词 + 空格）：类型前缀（支出/收入/还款…）或分类前缀（白名单分类名如「餐饮」）
    type_hint = None
    category_hint = None
    first_token = re.split(r"\s+", raw, 1)[0]
    if re.search(r"\s", raw):
        if first_token in _BILL_TYPE_PREFIX:
            type_hint = _BILL_TYPE_PREFIX[first_token]
            # 「还款」前缀：分类固定「还款」，避免落回「其他」
            if first_token == "还款":
                category_hint = "还款"
            raw = re.sub(r"^\S+\s+", "", raw, count=1).strip()
            # 类型前缀后紧跟分类前缀也支持（如「支出 餐饮 午餐30」）
            second_token = re.split(r"\s+", raw, 1)[0]
            if second_token in BILL_CATEGORIES and re.search(r"\s", raw):
                category_hint = second_token
                raw = re.sub(r"^\S+\s+", "", raw, count=1).strip()
        elif first_token in BILL_CATEGORIES:
            category_hint = first_token
            raw = re.sub(r"^\S+\s+", "", raw, count=1).strip()
    if not raw:
        return None, "内容为空"

    # 提取日期与时刻（在金额提取前解析，防止日期与时刻中的数字被误识别为金额）
    date_val = _parse_bill_date(raw, now)
    time_val = _parse_bill_time(raw, now) or now.strftime("%H:%M")

    # 用于金额提取的文本：先剔除日期与时刻，防止 2026-10-08 中的 2026 或 12点 中的 12 被当作金额
    text_for_amt = _strip_bill_date(raw)
    text_for_amt = _BILL_TIME_RE.sub(" ", text_for_amt)

    # 金额提取：优先匹配带货币单位（块钱/元钱/块/元/￥），其次匹配裸数字
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:块钱|元钱|块|元|￥)", text_for_amt)
    if not m:
        m = re.search(r"(-?\d+(?:\.\d+)?)", text_for_amt)
    if not m:
        return None, "未识别到金额"
    try:
        amount_val = float(m.group(1))
    except ValueError:
        return None, "金额解析失败"

    # 类型判断（显式前缀 > 收入 > 还款记支出 > 支出/默认）
    has_income = any(kw in raw for kw in _BILL_INCOME_KEYWORDS)
    has_repay = any(kw in raw for kw in _BILL_REPAY_KEYWORDS)
    has_borrow = any(kw in raw for kw in _BILL_BORROW_KEYWORDS)
    if has_borrow:
        return None, "负债类型已下线（账单仅支持 支出/收入）：借款/欠款不再支持记账，还款会自动记为支出"
    if type_hint:
        type_ = type_hint
    elif has_income:
        type_ = "income"
    else:
        # 还款关键词与无显式关键词时均默认 expense
        type_ = "expense"

    if type_ == "expense":
        amount = -abs(amount_val)
    else:
        amount = abs(amount_val)
    # 保持整数类型
    if isinstance(amount, float) and amount == int(amount):
        amount = int(amount)

    if category_hint:
        # 显式分类前缀优先于关键词检测
        category = category_hint
    elif has_repay and type_ == "expense":
        # 还款统一归入「还款」分类（对齐博客现有补记数据）
        category = "还款"
    else:
        category = _detect_bill_category(raw)
    account = _detect_bill_account(raw)

    # 标题/描述提取：去除已知片段后剩余文本
    cleaned = raw
    # 去除日期词
    cleaned = _strip_bill_date(cleaned)
    # 去除时间词（与 _BILL_TIME_RE 同口径，避免「12点」等混入标题）
    cleaned = _BILL_TIME_RE.sub(" ", cleaned)
    # 去除账户及账户别名
    for acc in list(BILL_ACCOUNTS) + list(_BILL_ACCOUNT_ALIASES):
        cleaned = cleaned.replace(acc, "")
    # 去除金额（含可选单位）
    cleaned = re.sub(r"(-?\d+(?:\.\d+)?)\s*(?:块钱|元钱|块|元|￥)?", "", cleaned)
    cleaned = cleaned.replace("块钱", "").replace("元钱", "")
    # 去除类型动词（保留类别名词如 工资 餐饮 午餐 等，避免误删标题）
    for kw in ["花了", "支出", "花费", "付款", "消费", "支付", "扣款", "到账", "入账", "收款"]:
        cleaned = cleaned.replace(kw, "")
    # 去除补记词
    for kw in ["补记", "补发", "昨天的", "今天的", "前天的", "大前天的"]:
        cleaned = cleaned.replace(kw, "")
    cleaned = re.sub(r"^\s*补\s*", "", cleaned)
    # 单独的 "发" 常见于 "发工资"
    cleaned = re.sub(r"\b发\b", "", cleaned)
    # 若包含独立“账单”字眼且有其他内容，清理“账单”
    if len(cleaned.replace("账单", "").strip()) >= 2:
        cleaned = cleaned.replace("账单", "")
    # 去除多余空白与标点
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。")
    cleaned = cleaned.strip()
    # 若清理后剩余为空或过短（单字），回退到类别或描述
    if not cleaned or len(cleaned) <= 1:
        if category != "其他":
            cleaned = category
        else:
            # 尝试从原文提取名词片段（去除数字与账户后的首个词）
            cleaned = raw
            cleaned = _strip_bill_date(cleaned)
            cleaned = _BILL_TIME_RE.sub(" ", cleaned)
            cleaned = re.sub(r"(-?\d+(?:\.\d+)?)\s*(?:块钱|元钱|块|元|￥)?", "", cleaned)
            cleaned = cleaned.replace("块钱", "").replace("元钱", "")
            for acc in list(BILL_ACCOUNTS) + list(_BILL_ACCOUNT_ALIASES):
                cleaned = cleaned.replace(acc, "")
            for kw in ["花了", "支出", "花费", "付款", "消费", "支付", "扣款", "发", "补记", "补发"]:
                cleaned = cleaned.replace(kw, "")
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。")
            if not cleaned:
                cleaned = category if category != "其他" else "账单"

    # 标题与描述：标题取清理后前 20 字符，描述取清理后全文
    title = cleaned[:20].strip() if cleaned else (category if category != "其他" else "账单")
    description = cleaned if cleaned else title

    data: Dict[str, Any] = {
        "title": title,
        "amount": amount,
        "type": type_,
        "category": category,
        "account": account,
        "date": date_val,
        "time": time_val,
        "description": description,
    }
    return data, ""


# 日程相关常量
_SCHEDULE_PRIORITY_KEYWORDS: Dict[str, str] = {
    "高优": "high",
    "高优先级": "high",
    "高": "high",
    "紧急": "high",
    "重要": "high",
    "中优": "medium",
    "中优先级": "medium",
    "中": "medium",
    "低优": "low",
    "低优先级": "low",
    "低": "low",
}

_SCHEDULE_REPEATS = ["每天", "每日", "每周", "每月", "每年"]


def _parse_schedule_date(text: str, now: datetime) -> datetime:
    # 相对时间“2分钟后/3小时后”等视为今天，避免被误判为全天
    if re.search(r"(\d+\s*(?:分钟|分|小时|时|天|周)\s*后|半小时后)", text):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    # 支持 今天/明天/后天/2026-08-24/8月24日/8月24/8.24/8-24
    m = re.search(r"(今天|明天|昨天|后天|\d{4}-\d{2}-\d{2}|\d{1,2}月\d{1,2}日?|\d{1,2}[.\-]\d{1,2})", text)
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if not m:
        return base
    token = m.group(1)
    if token == "今天":
        return base
    if token == "明天":
        return base + timedelta(days=1)
    if token == "昨天":
        return base - timedelta(days=1)
    if token == "后天":
        return base + timedelta(days=2)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", token):
        try:
            dt = datetime.strptime(token, "%Y-%m-%d")
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            return base
    m2 = re.match(r"^(\d{1,2})月(\d{1,2})日$", token)
    if m2:
        try:
            month = int(m2.group(1))
            day = int(m2.group(2))
            return datetime(now.year, month, day)
        except ValueError:
            return base
    m3 = re.match(r"^(\d{1,2})月(\d{1,2})$", token)
    if m3:
        try:
            month = int(m3.group(1))
            day = int(m3.group(2))
            return datetime(now.year, month, day)
        except ValueError:
            return base
    m4 = re.match(r"^(\d{1,2})[.\-](\d{1,2})$", token)
    if m4:
        try:
            month = int(m4.group(1))
            day = int(m4.group(2))
            return datetime(now.year, month, day)
        except ValueError:
            return base
    return base


def _parse_schedule_time(text: str, base_date: datetime, now: datetime = None) -> Tuple[datetime, bool]:
    """解析时间，返回 (datetime, has_time)。支持绝对时间与相对时间 2分钟后/半小时后"""
    # 相对时间优先：2分钟后 / 3小时后 / 半小时后 等，基准用传入的 now（保持测试可控）
    _now = now or now_shanghai()
    m_rel = re.search(r"(\d+)\s*分钟后", text)
    if m_rel:
        try:
            mins = int(m_rel.group(1))
            dt = _now + timedelta(minutes=mins)
            return dt.replace(second=0, microsecond=0), True
        except ValueError:
            pass
    m_rel2 = re.search(r"(\d+)\s*小时后", text)
    if m_rel2:
        try:
            hours = int(m_rel2.group(1))
            dt = _now + timedelta(hours=hours)
            return dt.replace(second=0, microsecond=0), True
        except ValueError:
            pass
    m_rel3 = re.search(r"(\d+)\s*秒后", text)
    if m_rel3:
        try:
            secs = int(m_rel3.group(1))
            dt = _now + timedelta(seconds=secs)
            return dt.replace(second=0, microsecond=0), True
        except ValueError:
            pass
    if "半小时后" in text or "半个小时后" in text:
        dt = _now + timedelta(minutes=30)
        return dt.replace(second=0, microsecond=0), True
    # 匹配 (\d{1,2}[:点]\d{0,2}) 兼容冒号与中文点
    m = re.search(r"(\d{1,2})\s*[:：点]\s*(\d{1,2})?", text)
    has_time = False
    hour = 0
    minute = 0
    if m:
        has_time = True
        try:
            hour = int(m.group(1))
        except ValueError:
            hour = 0
        if m.group(2):
            try:
                minute = int(m.group(2))
            except ValueError:
                minute = 0
        else:
            minute = 0
        # 下午/晚上 换算：12 小时制转 24
        if any(kw in text for kw in ["下午", "晚上", "傍晚", "夜间"]):
            if 1 <= hour <= 11:
                hour += 12
        # 上午/凌晨不加
        hour = max(0, min(23, hour))
        minute = max(0, min(59, minute))
    return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0), has_time


def _detect_schedule_priority(text: str) -> str:
    # 按关键词长度降序匹配，避免 "高" 误抢 "高优"
    for kw in sorted(_SCHEDULE_PRIORITY_KEYWORDS.keys(), key=len, reverse=True):
        if kw in text:
            return _SCHEDULE_PRIORITY_KEYWORDS[kw]
    return "none"


def _detect_schedule_location(text: str) -> str:
    # 优先 "在...开" 结构
    m = re.search(r"在\s*(.+?)\s*开", text)
    if m:
        loc = m.group(1).strip()
        # 去除尾部标点
        loc = loc.strip(" ，,。")
        if loc:
            return loc
    # 兜底：在 后取非空片段直到空白或标点
    m2 = re.search(r"在\s*([^\s，。,]+)", text)
    if m2:
        loc = m2.group(1).strip()
        # 若捕获中仍含 "开" 与后续，截断
        if "开" in loc:
            loc = loc.split("开")[0]
        return loc.strip(" ，,。")
    return ""


def _detect_schedule_repeat(text: str) -> str:
    for rep in _SCHEDULE_REPEATS:
        if rep in text:
            # 统一返回 "每周" 等短形式
            if rep == "每日":
                return "每天"
            return rep
    if "不重复" in text:
        return ""
    # 兼容 "每周重复" 等
    m = re.search(r"(每天|每周|每月|每年)", text)
    if m:
        return m.group(1)
    return ""


def _detect_remind_before(text: str) -> int:
    m = re.search(r"提前\s*(\d+)\s*分钟", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    m2 = re.search(r"提前\s*(\d+)\s*分", text)
    if m2:
        try:
            return int(m2.group(1))
        except ValueError:
            pass
    return 10


def parse_schedule(text: str, now=None) -> Tuple[Optional[Dict], str]:
    """解析日程自然语言。返回 (data, err)。

    data 包含：title, date(datetime), priority, location, repeat, remind_before(int), allDay(bool)
    """
    now = now or now_shanghai()
    raw = (text or "").strip()
    if not raw:
        return None, "内容为空"
    # 兼容常见错别字
    raw = raw.replace("生气", "生日").replace("生如", "生日")

    base_date = _parse_schedule_date(raw, now)
    dt, has_time = _parse_schedule_time(raw, base_date, now)
    # 若未解析到时间且文本中无时间关键词，则视为全天事件
    all_day = not has_time

    priority = _detect_schedule_priority(raw)
    location = _detect_schedule_location(raw)
    repeat = _detect_schedule_repeat(raw)
    remind_before = _detect_remind_before(raw)

    # 标题提取：去除已识别片段
    cleaned = raw
    # 去除相对时间
    cleaned = re.sub(r"\d+\s*分钟后", "", cleaned)
    cleaned = re.sub(r"\d+\s*小时后", "", cleaned)
    cleaned = re.sub(r"\d+\s*秒后", "", cleaned)
    cleaned = re.sub(r"半小时后|半个小时后", "", cleaned)
    # 去除日期
    cleaned = re.sub(r"(今天|明天|昨天|后天|\d{4}-\d{2}-\d{2}|\d{1,2}月\d{1,2}日)", "", cleaned)
    # 去除时间段关键词下午等 + 时间本身
    cleaned = re.sub(r"(上午|下午|晚上|傍晚|凌晨|夜间)", "", cleaned)
    cleaned = re.sub(r"(\d{1,2})\s*[:：点]\s*(\d{1,2})?", "", cleaned)
    # 去除优先级词（按长度降序）
    for kw in sorted(_SCHEDULE_PRIORITY_KEYWORDS.keys(), key=len, reverse=True):
        cleaned = cleaned.replace(kw, "")
    # 去除地点片段
    if location:
        # 同时去除 "在"+location
        cleaned = cleaned.replace("在" + location, "")
        cleaned = cleaned.replace(location, "")
    else:
        # 无明确地点时仍尝试去除 "在..." 兜底
        cleaned = re.sub(r"在\s*[^\s，。,]+", "", cleaned)
    # 去除重复词
    for rep in _SCHEDULE_REPEATS + ["重复", "不重复"]:
        cleaned = cleaned.replace(rep, "")
    # 去除提醒词
    cleaned = re.sub(r"提前\s*\d+\s*分钟", "", cleaned)
    cleaned = re.sub(r"提前\s*\d+\s*分", "", cleaned)
    # 去除剩余动词与空白
    cleaned = cleaned.replace("开", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。")
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = "日程"
    title = cleaned[:30].strip()
    # 若标题过长含多词，取最后一段（通常为事件名）
    # 例如 "周会" 已经精简
    data: Dict[str, Any] = {
        "title": title,
        "date": dt,
        "priority": priority,
        "location": location,
        "repeat": repeat,
        "remind_before": remind_before,
        "allDay": all_day,
    }
    return data, ""


def parse_schedules_batch(text: str, now=None) -> Tuple[List[Dict], str]:
    """批量解析多条生日/日程（用于一句含多个“生日是农历X月X日”的情况）。直接扫描全文所有日期。

    对齐博客 schedules 新 schema（2026-08）：农历生日写 isLunar/lunarMonth/lunarDay
    （不存公历近似 date），公历生日存 date；农历转公历由博客端 lunar-javascript 完成。
    """
    now = now or now_shanghai()
    raw = (text or "").strip().replace("生气", "生日").replace("生如", "生日")
    if not raw:
        return [], "内容为空"
    # 关键词到 person 的映射
    person_map = {
        "我": "我",
        "我的": "我",
        "对象": "对象",
        "我对象": "对象",
        "对象是": "对象",
        "妈": "我妈",
        "妈妈": "我妈",
        "我妈": "我妈",
        "爸": "我爸",
        "爸爸": "我爸",
        "我爸": "我爸",
        "大姐": "大姐",
        "二姐": "二姐",
        "姐": "大姐",
    }
    is_lunar_all = "都是农历" in raw or "均为农历" in raw
    results: List[Dict] = []
    # 直接扫描全文所有日期，避免按逗号切分丢失“对象的是12.22”这类无“生日”关键词的条目
    for m_date in re.finditer(r"(\d{1,2})[.\-月](\d{1,2})日?", raw):
        date_start = m_date.start()
        # 向前取 20 字符找人物：取结束位置最靠近日期的词（同结束位置取更长词，
        # 避免“…12.14二姐4.4”里“姐”抢过“二姐”、“…8.24对象12.22”里“我”抢过“对象”）
        context = raw[max(0, date_start - 20) : date_start]
        person = ""
        best_end = -1
        best_len = -1
        for key, val in person_map.items():
            pos = context.rfind(key)
            if pos == -1:
                continue
            end = pos + len(key)
            if end > best_end or (end == best_end and len(key) > best_len):
                best_end = end
                best_len = len(key)
                person = val
        if not person:
            m_p = re.search(r"(\S{1,6})的是", context)
            if m_p:
                person = m_p.group(1).strip()
        try:
            month = int(m_date.group(1))
            day = int(m_date.group(2))
        except ValueError:
            continue
        is_lunar = is_lunar_all or "农历" in raw[max(0, date_start - 10) : m_date.end() + 10] or "农历" in context
        title = "{}生日".format(person) if person else "生日"
        item: Dict[str, Any] = {
            "title": title,
            "priority": "none",
            "location": "",
            "repeat": "每年",
            "remind_before": 10,
            "allDay": True,
            "category": "birthday",
            "person": person,
            "isLunar": is_lunar,
        }
        if is_lunar:
            item["lunarMonth"] = month
            item["lunarDay"] = day
        else:
            # 公历生日：已过今年则用明年
            try:
                dt = datetime(now.year, month, day)
                if dt < now.replace(hour=0, minute=0, second=0, microsecond=0):
                    dt = datetime(now.year + 1, month, day)
                item["date"] = dt
            except ValueError:
                continue
        results.append(item)
    if not results:
        return [], "未识别到生日信息"
    return results, ""


def schedule_filename(data: Dict, now: datetime = None) -> str:
    """日程文件名的日期部分：农历 → lunar-M-D（对齐 lunar-8-24-我的生日.md）；
    普通 → YYYY-MM-DD。"""
    if data.get("isLunar") and data.get("lunarMonth") and data.get("lunarDay"):
        return "lunar-{}-{}".format(data.get("lunarMonth"), data.get("lunarDay"))
    date_val = data.get("date")
    base = now or now_shanghai()
    if isinstance(date_val, datetime):
        return date_val.strftime("%Y-%m-%d")
    if isinstance(date_val, str) and date_val.strip():
        return date_val.strip()[:10]
    return base.strftime("%Y-%m-%d")


def parse_anniversary(text: str, now=None) -> Tuple[Optional[Dict], str]:
    """解析纪念日自然语言：标题 + 日期（公历/农历）+ 可选 @人物。

    示例：
      /纪念日 我和宝宝认识的纪念日 1月1日 @宝宝
      /纪念日 结婚纪念日 农历5月20
      /纪念日 领证纪念日 2026-05-20

    产出固定：repeat=每年、allDay=True、category=anniversary；
    农历日期存 isLunar/lunarMonth/lunarDay（无 date），公历存 date。
    """
    now = now or now_shanghai()
    raw = (text or "").strip()
    if not raw:
        return None, "内容为空"

    person = ""
    m_person = re.search(r"@(\S{1,10})", raw)
    if m_person:
        person = m_person.group(1).strip()
        raw = re.sub(r"@\S{1,10}", "", raw).strip()

    is_lunar = False
    has_year = False
    year = now.year
    month = day = None

    # 农历优先：农历5月20 / 农历5.20 / 农历5-20
    m_lunar = re.search(r"农历\s*(\d{1,2})\s*[.\-月]\s*(\d{1,2})\s*日?", raw)
    if m_lunar:
        is_lunar = True
        month = int(m_lunar.group(1))
        day = int(m_lunar.group(2))
    else:
        # 带年公历：2026-01-01 / 2026年1月1日 / 2026.1.1
        m_ymd = re.search(r"(\d{4})\s*[.\-年]\s*(\d{1,2})\s*[.\-月]\s*(\d{1,2})\s*日?", raw)
        if m_ymd:
            has_year = True
            year = int(m_ymd.group(1))
            month = int(m_ymd.group(2))
            day = int(m_ymd.group(3))
        else:
            # 月日公历：1月1日 / 1.1 / 1-1（年份用当前年）
            m_md = re.search(r"(\d{1,2})\s*[.\-月]\s*(\d{1,2})\s*日?", raw)
            if m_md:
                month = int(m_md.group(1))
                day = int(m_md.group(2))

    if month is None:
        return None, "未识别到日期（支持 1月1日 / 2026-01-01 / 农历5月20）"

    data: Dict[str, Any] = {
        "title": "",
        "priority": "none",
        "location": "",
        "repeat": "每年",
        "remind_before": 10,
        "allDay": True,
        "category": "anniversary",
        "person": person,
    }
    if is_lunar:
        data["isLunar"] = True
        data["lunarMonth"] = month
        data["lunarDay"] = day
        if not (1 <= month <= 12 and 1 <= day <= 30):
            return None, "农历日期超出范围（月 1-12，日 1-30）"
    else:
        try:
            data["date"] = datetime(year, month, day)
        except ValueError:
            return None, "公历日期无效：{}-{}-{}".format(year, month, day)

    # 标题 = 移除日期词、农历字样、@人物后的剩余文本
    cleaned = raw
    cleaned = re.sub(r"\d{4}\s*[.\-年]\s*\d{1,2}\s*[.\-月]\s*\d{1,2}\s*日?", "", cleaned)
    cleaned = re.sub(r"\d{1,2}\s*[.\-月]\s*\d{1,2}\s*日?", "", cleaned)
    cleaned = cleaned.replace("农历", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。")
    data["title"] = cleaned[:30].strip() or "纪念日"
    return data, ""


def build_bill_md(data: Dict, now=None) -> str:
    """生成账单 markdown。对齐博客最新 bills 格式（2026-08-23 参照）：
    字符串带双引号、date/amount 不带、tags 行内数组。"""
    now = now or now_shanghai()
    title = str(data.get("title") or data.get("description") or "账单").strip() or "账单"
    amount = data.get("amount", 0)
    type_ = data.get("type", "expense")
    if type_ not in ("income", "expense"):
        type_ = "expense"
    category = str(data.get("category") or "其他").strip() or "其他"
    account = str(data.get("account") or "其他").strip() or "其他"
    date_val = data.get("date") or now
    if isinstance(date_val, datetime):
        date_str = date_val.strftime("%Y-%m-%d")
    else:
        date_str = str(date_val).strip() or now.strftime("%Y-%m-%d")
    # 时刻（HH:mm）：无则回退当前时刻，保证博客今日流水可展示
    time_val = str(data.get("time") or "").strip()
    if not re.match(r"^\d{2}:\d{2}$", time_val):
        time_val = now.strftime("%H:%M")
    description = str(data.get("description") or title).strip()
    tags = data.get("tags")
    if tags is None:
        tags = [category] if category else []
    # 确保 tags 为列表
    if isinstance(tags, str):
        tags = [tags]
    fm: Dict[str, Any] = {
        "title": title,
        "amount": amount,
        "type": type_,
        "category": category,
        "account": account,
        "date": date_str,
        "time": time_val,
        "description": description,
        "tags": list(tags),
    }
    body = str(data.get("body") or description or title).strip()
    return _dump_yaml(fm, quote_all=True, inline_keys={"tags"}) + "\n\n" + body + "\n"


def build_schedule_md(data: Dict, now=None) -> str:
    """生成日程 markdown。对齐博客最新 schedules 格式（2026-08 参照）：

    - 字符串带双引号、date/allDay/isLunar 等不带；空 location/repeat/person 不写
    - 农历生日（isLunar）：不写 date，写 isLunar/lunarMonth/lunarDay，
      文件名用 lunar-M-D 前缀（对齐 lunar-8-24-我的生日.md）
    - 普通日程：全天只写日期，非全天写到秒
    """
    now = now or now_shanghai()
    title = str(data.get("title") or "日程").strip() or "日程"
    priority = str(data.get("priority") or "none").strip()
    if priority not in SCHEDULE_PRIORITIES:
        # 兼容中文优先级误传入
        priority = _SCHEDULE_PRIORITY_KEYWORDS.get(priority, "none")
        if priority not in SCHEDULE_PRIORITIES:
            priority = "none"
    status = str(data.get("status") or "todo").strip()
    if status not in ("todo", "done", "cancelled"):
        status = "todo"
    location = str(data.get("location") or "").strip()
    repeat = str(data.get("repeat") or "").strip()
    category = str(data.get("category") or "schedule").strip() or "schedule"
    if category not in ("schedule", "birthday", "anniversary", "holiday"):
        category = "schedule"
    person = str(data.get("person") or "").strip()
    fm: Dict[str, Any] = {
        "title": title,
    }
    is_lunar = bool(data.get("isLunar"))
    if is_lunar:
        # 农历：不写 date，由博客端 lunar-javascript 换算
        fm["allDay"] = bool(data.get("allDay", True))
    else:
        date_val = data.get("date") or now
        all_day = data.get("allDay")
        if isinstance(date_val, datetime):
            if all_day is None:
                all_day = date_val.hour == 0 and date_val.minute == 0 and date_val.second == 0
            date_str = date_val.strftime("%Y-%m-%d") if all_day else date_val.strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_str = str(date_val).strip() or now.strftime("%Y-%m-%d")
            all_day = bool(data.get("allDay", False))
        fm["date"] = date_str
        fm["allDay"] = bool(all_day)
    fm["priority"] = priority
    fm["status"] = status
    if location:
        fm["location"] = location
    if repeat:
        fm["repeat"] = repeat
    fm["category"] = category
    if person:
        fm["person"] = person
    if is_lunar:
        fm["isLunar"] = True
        fm["lunarMonth"] = int(data.get("lunarMonth") or 1)
        fm["lunarDay"] = int(data.get("lunarDay") or 1)
    # 可选 endDate（仅非农历）
    if not is_lunar and data.get("endDate"):
        end_val = data.get("endDate")
        if isinstance(end_val, datetime):
            fm["endDate"] = end_val.strftime("%Y-%m-%d")
        else:
            fm["endDate"] = str(end_val)
    body = str(data.get("description") or data.get("body") or title).strip()
    return _dump_yaml(fm, quote_all=True) + "\n\n" + body + "\n"
