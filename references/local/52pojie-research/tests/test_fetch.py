#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch.py"
spec = importlib.util.spec_from_file_location("fetch_52pojie", SCRIPT)
assert spec and spec.loader
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class ParserTests(unittest.TestCase):
    def test_listing_parser_extracts_thread_links(self):
        source = """
        <title>『逆向资源区』</title>
        <span id='fd_page_top'><div class='pg'><span title='共 106 页'></span></div></span>
        <table id='threadlisttableid'><tbody>
          <tr><th><a class='s xst' href='thread-123-1-1.html'>工具讨论</a></th></tr>
          <tr><th><a class='s xst' href='thread-456-1-1.html'>另一个帖子</a></th></tr>
        </tbody></table>
        """
        result = fetch.parse_listing("https://www.52pojie.cn/forum-4-1.html", source, 4, 1)
        self.assertEqual(result["page_count"], 106)
        self.assertEqual([item["tid"] for item in result["threads"]], ["123", "456"])

    def test_rss_parser_extracts_public_metadata(self):
        source = """<?xml version='1.0' encoding='gbk'?>
        <rss><channel><title>逆向资源区</title><lastBuildDate>today</lastBuildDate>
          <item><title>工具</title><link>https://www.52pojie.cn/thread-123-1-1.html</link>
          <description>公开描述</description><author>作者</author><pubDate>today</pubDate></item>
        </channel></rss>"""
        result = fetch.parse_rss("https://www.52pojie.cn/forum.php?mod=rss&amp;fid=4", source, 4)
        self.assertEqual(result["items"][0]["title"], "工具")
        self.assertEqual(result["items"][0]["author"], "作者")

    def test_thread_parser_separates_posts_and_attachments(self):
        source = """
        <title>测试帖子 - 吾爱破解</title>
        <h1><span id='thread_subject'>测试帖子</span></h1>
        <div class='pg'><label><span>1</span> / 3 页</label></div>
        <span class='res-author'>作者A</span><em id='authorposton1'>发表于 2026-09-15</em>
        <div id='postmessage_1'><p>第一段</p><p>第二段</p>
          <img aid='9' zoomfile='https://attach.52pojie.cn/a.png' /></div>
        """
        result = fetch.parse_thread("https://www.52pojie.cn/thread-123-1-1.html", source, 123, 1)
        self.assertEqual(result["subject"], "测试帖子")
        self.assertEqual(result["page_count"], 3)
        self.assertEqual(result["posts"][0]["text"], "第一段\n第二段")
        self.assertEqual(result["attachments"][0]["aid"], "9")

    def test_hot_listing_is_public_and_thread_matching_returns_snippets(self):
        source = """
        <title>导读</title>
        <table><tr><th><a class='s xst' href='/thread-789-1-1.html'>热门工具</a></th></tr></table>
        """
        result = fetch.parse_listing("https://www.52pojie.cn/forum.php?mod=guide&view=hot", source, None, 1, view="hot")
        self.assertEqual(result["view"], "hot")
        self.assertEqual(result["threads"][0]["tid"], "789")
        self.assertEqual(fetch.hot_url(2), "https://www.52pojie.cn/forum.php?mod=guide&view=hot&page=2")
        self.assertIsNone(fetch.assert_public_url("https://www.52pojie.cn/forum.php?mod=guide&view=hot"))
        with self.assertRaises(ValueError):
            fetch.assert_public_url("https://www.52pojie.cn/forum.php?mod=redirect&goto=findpost")

        thread = {"page": 1, "posts": [{"post_id": "1", "page": 1, "text": "这里讨论 x64dbg 插件"}]}
        matches = fetch.thread_matches(thread, "x64dbg")
        self.assertEqual(matches[0]["post_id"], "1")
        self.assertIn("x64dbg", matches[0]["snippet"])

    def test_thread_parser_marks_restricted_empty_page(self):
        source = """
        <title>提示信息 - 吾爱破解</title>
        <div id='messagetext'><p>抱歉，您没有权限阅读本帖</p></div>
        """
        result = fetch.parse_thread("https://www.52pojie.cn/thread-999-1-1.html", source, 999, 1)
        self.assertEqual(result["content_status"], "restricted")
        self.assertIn("权限", result["message"])
        self.assertEqual(result["posts"], [])

    def test_search_can_find_a_body_only_match_with_a_bounded_scan(self):
        listing = {
            "threads": [{"tid": "123", "url": "https://www.52pojie.cn/thread-123-1-1.html", "title": "普通标题"}]
        }
        detail = {
            "page": 1,
            "page_count": 1,
            "pages_read": [1],
            "truncated": False,
            "content_status": "ok",
            "message": "",
            "posts": [{"post_id": "1", "page": 1, "text": "正文出现 secret 关键词"}],
        }
        args = fetch.build_parser().parse_args([
            "search", "--query", "secret", "--pages", "1", "--no-include-rss",
            "--scan-thread-bodies", "--max-body-threads", "1", "--delay", "0",
        ])
        with patch.object(fetch, "command_list", return_value=listing), patch.object(fetch, "read_thread_pages", return_value=detail):
            result = fetch.command_search(args)
        self.assertEqual(result["body_scan_threads"], 1)
        self.assertFalse(result["body_scan_truncated"])
        self.assertEqual(result["matches"][0]["matched_in"], "thread")
        self.assertEqual(len(result["matches"][0]["thread_matches"]), 1)


if __name__ == "__main__":
    unittest.main()
