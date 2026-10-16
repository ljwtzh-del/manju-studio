import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("bridge.py")
spec = importlib.util.spec_from_file_location("workbuddy_bridge", MODULE_PATH)
bridge = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(bridge)


class BridgeUnitTests(unittest.TestCase):
    def test_normalize_content(self):
        self.assertEqual(bridge.normalize_content(["hello", "world"]), "hello\nworld")
        self.assertEqual(bridge.normalize_content(None), "")
        self.assertIn('"x": 1', bridge.normalize_content({"x": 1}))

    def test_task_file_must_be_under_inbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "handoff" / "inbox"
            inbox.mkdir(parents=True)
            allowed = inbox / "ok.md"
            allowed.write_text("# task\nDo something safe.", encoding="utf-8")
            text = bridge.load_task_text(allowed, root)
            self.assertIn(str(root), text)
            self.assertIn("Do something safe", text)
            outside = root / "secret.md"
            outside.write_text("do not send", encoding="utf-8")
            with self.assertRaises(bridge.BridgeError):
                bridge.load_task_text(outside, root)

    def test_task_file_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "handoff" / "inbox"
            inbox.mkdir(parents=True)
            task = inbox / "large.md"
            task.write_text("x" * (bridge.MAX_TASK_CHARS + 1), encoding="utf-8")
            with self.assertRaises(bridge.BridgeError):
                bridge.load_task_text(task, root)

    def test_ensure_project_dirs_and_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.ensure_project_dirs(root)
            for rel in ("handoff/inbox", "handoff/sent", "handoff/reports", "handoff/archive"):
                self.assertTrue((root / rel).is_dir())

    def test_github_issue_from_other_author_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.ensure_project_dirs(root)
            issue = {"number": 12, "title": "untrusted", "body": "text", "url": "https://example.invalid/12", "author": {"login": "someone-else"}, "labels": [{"name": "workbuddy-task"}]}
            bridge.dispatch_github_issue(root, "owner/repo", issue, "my-account")
            self.assertFalse((root / "handoff" / "inbox" / "github-issue-12.md").exists())

    def test_watch_github_command_parses(self):
        args = bridge.build_parser().parse_args(["watch-github", "--repo", "owner/repo", "--once"])
        self.assertEqual(args.command, "watch-github")
        self.assertEqual(args.repo, "owner/repo")
        self.assertTrue(args.once)


if __name__ == "__main__":
    unittest.main(verbosity=2)
