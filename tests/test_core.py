# -*- coding: utf-8 -*-
"""blog_writer_core 核心逻辑单元测试。"""

import sys
import os
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blog_writer_core import (  # noqa: E402
    BILL_ACCOUNTS,
    BILL_CATEGORIES,
    SCHEDULE_PRIORITIES,
    SESSION_TIMEOUT,
    Session,
    build_album_md,
    build_amap_url,
    build_bill_md,
    build_github_commit_body,
    build_github_delete_tree_body,
    build_github_put_body,
    build_github_ref_update_body,
    build_github_tree_body,
    github_ref_url,
    github_refs_url,
    github_commit_url,
    github_trees_url,
    github_commits_url,
    build_imgbed_upload,
    build_moment_md,
    build_note_md,
    build_place_md,
    build_schedule_md,
    build_upload_url,
    build_friend_md,
    clean_filename_part,
    extract_tags,
    format_moment_published,
    gen_moment_id,
    moment_filename,
    next_friend_index,
    note_filename,
    parse_album,
    parse_album_frontmatter,
    parse_amap_response,
    parse_bill,
    parse_bills_batch,
    parse_dynamic,
    parse_friend_text,
    parse_github_put_response,
    parse_imgbed_response,
    parse_message,
    parse_note,
    parse_place,
    parse_schedule,
    parse_schedules_batch,
    place_filename,
    schedule_filename,
    upload_base_host,
    validate_friend_data,
    with_suffix,
)

try:
    import yaml
except ImportError:
    yaml = None


class TestParseMessage(unittest.TestCase):
    def test_command_with_slash(self):
        self.assertEqual(parse_message("/动态 今天去了公园")[0], "动态")
        self.assertEqual(parse_message("/动态 今天去了公园")[1], ["今天去了公园"])

    def test_command_without_slash(self):
        self.assertEqual(parse_message("发布")[0], "发布")

    def test_unknown_message(self):
        cmd, _, raw = parse_message("随便聊聊")
        self.assertIsNone(cmd)
        self.assertEqual(raw, "随便聊聊")

    def test_empty(self):
        self.assertIsNone(parse_message("")[0])
        self.assertIsNone(parse_message("   ")[0])

    def test_multi_space(self):
        cmd, args, _ = parse_message("/笔记 日常随笔 我的标题")
        self.assertEqual(cmd, "笔记")
        self.assertEqual(args, ["日常随笔", "我的标题"])

    def test_album_command(self):
        cmd, args, _ = parse_message("/相册 情侣头像")
        self.assertEqual(cmd, "相册")
        self.assertEqual(args, ["情侣头像"])

    def test_parse_album(self):
        self.assertEqual(parse_album(["情侣头像"]), "情侣头像")
        self.assertEqual(parse_album(["我的", "旅行"]), "我的 旅行")
        self.assertEqual(parse_album([]), "")
        self.assertEqual(parse_album(["  "]), "")

    def test_parse_album_frontmatter(self):
        # 常规：引号包裹的 imgbedFolder
        md = '---\ntitle: "测试相册"\nimgbedFolder: "blog/album/相册1"\n---\n'
        self.assertEqual(parse_album_frontmatter(md), ("测试相册", "blog/album/相册1"))
        # 无引号
        md2 = "---\ntitle: 情侣头像\ndate: 2026-08-13\nimgbedFolder: blog/album/情侣头像\n---\n"
        self.assertEqual(parse_album_frontmatter(md2), ("情侣头像", "blog/album/情侣头像"))
        # 缺字段
        md3 = "---\ntitle: 只有标题\n---\n"
        self.assertEqual(parse_album_frontmatter(md3), ("只有标题", ""))
        # 空/无 frontmatter
        self.assertEqual(parse_album_frontmatter(""), ("", ""))
        self.assertEqual(parse_album_frontmatter("正文无 frontmatter"), ("", ""))
        # title 值含冒号或特殊字符（键值行仅取第一个冒号后的内容）
        md4 = '---\ntitle: "A: B"\n---\n'
        self.assertEqual(parse_album_frontmatter(md4), ("A: B", ""))


class TestParseArgs(unittest.TestCase):
    def test_dynamic(self):
        content, tags = parse_dynamic(["今天", "去了公园"])
        self.assertEqual(content, "今天 去了公园")
        self.assertEqual(tags, [])

    def test_dynamic_with_tags(self):
        content, tags = parse_dynamic(["今天去了公园", "#日常", "#2026"])
        self.assertEqual(content, "今天去了公园")
        self.assertEqual(tags, ["日常", "2026"])
        # 标签去重
        content, tags = parse_dynamic(["内容", "#日常", "#日常"])
        self.assertEqual(tags, ["日常"])
        # 只有标签没有正文
        content, tags = parse_dynamic(["#日常"])
        self.assertIsNone(content)
        self.assertEqual(tags, ["日常"])

    def test_dynamic_empty(self):
        self.assertEqual(parse_dynamic([]), (None, []))
        self.assertEqual(parse_dynamic(["  "]), (None, []))

    def test_note_two_args(self):
        self.assertEqual(parse_note(["日常随笔", "标题"], "默认"), ("日常随笔", "标题"))

    def test_note_one_arg_uses_default_dir(self):
        self.assertEqual(parse_note(["标题"], "日常随笔"), ("日常随笔", "标题"))

    def test_note_multi_word_title(self):
        self.assertEqual(parse_note(["每日总结", "今天", "很好"], "默认"), ("每日总结", "今天 很好"))

    def test_note_no_args(self):
        self.assertEqual(parse_note([], "默认"), ("默认", ""))

    def test_place(self):
        self.assertEqual(parse_place(["陕西", "华阴市华山", "去找宝宝了"]), ("陕西", "华阴市华山", "去找宝宝了", []))

    def test_place_with_tags(self):
        self.assertEqual(
            parse_place(["陕西", "华阴市华山", "去找宝宝了", "#旅游", "#2026"]),
            ("陕西", "华阴市华山", "去找宝宝了", ["旅游", "2026"]),
        )

    def test_place_two_args(self):
        self.assertEqual(parse_place(["陕西", "华阴市华山"]), ("陕西", "华阴市华山", "", []))

    def test_place_one_arg(self):
        self.assertEqual(parse_place(["华山"]), ("", "华山", "", []))

    def test_place_empty(self):
        self.assertEqual(parse_place([]), ("", "", "", []))

    def test_extract_tags(self):
        clean, tags = extract_tags("今天 #日常 去公园\n第二行 #2026")
        self.assertEqual(tags, ["日常", "2026"])
        self.assertNotIn("#", clean)
        self.assertEqual(clean, "今天 去公园\n第二行")


class TestNaming(unittest.TestCase):
    def test_moment_id_format(self):
        m = gen_moment_id()
        self.assertTrue(m.startswith("ext-"))
        self.assertTrue(m[4:].isdigit())

    def test_published_format(self):
        self.assertRegex(format_moment_published(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_filenames(self):
        day = datetime(2026, 8, 8)
        self.assertEqual(moment_filename(day), "2026-08-08")
        self.assertEqual(note_filename(day), "2026年8月8日")
        self.assertEqual(note_filename(datetime(2026, 6, 1)), "2026年6月1日")
        self.assertEqual(place_filename(day), "2026-08-08")

    def test_with_suffix(self):
        self.assertEqual(with_suffix("a", ".md", 0), "a.md")
        self.assertEqual(with_suffix("a", ".md", 1), "a-1.md")
        self.assertEqual(with_suffix("a", ".md", 10), "a-10.md")


class TestMarkdown(unittest.TestCase):
    def test_moment_md_structure(self):
        md = build_moment_md("今天去了公园", ["https://img.tsh520.cn/file/a.jpg"], ["日常"])
        lines = md.split("\n")
        self.assertEqual(lines[0], "---")
        self.assertTrue("---" in lines)
        # 对齐现有格式：published 不加引号，无 id 字段
        self.assertIn("published: 20", md)
        self.assertNotIn('"published"', md)
        self.assertNotIn("id: ext-", md)
        # 2026-08-13 起博客不再按条写 author/avatar（schema 提供默认值）
        self.assertNotIn("author:", md)
        self.assertNotIn("avatar:", md)
        # 图片在 frontmatter 的 images 数组（URL 裸写，对齐现有风格），正文只有文字
        self.assertIn("images:", md)
        self.assertIn("  - https://img.tsh520.cn/file/a.jpg", md)
        self.assertNotIn("![a.jpg]", md)
        self.assertIn("今天去了公园", md)
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertNotIn("author", fm)
            self.assertNotIn("avatar", fm)
            self.assertEqual(fm["tags"], ["日常"])
            self.assertEqual(fm["images"], ["https://img.tsh520.cn/file/a.jpg"])
            self.assertNotIn("id", fm)
            self.assertIn("published", fm)

    def test_moment_md_no_images(self):
        md = build_moment_md("纯文字动态", [], ["日常"])
        self.assertNotIn("images:", md)
        self.assertNotIn("author:", md)
        self.assertNotIn("avatar:", md)
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm.get("images"), None)

    def test_note_md(self):
        md = build_note_md("标题", "正文第一行\n第二行", [], datetime(2026, 8, 8))
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm["name"], "标题")
            # js-yaml（Astro 用）会把 2026-08-08 当字符串；PyYAML 会解析成 date 对象，两者皆可
            self.assertTrue(fm["date"] == "2026-08-08" or fm["date"] == datetime(2026, 8, 8).date())
            self.assertNotIn("images", fm)
        self.assertIn("正文第一行\n第二行", md)
        self.assertNotIn("![]", md)

    def test_note_md_with_images(self):
        md = build_note_md("标题", "正文", ["https://img.tsh520.cn/file/a.jpg", "https://img.tsh520.cn/file/b.jpg"], datetime(2026, 8, 8))
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm["images"], ["https://img.tsh520.cn/file/a.jpg", "https://img.tsh520.cn/file/b.jpg"])
        self.assertIn("  - https://img.tsh520.cn/file/a.jpg", md)
        self.assertNotIn("![", md)

    def test_place_md(self):
        md = build_place_md("陕西", "华阴市华山", "去找宝宝了", ["https://img.tsh520.cn/file/places/x.jpg"], 34.477861, 110.084789, ["旅游"], datetime(2026, 8, 8))
        # 2026-08 新格式：新增 description 固定句式，不再写 visitCount（schema 默认 1）
        self.assertIn('description: "记录在陕西华阴市华山的足迹。"', md)
        self.assertNotIn("visitCount", md)
        self.assertIn('tags: ["旅游"]', md)
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm["province"], "陕西")
            self.assertEqual(fm["city"], "华阴市华山")
            self.assertEqual(fm["experience"], "去找宝宝了")
            self.assertEqual(fm["lat"], 34.477861)
            self.assertEqual(fm["lng"], 110.084789)
            self.assertNotIn("visitCount", fm)
            self.assertEqual(fm["photos"], ["https://img.tsh520.cn/file/places/x.jpg"])
            self.assertEqual(fm["tags"], ["旅游"])

    def test_place_md_no_experience(self):
        md = build_place_md("河南", "安阳", "", [], 36.1, 114.3, ["旅游"], datetime(2026, 8, 8))
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertNotIn("experience", fm)
            self.assertNotIn("photos", fm)

    def test_album_md(self):
        # 对齐博客相册惯例（2026-08）：title/subtitle/date + imgbedFolder（带引号），无 photos 列表
        md = build_album_md("情侣头像", "blog/album/情侣头像", datetime(2026, 8, 13))
        self.assertIn("title: 情侣头像", md)
        self.assertIn("subtitle: 记录情侣头像", md)
        self.assertIn("date: 2026-08-13", md)
        self.assertNotIn('"date"', md)
        self.assertIn('imgbedFolder: "blog/album/情侣头像"', md)
        self.assertNotIn("photos:", md)
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm["title"], "情侣头像")
            self.assertEqual(fm["imgbedFolder"], "blog/album/情侣头像")
            # js-yaml（Astro 用）按字符串解析；PyYAML 解析成 date 对象，两者皆可
            self.assertTrue(fm["date"] == "2026-08-13" or fm["date"] == datetime(2026, 8, 13).date())

    def test_yaml_quoting(self):
        # 含特殊字符的标题必须被正确引用，YAML 可解析
        md = build_note_md("标题: 带冒号", "正文", [], datetime(2026, 8, 8))
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm["name"], "标题: 带冒号")

    def test_yaml_numeric_tag_quoted(self):
        # 纯数字字符串必须加引号，否则 YAML 解析成 int，zod z.array(z.string()) 校验失败
        # （2026-08 起 places 用行内数组：tags: ["旅游", "2026"]）
        md = build_place_md("河南", "安阳", "", [], 36.1, 114.3, ["旅游", "2026"], datetime(2026, 8, 8))
        self.assertIn('"2026"', md)
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm["tags"], ["旅游", "2026"])

    def test_yaml_url_unquoted(self):
        # 动态（plain 风格）URL 仍裸写，对齐现有 moments 数据风格
        md = build_moment_md("内容", ["https://img.tsh520.cn/file/places/x.jpg"], ["日常"], datetime(2026, 8, 8))
        self.assertIn("  - https://img.tsh520.cn/file/places/x.jpg", md)
        # 足迹（quoted 风格，2026-08 对齐博客新格式）photos 带引号
        md2 = build_place_md("陕西", "华山", "", ["https://img.tsh520.cn/file/places/x.jpg"], 1.0, 2.0, ["旅游"], datetime(2026, 8, 8))
        self.assertIn('  - "https://img.tsh520.cn/file/places/x.jpg"', md2)
        if yaml:
            fm = yaml.safe_load(md2.split("---")[1])
            self.assertEqual(fm["photos"], ["https://img.tsh520.cn/file/places/x.jpg"])


class TestRequests(unittest.TestCase):
    def test_imgbed_upload_multipart(self):
        req = build_imgbed_upload("https://img.tsh520.cn/file", "a.png", b"1234")
        self.assertIn("multipart/form-data; boundary=", req["headers"]["Content-Type"])
        self.assertIn(b'name="file"; filename="a.png"', req["body"])
        self.assertIn(b"Content-Type: image/png", req["body"])
        self.assertNotIn(b"application/octet-stream", req["body"])
        self.assertTrue(req["body"].endswith(b"--\r\n") or req["body"].endswith(b"--"))
        self.assertIn(b"1234", req["body"])

    def test_imgbed_upload_mime_by_extension(self):
        from blog_writer_core import build_imgbed_upload as _build

        self.assertIn(b"Content-Type: image/jpeg", _build("https://img.tsh520.cn/upload", "photo.jpg", b"x")["body"])
        self.assertIn(b"Content-Type: image/jpeg", _build("https://img.tsh520.cn/upload", "photo.JPEG", b"x")["body"])
        self.assertIn(b"Content-Type: image/png", _build("https://img.tsh520.cn/upload", "a.png", b"x")["body"])
        self.assertIn(b"Content-Type: image/webp", _build("https://img.tsh520.cn/upload", "x.webp", b"x")["body"])
        self.assertIn(b"Content-Type: image/gif", _build("https://img.tsh520.cn/upload", "a.gif", b"x")["body"])
        self.assertIn(b"Content-Type: image/heic", _build("https://img.tsh520.cn/upload", "a.heic", b"x")["body"])
        self.assertIn(b"Content-Type: image/svg+xml", _build("https://img.tsh520.cn/upload", "a.svg", b"x")["body"])
        self.assertIn(b"Content-Type: image/x-icon", _build("https://img.tsh520.cn/upload", "a.ico", b"x")["body"])
        self.assertIn(b"Content-Type: video/mp4", _build("https://img.tsh520.cn/upload", "v.mp4", b"x")["body"])
        self.assertIn(b"Content-Type: video/quicktime", _build("https://img.tsh520.cn/upload", "v.mov", b"x")["body"])
        self.assertIn(b"Content-Type: video/x-m4v", _build("https://img.tsh520.cn/upload", "v.m4v", b"x")["body"])
        self.assertIn(b"Content-Type: video/webm", _build("https://img.tsh520.cn/upload", "v.webm", b"x")["body"])
        # 无扩展名/未知扩展名兜底 image/jpeg
        self.assertIn(b"Content-Type: image/jpeg", _build("https://img.tsh520.cn/upload", "noext", b"x")["body"])
        self.assertIn(b"Content-Type: image/jpeg", _build("https://img.tsh520.cn/upload", "file.unknown123", b"x")["body"])

    def test_imgbed_response(self):
        # 新版数组格式（官方文档 src/api/upload.md）：优先取 src（规范路径）
        ok, url = parse_imgbed_response(
            200, '[{"src": "/file/abc123_image.jpg", "publicUrl": "https://img.tsh520.cn/abc123_image.jpg"}]',
            "img.tsh520.cn",
        )
        self.assertTrue(ok)
        self.assertEqual(url, "https://img.tsh520.cn/file/abc123_image.jpg")
        # src 相对路径 → 拼主机
        ok, url = parse_imgbed_response(200, '[{"src": "/file/x.jpg"}]', "img.tsh520.cn")
        self.assertTrue(ok)
        self.assertEqual(url, "https://img.tsh520.cn/file/x.jpg")
        # 完整链接原样返回
        ok, url = parse_imgbed_response(200, '[{"src": "https://cdn.other.com/x.jpg"}]', "img.tsh520.cn")
        self.assertTrue(ok)
        self.assertEqual(url, "https://cdn.other.com/x.jpg")
        # 空数组
        ok, url = parse_imgbed_response(200, "[]", "img.tsh520.cn")
        self.assertFalse(ok)
        # 旧格式兼容
        ok, url = parse_imgbed_response(200, '{"code":200,"data":{"url":"https://x/a.jpg"}}', "")
        self.assertTrue(ok)
        self.assertEqual(url, "https://x/a.jpg")
        ok, url = parse_imgbed_response(200, '{"code":500,"message":"bad"}', "")
        self.assertFalse(ok)
        ok, url = parse_imgbed_response(200, "not json", "")
        self.assertFalse(ok)
        ok, url = parse_imgbed_response(200, '{"code":200,"data":"https://x/b.jpg"}', "")
        self.assertTrue(ok)
        self.assertEqual(url, "https://x/b.jpg")

    def test_upload_url_helpers(self):
        self.assertEqual(
            build_upload_url("https://img.tsh520.cn/upload", "blog/moments"),
            "https://img.tsh520.cn/upload?returnFormat=full&uploadFolder=blog/moments",
        )
        # 已有 authCode 时用 & 追加
        self.assertEqual(
            build_upload_url("https://img.tsh520.cn/upload?authCode=abc", "places"),
            "https://img.tsh520.cn/upload?authCode=abc&returnFormat=full&uploadFolder=places",
        )
        # 不重复追加已有参数
        self.assertEqual(
            build_upload_url("https://img.tsh520.cn/upload?uploadFolder=x&returnFormat=full", "blog"),
            "https://img.tsh520.cn/upload?uploadFolder=x&returnFormat=full",
        )
        # 空目录不加 uploadFolder
        self.assertEqual(
            build_upload_url("https://img.tsh520.cn/upload", ""),
            "https://img.tsh520.cn/upload?returnFormat=full",
        )
        self.assertEqual(upload_base_host("https://img.tsh520.cn/upload"), "img.tsh520.cn")

    def test_amap_url(self):
        url = build_amap_url("陕西省华阴市华山", "KEY123")
        self.assertIn("address=%E9%99%95%E8%A5%BF", url)
        self.assertIn("key=KEY123", url)

    def test_amap_response(self):
        ok, coords = parse_amap_response(200, '{"status":"1","count":"1","geocodes":[{"location":"110.084789,34.477861"}]}')
        self.assertTrue(ok)
        self.assertEqual(coords, (34.477861, 110.084789))
        ok, coords = parse_amap_response(200, '{"status":"0","count":"0","geocodes":[]}')
        self.assertFalse(ok)
        ok, coords = parse_amap_response(200, '{"status":"1","count":"0"}')
        self.assertFalse(ok)
        ok, coords = parse_amap_response(200, '{"status":"1","count":"1","geocodes":[{"location":"abc"}]}')
        self.assertFalse(ok)
        ok, coords = parse_amap_response(500, "oops")
        self.assertFalse(ok)

    def test_github_put_body(self):
        body = build_github_put_body("msg", "内容".encode("utf-8"), "main")
        self.assertIn('"message": "msg"', body)
        self.assertIn('"branch": "main"', body)
        self.assertIn('"content": "', body)

    def test_github_put_response(self):
        self.assertTrue(parse_github_put_response(201, "{}")[0])
        self.assertTrue(parse_github_put_response(200, "{}")[0])
        ok, err = parse_github_put_response(422, "{}")
        self.assertFalse(ok)
        self.assertEqual(err, "CONFLICT")
        ok, err = parse_github_put_response(403, '{"message":"rate limited"}')
        self.assertFalse(ok)
        self.assertIn("rate limited", err)

    def test_github_git_data_api_helpers(self):
        # 验证 URL 构造
        self.assertEqual(
            github_ref_url("owner/repo", "main"),
            "https://api.github.com/repos/owner/repo/git/ref/heads/main",
        )
        self.assertEqual(
            github_refs_url("owner/repo", "feat/test"),
            "https://api.github.com/repos/owner/repo/git/refs/heads/feat/test",
        )
        self.assertEqual(
            github_commit_url("owner/repo", "abc123sha"),
            "https://api.github.com/repos/owner/repo/git/commits/abc123sha",
        )
        self.assertEqual(
            github_trees_url("owner/repo"),
            "https://api.github.com/repos/owner/repo/git/trees",
        )
        self.assertEqual(
            github_commits_url("owner/repo"),
            "https://api.github.com/repos/owner/repo/git/commits",
        )

        # 验证 tree body 构造
        files = [
            ("src/content/bills/2026-10-11-lunch.md", "---\ntitle: lunch\n---"),
            ("src/content/bills/2026-10-11-dinner.md", "---\ntitle: dinner\n---"),
        ]
        tree_body = build_github_tree_body(files, base_tree="base_sha_123")
        self.assertIn('"base_tree": "base_sha_123"', tree_body)
        self.assertIn("src/content/bills/2026-10-11-lunch.md", tree_body)
        self.assertIn("100644", tree_body)
        self.assertIn("blob", tree_body)
        self.assertIn("---\\ntitle: lunch\\n---", tree_body)

        # 验证 commit body 构造
        commit_body = build_github_commit_body("批量发布", "tree_sha_xyz", "parent_sha_uvw")
        self.assertIn('"message": "\\u6279\\u91cf\\u53d1\\u5e03"', commit_body)
        self.assertIn('"tree": "tree_sha_xyz"', commit_body)
        self.assertIn('"parents": ["parent_sha_uvw"]', commit_body)

        # 验证 ref update body 构造
        ref_body = build_github_ref_update_body("new_commit_sha", force=False)
        self.assertIn('"sha": "new_commit_sha"', ref_body)
        self.assertIn('"force": false', ref_body)



class TestSession(unittest.TestCase):
    def test_expiry(self):
        now = datetime.now()
        s = Session("moment", {"content": "x"}, now)
        self.assertFalse(s.expired(now))
        self.assertTrue(s.expired(now + SESSION_TIMEOUT + timedelta(seconds=1)))

    def test_touch(self):
        now = datetime.now()
        s = Session("moment", {"content": "x"}, now)
        s.touch(now + timedelta(minutes=29))
        self.assertFalse(s.expired(now + timedelta(minutes=29) + SESSION_TIMEOUT - timedelta(seconds=1)))
        self.assertTrue(s.expired(now + timedelta(minutes=29) + SESSION_TIMEOUT + timedelta(seconds=1)))

    def test_text_and_images(self):
        s = Session("note", {"title": "t"})
        s.add_text("第一段")
        s.add_text("第二段")
        s.add_image("http://x/1.jpg", b"123")
        self.assertEqual(s.full_text(), "第一段\n第二段")
        self.assertEqual(len(s.images), 1)
        self.assertEqual(s.images[0], ("http://x/1.jpg", b"123"))


class TestFriend(unittest.TestCase):
    def test_parse_full(self):
        text = (
            "站点名称: 团子和蛋糕\n"
            "站点描述：如果你喜欢那么欢迎来到我的世界！\n"
            "站点链接 https://blog.tsh520.cn\n"
            "头像链接: /assets/ziyuan/tx.webp\n"
        )
        data = parse_friend_text(text)
        self.assertEqual(data["title"], "团子和蛋糕")
        self.assertEqual(data["desc"], "如果你喜欢那么欢迎来到我的世界！")
        self.assertEqual(data["siteurl"], "https://blog.tsh520.cn")
        self.assertEqual(data["imgurl"], "/assets/ziyuan/tx.webp")

    def test_parse_english_keys_and_order(self):
        text = "siteurl: https://blog.ayeez.cn\ntitle: 阿叶\nimgurl: https://qiniu.ayeez.cn/avatar.jpg\ndesc: 记录生活"
        data = parse_friend_text(text)
        self.assertEqual(data["title"], "阿叶")
        self.assertEqual(data["siteurl"], "https://blog.ayeez.cn")
        self.assertEqual(data["imgurl"], "https://qiniu.ayeez.cn/avatar.jpg")

    def test_parse_no_key_lines(self):
        # 无键名：URL 自动归类
        data = parse_friend_text("我的博客\nhttps://blog.tsh520.cn\nhttps://img.tsh520.cn/avatar.png")
        self.assertEqual(data["title"], "我的博客")
        self.assertEqual(data["siteurl"], "https://blog.tsh520.cn")
        self.assertEqual(data["imgurl"], "https://img.tsh520.cn/avatar.png")

    def test_parse_partial(self):
        data = parse_friend_text("站点名称: 小明\n其他无关行\n")
        self.assertEqual(data["title"], "小明")
        self.assertNotIn("siteurl", data)

    def test_parse_unknown_key_with_url_value(self):
        # 用户实测格式：键名不在别名表，但值能兜底识别
        data = parse_friend_text(
            "网站名称: RAGNote\n"
            "描述:Life is code. I will debug it.\n"
            "网站地址: https://ragnote.top/\n"
            "头像:https://ragnote.top/Avatar.png\n"
        )
        self.assertEqual(data["title"], "RAGNote")
        self.assertEqual(data["desc"], "Life is code. I will debug it.")
        self.assertEqual(data["siteurl"], "https://ragnote.top/")
        self.assertEqual(data["imgurl"], "https://ragnote.top/Avatar.png")

    def test_parse_no_colon_space(self):
        # 冒号后无空格的紧凑格式
        data = parse_friend_text("站点名称:张三\n站点链接:https://z.com\n站点描述:描述文字")
        self.assertEqual(data["title"], "张三")
        self.assertEqual(data["siteurl"], "https://z.com")
        self.assertEqual(data["desc"], "描述文字")

    def test_parse_butterfly_style_english_keys(self):
        # Butterfly 主题格式：name / link / avatar / descr
        data = parse_friend_text(
            "name: Hexo\nlink: https://hexo.io/\navatar: https://hexo.io/logo.svg\ndescr: 快速强大的博客框架"
        )
        self.assertEqual(data["title"], "Hexo")
        self.assertEqual(data["siteurl"], "https://hexo.io/")
        self.assertEqual(data["imgurl"], "https://hexo.io/logo.svg")
        self.assertEqual(data["desc"], "快速强大的博客框架")

    def test_parse_chinese_variants(self):
        # 中文博客圈常见变体
        data = parse_friend_text(
            "博客名：张三的博客\n"
            "博客地址: https://blog.zhang.com\n"
            "博主头像: https://blog.zhang.com/avatar.jpg\n"
            "博主简介：记录生活\n"
        )
        self.assertEqual(data["title"], "张三的博客")
        self.assertEqual(data["siteurl"], "https://blog.zhang.com")
        self.assertEqual(data["imgurl"], "https://blog.zhang.com/avatar.jpg")
        self.assertEqual(data["desc"], "记录生活")

    def test_validate(self):
        ok, _ = validate_friend_data({"title": "a", "siteurl": "https://a.com"})
        self.assertTrue(ok)
        ok, err = validate_friend_data({"siteurl": "https://a.com"})
        self.assertFalse(ok)
        self.assertIn("名称", err)
        ok, err = validate_friend_data({"title": "a"})
        self.assertFalse(ok)
        self.assertIn("链接", err)
        ok, err = validate_friend_data({"title": "a", "siteurl": "not-a-url"})
        self.assertFalse(ok)

    def test_build_friend_md(self):
        md = build_friend_md("张三", "描述", "https://z.com", "/assets/a.png", ["Blog"])
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm["title"], "张三")
            self.assertEqual(fm["siteurl"], "https://z.com")
            # 2026-08 对齐现有友链文件：weight 0、末尾 group: other
            self.assertEqual(fm["weight"], 0)
            self.assertTrue(fm["enabled"])
            self.assertEqual(fm["group"], "other")

    def test_clean_filename(self):
        self.assertEqual(clean_filename_part("张三的博客"), "张三的博客")
        self.assertEqual(clean_filename_part('a/b:c*d?'), "a-b-c-d")
        self.assertEqual(clean_filename_part("  "), "friend")

    def test_next_index(self):
        self.assertEqual(next_friend_index(["01-a.md", "02-b.md", "05-c.md"]), 6)
        self.assertEqual(next_friend_index(["01-a.md"]), 2)
        self.assertEqual(next_friend_index([]), 1)
        self.assertEqual(next_friend_index(["not-numbered.md"]), 1)


class TestBillSchedule(unittest.TestCase):
    def test_parse_bill_natural(self):
        data, err = parse_bill("今天午餐微信花了32")
        self.assertEqual(err, "")
        self.assertEqual(data["amount"], -32)
        self.assertEqual(data["category"], "餐饮")
        self.assertEqual(data["account"], "微信")

    def test_parse_bill_income(self):
        data, _ = parse_bill("发工资12000 银行卡")
        self.assertEqual(data["type"], "income")
        self.assertEqual(data["amount"], 12000)

    def test_parse_bill_borrow_rejected(self):
        # 负债类型已下线（博客账单仅支持 支出/收入）：借款/欠款返回错误
        data, err = parse_bill("花呗借款5000")
        self.assertIsNone(data)
        self.assertIn("负债类型已下线", err)

    def test_parse_bill_repay_as_expense(self):
        # 还款 = 资金流出，记为普通支出（分类「还款」，金额为负）
        data, err = parse_bill("花呗还款2000")
        self.assertEqual(err, "")
        self.assertEqual(data["type"], "expense")
        self.assertEqual(data["amount"], -2000)
        self.assertEqual(data["category"], "还款")
        self.assertEqual(data["account"], "花呗")

    def test_parse_bill_type_prefix(self):
        # 首词显式类型前缀
        data, _ = parse_bill("支出 午餐微信花了32")
        self.assertEqual(data["type"], "expense")
        self.assertEqual(data["amount"], -32)
        data2, _ = parse_bill("收入 兼职到手800 支付宝")
        self.assertEqual(data2["type"], "income")
        self.assertEqual(data2["amount"], 800)
        # 「还款」前缀 → 支出、分类固定「还款」
        data3, _ = parse_bill("还款 2000 微信")
        self.assertEqual(data3["type"], "expense")
        self.assertEqual(data3["amount"], -2000)
        self.assertEqual(data3["category"], "还款")

    def test_parse_bill_prefix_word_alone_not_stripped(self):
        # 「消费」后无空格内容时（如「消费30」），不作为前缀剥离，按关键词正常解析
        data, _ = parse_bill("消费30")
        self.assertEqual(data["type"], "expense")
        self.assertEqual(data["amount"], -30)

    def test_parse_bill_time_expressions(self):
        # 时间表达提取 → time 字段 HH:mm；标题不混入时间词
        cases = {
            "晚上8点吃了火锅60": "20:00",
            "下午3点半打车12": "15:30",
            "12点30分午饭20": "12:30",
            "14:30 奶茶18": "14:30",
            "早上6点买了包子5": "06:00",
        }
        for text, expect in cases.items():
            data, err = parse_bill(text)
            self.assertEqual(err, "", text)
            self.assertEqual(data["time"], expect, text)
        # 无时间词 → 回退当前时刻（HH:mm 格式）
        data, _ = parse_bill("午餐30")
        self.assertRegex(data["time"], r"^\d{2}:\d{2}$")
        # 标题剥离时间词
        hotpot, _ = parse_bill("晚上8点吃了火锅60")
        self.assertNotIn("8点", hotpot["title"])

    def test_build_bill_md_includes_time(self):
        # build_bill_md 输出 time 字段（HH:mm 带引号），旧数据缺 time 时回退 now
        from blog_writer_core import build_bill_md
        md = build_bill_md(
            {
                "title": "买鱼",
                "amount": -22,
                "type": "expense",
                "category": "水产",
                "account": "微信",
                "date": datetime(2026, 9, 5),
                "time": "09:05",
                "description": "买鱼",
            },
            now=datetime(2026, 9, 5, 10, 0),
        )
        self.assertIn('time: "09:05"', md)
        # time 缺失/非法 → 回退 now 的 HH:mm
        md2 = build_bill_md(
            {
                "title": "买鱼",
                "amount": -22,
                "type": "expense",
                "category": "水产",
                "account": "微信",
                "date": datetime(2026, 9, 5),
            },
            now=datetime(2026, 9, 5, 10, 0),
        )
        self.assertIn('time: "10:00"', md2)

    def test_parse_bill_category_prefix(self):
        # 首词分类前缀：关键词没命中的冷门消费（如理发）可显式指定分类
        data, _ = parse_bill("食品酒水 买了箱牛奶45")
        self.assertEqual(data["category"], "食品酒水")
        self.assertEqual(data["title"], "买了箱牛奶")
        # 类型 + 分类组合前缀
        data2, _ = parse_bill("支出 餐饮 午餐30")
        self.assertEqual(data2["type"], "expense")
        self.assertEqual(data2["category"], "餐饮")
        self.assertEqual(data2["title"], "午餐")

    def test_build_bill_md(self):
        md = build_bill_md(
            {
                "title": "午餐",
                "amount": -32,
                "type": "expense",
                "category": "餐饮",
                "account": "微信",
                "date": datetime(2026, 8, 21),
                "description": "午餐",
            },
            datetime(2026, 8, 21),
        )
        # 2026-08 对齐博客最新 bills 格式：字符串带引号、tags 行内数组、date/amount 不带
        self.assertIn("amount: -32", md)
        self.assertIn('category: "餐饮"', md)
        self.assertIn('title: "午餐"', md)
        self.assertIn("date: 2026-08-21", md)
        self.assertIn('tags: ["餐饮"]', md)

    def test_bill_16_screenshot_cases(self):
        # 严格验证来自真实微信截图的全部 16 笔被误判为「其他」的原始文本
        cases = [
            ("绿茶3", "食品酒水", 3),
            ("雪糕5", "食品酒水", 5),
            ("在美团买药买了感冒药和退烧药花了48块钱", "医疗健康", 48),
            ("昨天晚上去网吧上网充值了50块钱", "游戏", 50),
            ("昨天晚上跟朋友喝奶茶花了18块钱", "食品酒水", 18),
            ("昨天下午买了两张电影票花了70块钱", "休闲娱乐", 70),
            ("昨天在Steam买了一款游戏花了198块钱", "游戏", 198),
            ("昨天去医院挂号看病花了65块钱", "医疗健康", 65),
            ("昨天买了件短袖T恤花了89块钱", "居家生活", 89),
            ("昨天晚上在便利店买了包烟花了25块钱微信", "食品酒水", 25),
            ("昨天给家里猫咪买了包猫粮和猫罐头花了120块钱", "宠物", 120),
            ("昨天下午去肯德基吃了份套餐38块钱花呗", "餐饮", 38),
            ("昨天去屈臣氏买了瓶洗面奶和防晒霜花了85块钱", "居家生活", 85),
            ("昨天晚上租了个共享充电宝花了6块钱微信", "居家生活", 6),
            ("昨天买了本技术书籍花了59块钱", "居家生活", 59),
            ("昨天买了两盒酸奶和一袋切片面包花了18块钱", "食品酒水", 18),
        ]
        for text, exp_cat, exp_amt in cases:
            data, err = parse_bill(text)
            self.assertEqual(err, "", f"Failed on {text}: {err}")
            self.assertEqual(data["category"], exp_cat, f"Wrong category for {text}")
            self.assertEqual(abs(data["amount"]), exp_amt, f"Wrong amount for {text}")

    def test_bill_backfill_date_parsing(self):
        # 补记日期提取：支持 YYYY-MM-DD、昨天、前天、大前天、10-08、10.8、10月8日
        ref_now = datetime(2026, 11, 9, 12, 0, 0)
        # 1. 明确标准年月日
        data1, _ = parse_bill("2026-10-08 午餐30", ref_now)
        self.assertEqual(data1["date"].strftime("%Y-%m-%d"), "2026-10-08")
        self.assertEqual(abs(data1["amount"]), 30)

        # 2. 昨天
        data2, _ = parse_bill("昨天 午餐30", ref_now)
        self.assertEqual(data2["date"].strftime("%Y-%m-%d"), "2026-11-08")
        self.assertEqual(abs(data2["amount"]), 30)

        # 3. 前天
        data3, _ = parse_bill("前天 晚餐45", ref_now)
        self.assertEqual(data3["date"].strftime("%Y-%m-%d"), "2026-11-07")

        # 4. 大前天
        data4, _ = parse_bill("大前天 打车20", ref_now)
        self.assertEqual(data4["date"].strftime("%Y-%m-%d"), "2026-11-06")

        # 5. 月日简写 10-08 与 10.8
        data5, _ = parse_bill("10-08 午餐30", ref_now)
        self.assertEqual(data5["date"].strftime("%Y-%m-%d"), "2026-10-08")

        data6, _ = parse_bill("10.8 午餐30", ref_now)
        self.assertEqual(data6["date"].strftime("%Y-%m-%d"), "2026-10-08")

        # 6. 中文月日 10月8日
        data7, _ = parse_bill("10月8日 电影票70", ref_now)
        self.assertEqual(data7["date"].strftime("%Y-%m-%d"), "2026-10-08")

        # 7. 纯金额不含日期（如 10.8元）不应被误判为 10月8日
        data8, _ = parse_bill("午餐10.8元", ref_now)
        self.assertEqual(data8["date"].strftime("%Y-%m-%d"), "2026-11-09")
        self.assertEqual(data8["amount"], -10.8)

    def test_batch_bill_global_date_inheritance(self):
        # 批量账单全局首词日期继承：整批继承“昨天”，第二笔不回退今天
        ref_now = datetime(2026, 11, 9, 12, 0, 0)
        items, err = parse_bills_batch("昨天 午餐30 晚餐45 打车12", ref_now)
        self.assertEqual(err, "")
        self.assertEqual(len(items), 3)
        for item in items:
            self.assertEqual(item["date"].strftime("%Y-%m-%d"), "2026-11-08")
        self.assertEqual(abs(items[0]["amount"]), 30)
        self.assertEqual(abs(items[1]["amount"]), 45)
        self.assertEqual(abs(items[2]["amount"]), 12)

        # 单笔带日期不应被误拆成 4 笔
        single, err = parse_bills_batch("2026-10-08 午餐30", ref_now)
        self.assertEqual(err, "")
        self.assertEqual(len(single), 1)
        self.assertEqual(single[0]["title"], "午餐")
        self.assertEqual(single[0]["date"].strftime("%Y-%m-%d"), "2026-10-08")

        # 批量带完整日期前缀
        batch2, err = parse_bills_batch("2026-10-08 午餐30 晚餐45 打车12", ref_now)
        self.assertEqual(err, "")
        self.assertEqual(len(batch2), 3)
        for item in batch2:
            self.assertEqual(item["date"].strftime("%Y-%m-%d"), "2026-10-08")

    def test_build_github_delete_tree_body(self):
        # build_github_delete_tree_body 产生带 sha: null 的 tree entries
        body = build_github_delete_tree_body(["src/content/bills/2026-10-08-午餐.md"], "base123")
        import json
        data = json.loads(body)
        self.assertEqual(data["base_tree"], "base123")
        self.assertEqual(len(data["tree"]), 1)
        self.assertEqual(data["tree"][0]["path"], "src/content/bills/2026-10-08-午餐.md")
        self.assertIsNone(data["tree"][0]["sha"])

    def test_parse_schedule_natural(self):
        data, _ = parse_schedule("明天下午3点高优在会议室A开周会 每周重复 提前15分钟")
        self.assertEqual(data["title"], "周会")
        self.assertEqual(data["priority"], "high")
        self.assertEqual(data["location"], "会议室A")
        self.assertEqual(data["repeat"], "每周")
        self.assertEqual(data["remind_before"], 15)

    def test_build_schedule_md(self):
        md = build_schedule_md(
            {"title": "周会", "date": datetime(2026, 8, 22, 15, 0), "priority": "high", "location": "会议室A"},
            datetime(2026, 8, 22),
        )
        # 2026-08 对齐博客最新 schedules 格式：字符串带引号
        self.assertIn('title: "周会"', md)
        self.assertIn("date: 2026-08-22 15:00:00", md)
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm["title"], "周会")
            self.assertEqual(fm["location"], "会议室A")

    def test_build_schedule_md_empty_fields_omitted(self):
        # 空地点/重复不写字段（对齐现有文件：示例占位无 location/repeat）
        md = build_schedule_md({"title": "示例", "date": datetime(2026, 8, 22), "allDay": True}, datetime(2026, 8, 22))
        self.assertNotIn("location:", md)
        self.assertNotIn("repeat:", md)
        self.assertIn("date: 2026-08-22\n", md)  # 全天只写日期

    def test_schedules_batch_lunar(self):
        # 2026-08 农历生日：isLunar/lunarMonth/lunarDay，不存公历 date
        items, err = parse_schedules_batch("我的生日农历8.24对象12.22妈8.7大姐11.22爸12.14二姐4.4都是农历")
        self.assertEqual(err, "")
        self.assertEqual(len(items), 6)
        persons = [it["person"] for it in items]
        self.assertEqual(persons, ["我", "对象", "我妈", "大姐", "我爸", "二姐"])
        first = items[0]
        self.assertTrue(first["isLunar"])
        self.assertEqual(first["lunarMonth"], 8)
        self.assertEqual(first["lunarDay"], 24)
        self.assertNotIn("date", first)
        md = build_schedule_md(first)
        self.assertIn("isLunar: true", md)
        self.assertIn("lunarMonth: 8", md)
        self.assertIn("lunarDay: 24", md)
        self.assertNotIn("date:", md)
        self.assertEqual(schedule_filename(first), "lunar-8-24")

    def test_schedules_batch_solar(self):
        # 公历生日：存 date（今年已过则顺延明年）
        items, err = parse_schedules_batch("我生日3.15对象生日9.20")
        self.assertEqual(err, "")
        self.assertEqual(len(items), 2)
        self.assertFalse(items[0]["isLunar"])
        self.assertIn("date", items[0])
        self.assertEqual(schedule_filename(items[0], datetime(2026, 8, 23)), "2027-03-15")

    def test_parse_anniversary(self):
        from blog_writer_core import parse_anniversary

        # 公历月日 + @人物（对齐博客现有“我和宝宝认识的纪念日”）
        data, err = parse_anniversary("我和宝宝认识的纪念日 1月1日 @宝宝", datetime(2026, 8, 23))
        self.assertEqual(err, "")
        self.assertEqual(data["title"], "我和宝宝认识的纪念日")
        self.assertEqual(data["category"], "anniversary")
        self.assertEqual(data["repeat"], "每年")
        self.assertTrue(data["allDay"])
        self.assertEqual(data["person"], "宝宝")
        self.assertEqual(data["date"], datetime(2026, 1, 1))
        self.assertNotIn("isLunar", data)

        # 农历
        data2, _ = parse_anniversary("结婚纪念日 农历5月20", datetime(2026, 8, 23))
        self.assertTrue(data2["isLunar"])
        self.assertEqual(data2["lunarMonth"], 5)
        self.assertEqual(data2["lunarDay"], 20)
        self.assertNotIn("date", data2)
        self.assertEqual(data2["title"], "结婚纪念日")
        self.assertEqual(schedule_filename(data2), "lunar-5-20")

        # 带年公历
        data3, _ = parse_anniversary("领证纪念日 2026-05-20", datetime(2026, 8, 23))
        self.assertEqual(data3["date"], datetime(2026, 5, 20))

        # 无日期报错
        data4, err4 = parse_anniversary("结婚纪念日", datetime(2026, 8, 23))
        self.assertIsNone(data4)
        self.assertIn("日期", err4)

        # 日期非法报错
        data5, err5 = parse_anniversary("纪念日 13月40", datetime(2026, 8, 23))
        self.assertIsNone(data5)

    def test_build_anniversary_md(self):
        from blog_writer_core import build_schedule_md, parse_anniversary

        data, _ = parse_anniversary("我和宝宝认识的纪念日 1月1日 @宝宝", datetime(2026, 8, 23))
        md = build_schedule_md(data)
        # 对齐博客现有 src/content/schedules/2026-01-01-我和宝宝认识的纪念日.md
        self.assertIn('category: "anniversary"', md)
        self.assertIn('repeat: "每年"', md)
        self.assertIn('person: "宝宝"', md)
        self.assertIn("date: 2026-01-01", md)


class TestMedia(unittest.TestCase):
    def test_tmdb_search_url_and_poster(self):
        from blog_writer_core import build_tmdb_search_url, tmdb_poster_url

        url = build_tmdb_search_url("侏罗纪世界", "mykey")
        self.assertIn("api_key=mykey", url)
        self.assertIn("language=zh-CN", url)
        # 自定义反代 base
        url2 = build_tmdb_search_url("x", "k", "https://tmdb-proxy.example.com/")
        self.assertTrue(url2.startswith("https://tmdb-proxy.example.com/3/search/multi"))
        self.assertEqual(
            tmdb_poster_url("/abc.jpg"),
            "https://image.tmdb.org/t/p/w500/abc.jpg",
        )
        self.assertEqual(
            tmdb_poster_url("abc.jpg", "https://img-proxy.example.com/t/p/"),
            "https://img-proxy.example.com/t/p/w500/abc.jpg",
        )

    def test_parse_tmdb_search_response(self):
        from blog_writer_core import parse_tmdb_search_response
        import json

        body = json.dumps({
            "results": [
                {"media_type": "person", "name": "导演"},
                {
                    "media_type": "tv", "name": "测试剧", "original_name": "Test Show",
                    "first_air_date": "2024-03-01", "overview": "剧情简介", "vote_average": 8.1,
                    "poster_path": "/tv.jpg",
                },
            ]
        }, ensure_ascii=False)
        data, err = parse_tmdb_search_response(200, body)
        self.assertEqual(err, "")
        self.assertEqual(data["media_type"], "tv")
        self.assertEqual(data["title"], "测试剧")
        self.assertEqual(data["year"], "2024")
        # 未找到
        data2, err2 = parse_tmdb_search_response(200, json.dumps({"results": []}))
        self.assertIsNone(data2)
        self.assertIn("未找到", err2)
        # 401
        data3, err3 = parse_tmdb_search_response(401, "{}")
        self.assertIsNone(data3)
        self.assertIn("401", err3)

    def test_parse_media_score(self):
        from blog_writer_core import parse_media_score

        self.assertEqual(parse_media_score("评分 8"), 8)
        self.assertEqual(parse_media_score("打分：9"), 9)
        self.assertEqual(parse_media_score("10分"), 10)
        self.assertEqual(parse_media_score("99分"), 10)  # clamp 到 10
        self.assertIsNone(parse_media_score("好看"))
        self.assertIsNone(parse_media_score("评分"))  # 无数字不算

    def test_build_bangumi_md(self):
        from blog_writer_core import build_bangumi_md

        md = build_bangumi_md(
            "侏罗纪世界",
            "https://img.tsh520.cn/file/blog/bangumi/侏罗纪世界.jpg",
            score=8,
            tags=["冒险", "科幻"],
            comment="女主不该活着。",
            subcategory="movie",
            now=datetime(2026, 8, 23),
        )
        # 对齐博客现有 src/content/bangumi/anime/侏罗纪世界.md 格式
        self.assertIn("title: 侏罗纪世界", md)
        self.assertIn("category: anime", md)
        self.assertIn("subcategory: movie", md)
        self.assertIn("status: 2", md)
        self.assertIn("image: https://img.tsh520.cn/file/blog/bangumi/侏罗纪世界.jpg", md)
        self.assertIn("score: 8", md)
        self.assertIn("- 冒险", md)
        self.assertIn("published: 2026-08-23", md)
        self.assertIn("女主不该活着。", md)
        # 无评分/标签时不写字段
        md2 = build_bangumi_md("X", "https://i/x.jpg", score=None, tags=[], comment="", subcategory="tv", now=datetime(2026, 8, 23))
        self.assertNotIn("score:", md2)
        self.assertNotIn("tags:", md2)
        # 书籍：category book、无 subcategory
        md3 = build_bangumi_md(
            "认知觉醒", "https://img.tsh520.cn/file/blog/bangumi/认知觉醒.jpg",
            score=9, tags=["心理"], comment="好书", category="book", now=datetime(2026, 8, 23),
        )
        self.assertIn("category: book", md3)
        self.assertNotIn("subcategory", md3)
        self.assertIn("score: 9", md3)

    def test_parse_media_fields(self):
        from blog_writer_core import parse_media_fields

        self.assertEqual(parse_media_fields("名称: 我的阿勒泰"), {"title": "我的阿勒泰"})
        self.assertEqual(parse_media_fields("类型: 剧集"), {"subcategory": "tv"})
        self.assertEqual(parse_media_fields("类型：电影"), {"subcategory": "movie"})
        # 普通文本/评分不是键值对
        self.assertEqual(parse_media_fields("评分 8"), {})
        self.assertEqual(parse_media_fields("好看"), {})


class TestDaohang(unittest.TestCase):
    def test_xxapi_ico(self):
        from blog_writer_core import build_xxapi_ico_url, parse_xxapi_ico_response

        url = build_xxapi_ico_url("https://example.com/x?a=1")
        self.assertEqual(url, "https://v2.xxapi.cn/api/ico?url=https%3A%2F%2Fexample.com%2Fx%3Fa%3D1")
        ok_url, err = parse_xxapi_ico_response(200, '{"code":200,"data":"https://api.iowen.cn/favicon/x.png"}')
        self.assertEqual(err, "")
        self.assertEqual(ok_url, "https://api.iowen.cn/favicon/x.png")
        # 失败路径
        icon2, err2 = parse_xxapi_ico_response(200, '{"code":404}')
        self.assertIsNone(icon2)
        icon3, err3 = parse_xxapi_ico_response(200, '{"code":200,"data":"/relative.png"}')
        self.assertIsNone(icon3)

    def test_host_and_slug(self):
        from blog_writer_core import daohang_slug, site_host

        self.assertEqual(site_host("https://app.pagescms.org/inbox"), "app.pagescms.org")
        self.assertEqual(site_host("example.com/path"), "example.com")
        # 对齐现有无编号文件命名：app-pagescms-org.md / xxapi-cn.md
        self.assertEqual(daohang_slug("https://app.pagescms.org/"), "app-pagescms-org")
        self.assertEqual(daohang_slug("xxapi.cn"), "xxapi-cn")

    def test_parse_daohang_text(self):
        from blog_writer_core import parse_daohang_text

        kv = parse_daohang_text("名称: 团子的邮箱\n分类：学习网站\n描述: 邮箱服务")
        self.assertEqual(kv.get("name"), "团子的邮箱")
        self.assertEqual(kv.get("category"), "学习网站")  # 分类现为文件夹名
        self.assertEqual(kv.get("description"), "邮箱服务")
        # color 已随博客导航精简删除，不再解析
        self.assertNotIn("color", parse_daohang_text("颜色: #3b82f6"))
        # 无键值对内容
        self.assertEqual(parse_daohang_text("随便一句话"), {})

    def test_build_daohang_md(self):
        from blog_writer_core import build_daohang_md

        # 对齐博客 2026-09-21（v1.40.3 + tags 回归）：条目写 name/url + 可选 icon/description/tags
        md = build_daohang_md(
            "团子的邮箱",
            "https://email.0824.uk/inbox",
            "https://img.tsh520.cn/file/blog/daohang/x-icon.webp",
            "个人使用的邮箱服务",
            body="正文",
        )
        self.assertIn("name: 团子的邮箱", md)
        self.assertIn("url: https://email.0824.uk/inbox", md)
        self.assertIn("icon: https://img.tsh520.cn/file/blog/daohang/x-icon.webp", md)
        self.assertIn("description: 个人使用的邮箱服务", md)
        self.assertIn("正文", md)
        # 已删除字段一律不写（category 由文件夹决定；color/featured/order/image 已从 schema 移除）
        self.assertNotIn("category:", md)
        self.assertNotIn("color:", md)
        self.assertNotIn("featured:", md)
        self.assertNotIn("order:", md)
        # 无图标/描述时不写字段
        md2 = build_daohang_md("X", "https://x.com")
        self.assertNotIn("icon:", md2)
        self.assertNotIn("description:", md2)

    def test_build_daohang_md_tags(self):
        from blog_writer_core import build_daohang_md

        # tags 2026-09-21 起回归为可选字段，块状列表（与 src/content/daohang 下现有条目一致）
        md = build_daohang_md(
            "站点X",
            "https://x.cn",
            tags=["API", "对话"],
        )
        self.assertIn("tags:\n  - API\n  - 对话", md)
        # 空/空白 tags 不写 tags 行
        self.assertNotIn("tags:", build_daohang_md("X", "https://x.com", tags=[]))
        self.assertNotIn("tags:", build_daohang_md("X", "https://x.com", tags=["  ", ""]))
        # 单项也可
        self.assertIn("tags:\n  - 工具", build_daohang_md("X", "https://x.com", tags=["工具"]))


class TestWizard(unittest.TestCase):
    def test_parse_choice(self):
        from blog_writer_core import parse_choice

        self.assertEqual(parse_choice("1", 5), 1)
        self.assertEqual(parse_choice("3.", 5), 3)
        self.assertEqual(parse_choice("2、", 5), 2)
        self.assertEqual(parse_choice("  4  ", 5), 4)
        self.assertEqual(parse_choice("2 xxx", 5), 2)
        self.assertIsNone(parse_choice("0", 5))
        self.assertIsNone(parse_choice("6", 5))
        self.assertIsNone(parse_choice("abc", 5))
        self.assertIsNone(parse_choice("", 5))

    def test_format_choices(self):
        from blog_writer_core import format_choices

        t = format_choices("请选择：", ["a", "b"], extra=["新建"])
        self.assertIn("1. a", t)
        self.assertIn("3. 新建", t)
        self.assertIn("回复数字选择", t)

    def test_wizard_cancel_skip(self):
        from blog_writer_core import is_wizard_cancel, is_wizard_skip

        self.assertTrue(is_wizard_cancel("取消"))
        self.assertTrue(is_wizard_cancel("q"))
        self.assertTrue(is_wizard_skip("跳过"))
        self.assertFalse(is_wizard_cancel("1"))

    def test_session_wizard_field(self):
        from blog_writer_core import Session

        s = Session("note", {"title": "t"})
        self.assertIsNone(s.wizard)
        s.wizard = {"step": "note_pick_notebook"}
        self.assertEqual(s.wizard["step"], "note_pick_notebook")

    def test_build_notebook_index_json(self):
        import json

        from blog_writer_core import build_notebook_index_json

        md = build_notebook_index_json("全新笔记本")
        data = json.loads(md)
        self.assertEqual(data, {"name": "全新笔记本"})
        # tab 缩进 + 中文不转义（对齐现有 _index.json 风格）
        self.assertIn("\t\"name\": \"全新笔记本\"", md)


# 微信公众号文章样例（结构对齐 2026-09-16 实测页面：section 分段、span leaf、
# js_content 容器、脚本边界、页脚二维码/头像需过滤、ct 时间戳、HTML 实体）
WX_ARTICLE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta property="og:title" content="测试文章标题" />
<meta name="description" content="这是测试摘要。" />
</head>
<body>
<h1 class="rich_media_title " id="activity-name">
  <span class="js_title_inner">测试文章标题</span>
</h1>
<a id="js_name">测试公众号</a>
<em id="publish_time" class="rich_media_meta rich_media_meta_text"></em>
<script>var ct = "1785463020";</script>
<div class="rich_media_content js_underline_content" id="js_content" style="visibility: hidden;">
  <section><span leaf="">第一段文字 <strong>加粗</strong> 与 <em>斜体</em>，实体 &amp; &#39;单引号&#39;。</span></section>
  <section><span leaf="">第二段：<a href="https://example.com/a?b=1">链接文字</a></span></section>
  <section><img class="rich_pages wxw-img" data-src="https://mmbiz.qpic.cn/mmbiz_jpg/abc/640?wx_fmt=jpeg&amp;from=appmsg" /></section>
  <section><span leaf="">图片后面一段。<br>换行后的文字。</span></section>
  <section><img id="js_pc_qr_code_img" class="qr_code_pc_img" /><img class="jump_author_avatar" src="http://mmbiz.qpic.cn/mmbiz_png/xyz/0?wx_fmt=png" /></section>
  <ul><li>列表项一</li><li>列表项二</li></ul>
  <blockquote>引用内容</blockquote>
  <section><span leaf="">最后一段。</span></section>
  <script>console.log("tail")</script>
  <div class="rich_media_tool" id="js_tool">工具条不该进正文</div>
</div>
</body>
</html>"""


class TestWxArticle(unittest.TestCase):
    def test_extract_wx_url(self):
        from blog_writer_core import extract_wx_url

        self.assertEqual(
            extract_wx_url("/转载 https://mp.weixin.qq.com/s/_0CXcOf250uUhy1304rG3w"),
            "https://mp.weixin.qq.com/s/_0CXcOf250uUhy1304rG3w",
        )
        long_url = "https://mp.weixin.qq.com/s?__biz=MzA1&mid=123&idx=1&sn=abc"
        self.assertEqual(extract_wx_url("看这个 " + long_url + " 不错"), long_url)
        # 末尾标点剥离
        self.assertEqual(extract_wx_url("https://mp.weixin.qq.com/s/abc。"), "https://mp.weixin.qq.com/s/abc")
        # 非微信域名 / 无链接
        self.assertIsNone(extract_wx_url("https://example.com/s/abc"))
        self.assertIsNone(extract_wx_url("没有链接"))

    def test_extract_wx_article_ok(self):
        from blog_writer_core import WX_IMG_PLACEHOLDER, extract_wx_article

        data, err = extract_wx_article(WX_ARTICLE_HTML)
        self.assertEqual(err, "")
        self.assertEqual(data["title"], "测试文章标题")
        self.assertEqual(data["author"], "测试公众号")
        # publish_time 元素为空 → 回退 var ct 时间戳（1785463020 → 2026-07-31 上海时区）
        self.assertEqual(data["publish_date"], "2026-07-31")
        self.assertEqual(data["digest"], "这是测试摘要。")
        # 只保留正文图（过滤二维码/头像），且 http mmbiz 升级为 https
        self.assertEqual(len(data["image_urls"]), 1)
        self.assertTrue(data["image_urls"][0].startswith("https://mmbiz.qpic.cn/mmbiz_jpg/"))
        body = data["body_md"]
        self.assertIn("第一段文字", body)
        self.assertIn("**加粗**", body)
        self.assertIn("*斜体*", body)
        self.assertIn("& '单引号'", body)
        self.assertIn("[链接文字](https://example.com/a?b=1)", body)
        self.assertIn("- 列表项一", body)
        self.assertIn("> 引用内容", body)
        self.assertIn(WX_IMG_PLACEHOLDER % 0, body)
        # 页脚内容不进入正文
        self.assertNotIn("工具条不该进正文", body)

    def test_extract_wx_article_verify_page(self):
        from blog_writer_core import extract_wx_article

        data, err = extract_wx_article("<html><body>当前环境异常，完成验证后即可继续访问。</body></html>")
        self.assertIsNone(data)
        self.assertIn("验证", err)

    def test_extract_wx_article_no_content(self):
        from blog_writer_core import extract_wx_article

        data, err = extract_wx_article("<html><body><h1 id='x'>标题</h1></body></html>")
        self.assertIsNone(data)
        self.assertIn("正文", err)

    def test_extract_wx_article_digest_fallback(self):
        from blog_writer_core import extract_wx_article

        html = WX_ARTICLE_HTML.replace('<meta name="description" content="这是测试摘要。" />', "")
        data, err = extract_wx_article(html)
        self.assertEqual(err, "")
        self.assertTrue(data["digest"])
        self.assertIn("第一段文字", data["digest"])

    def test_extract_wx_article_empty_strong_cleaned(self):
        from blog_writer_core import extract_wx_article

        html = WX_ARTICLE_HTML.replace("第一段文字", "<strong></strong>第一段文字<strong> </strong>")
        data, err = extract_wx_article(html)
        self.assertEqual(err, "")
        self.assertNotIn("****", data["body_md"])

    def test_html_to_markdown_basic(self):
        from blog_writer_core import html_to_markdown

        md = html_to_markdown("<h2>大标题</h2><p>段落一</p><p>段落<b>粗</b></p><section>分节</section>")
        self.assertIn("## 大标题", md)
        self.assertIn("段落一", md)
        self.assertIn("**粗**", md)
        self.assertIn("分节", md)
        # section 作为段落边界：分节与上一段之间必须有换行（不粘连）
        self.assertNotIn("**粗**分节", md)

    def test_assemble_article_body(self):
        from blog_writer_core import assemble_article_body

        body = "前文\n\n{{IMG_0}}\n\n中间\n\n{{IMG_1}}\n\n后文\n\n{{IMG_9}}"
        out = assemble_article_body(body, ["https://img/a.jpg", "https://img/b.jpg"])
        self.assertIn("https://img/a.jpg", out)
        self.assertIn("https://img/b.jpg", out)
        self.assertNotIn("{{IMG_", out)  # 未解析到的占位符清除

    def test_build_article_md(self):
        from blog_writer_core import build_article_md

        md = build_article_md(
            "测试文章标题",
            "正文第一段。",
            ["https://img.tsh520.cn/file/blog/article/article-1.jpg"],
            ["转载"],
            description="这是测试摘要。",
            source_link="https://mp.weixin.qq.com/s/abc",
            author="测试公众号",
            publish_date="2026-07-31",
            now=datetime(2026, 9, 16),
        )
        self.assertIn("title: 测试文章标题", md)
        self.assertIn("published: 2026-09-16", md)
        self.assertIn("tags:\n  - 转载", md)
        self.assertIn("sourceLink: https://mp.weixin.qq.com/s/abc", md)
        self.assertIn("image: https://img.tsh520.cn/file/blog/article/article-1.jpg", md)
        self.assertNotIn("category:", md)  # 分类=目录，不写 frontmatter
        self.assertIn("> 本文转载自微信公众号「测试公众号」（原文发布于 2026-07-31）", md)
        self.assertIn("> 原文链接：https://mp.weixin.qq.com/s/abc", md)
        self.assertIn("正文第一段。", md)
        if yaml:
            fm = yaml.safe_load(md.split("---")[1])
            self.assertEqual(fm["title"], "测试文章标题")
            self.assertEqual(fm["tags"], ["转载"])
            self.assertEqual(fm["sourceLink"], "https://mp.weixin.qq.com/s/abc")


if __name__ == "__main__":
    unittest.main()
