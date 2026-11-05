import shutil, subprocess, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *


def git(v, *a):
    return subprocess.run(["git", *a], cwd=v, capture_output=True, text=True, encoding="utf-8")


class Sync(unittest.TestCase):
    def setUp(self):
        self.v = mkvault("sync")
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.v)], check=True)
        git(self.v, "config", "user.name", "T"); git(self.v, "config", "user.email", "t@e.x")
        concept(self.v, "c", "A", ["concept", "c", "status/solid"])
        (self.v / "README.md").write_text("r\n", encoding="utf-8")
        self.origin = WORK / "origin.git"
        if self.origin.exists():
            force_rmtree(self.origin)

    def push(self, *a):
        return run(self.v, "sync.py", "push", *a)

    def bare(self):
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        git(self.v, "remote", "add", "origin", str(self.origin))

    def test_push_no_remote(self):
        r = self.push("-m", "first"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Committed", r.stdout); self.assertIn("No GitHub remote", r.stdout)
        self.assertEqual(git(self.v, "log", "-1", "--format=%s").stdout.strip(), "first")
        self.assertTrue((self.v / "courses" / "c" / "map.md").exists())
        self.assertIn("courses/c/map.md", git(self.v, "ls-files").stdout)

    def test_nothing_to_commit(self):
        self.push(); r = self.push(); self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("Nothing to commit", r.stdout)

    def test_pull_no_remote(self):
        r = run(self.v, "sync.py", "pull"); self.assertEqual(r.returncode, 0); self.assertIn("nothing to pull", r.stdout)

    def test_remote_flow(self):
        self.bare()
        r = self.push("-m", "one"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("Pushed", r.stdout)
        self.assertIn("origin/main", git(self.v, "rev-parse", "--abbrev-ref", "@{u}").stdout)
        (self.v / "new.md").write_text("n", encoding="utf-8")
        r = self.push(); self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("Pushed", r.stdout)
        self.assertRegex(git(self.v, "log", "-1", "--format=%s").stdout, r"Study session \d{4}-\d\d-\d\d \d\d:\d\d")
        r = self.push(); self.assertIn("Nothing to commit", r.stdout); self.assertIn("Pushed", r.stdout)
        other = WORK / "clone2"
        if other.exists(): force_rmtree(other)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True)
        git(other, "config", "user.name", "O"); git(other, "config", "user.email", "o@e.x")
        (other / "from_other.md").write_text("o", encoding="utf-8"); git(other, "add", "-A"); git(other, "commit", "-qm", "o"); git(other, "push", "-q")
        r = run(self.v, "sync.py", "pull"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.v / "from_other.md").exists())
        r = run(self.v, "sync.py", "pull"); self.assertEqual(r.returncode, 0); self.assertIn("up to date", r.stdout.lower())
        (self.v / "README.md").write_text("dirty\n", encoding="utf-8")
        (other / "x2.md").write_text("o", encoding="utf-8"); git(other, "add", "-A"); git(other, "commit", "-qm", "o2"); git(other, "push", "-q")
        r = run(self.v, "sync.py", "pull"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.v / "README.md").read_text(), "dirty\n")
        force_rmtree(other)

    def test_push_rejected(self):
        self.bare(); self.push()
        other = WORK / "clone3"
        if other.exists(): force_rmtree(other)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True)
        git(other, "config", "user.name", "O"); git(other, "config", "user.email", "o@e.x")
        (other / "o.md").write_text("o"); git(other, "add", "-A"); git(other, "commit", "-qm", "o"); git(other, "push", "-q")
        (self.v / "mine.md").write_text("m")
        r = self.push(); self.assertNotEqual(r.returncode, 0); self.assertIn("Push failed", r.stderr)
        force_rmtree(other)

    def big(self, rel):
        p = self.v / rel; p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f: f.truncate(51 * 1024 * 1024)
        return p

    def test_large_file(self):
        self.bare()
        self.big("courses/c/slides/huge deck [v2].pdf"); self.big("vid.mp4")
        small = self.v / "courses" / "c" / "slides" / "ok.pdf"; small.write_bytes(b"x")
        r = self.push(); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Kept local only", r.stdout)
        gi = (self.v / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("# Large files kept on this laptop only", gi); self.assertIn("/vid.mp4", gi)
        tracked = git(self.v, "ls-files").stdout
        self.assertNotIn("vid.mp4", tracked); self.assertNotIn("huge deck", tracked); self.assertIn("ok.pdf", tracked)
        self.assertTrue((self.v / "vid.mp4").exists())
        self.assertEqual(git(self.v, "status", "--porcelain").stdout.strip(), "")
        r = self.push(); self.assertNotIn("Kept local only", r.stdout)
        self.assertEqual((self.v / ".gitignore").read_text(encoding="utf-8").count("/vid.mp4"), 1)
        sz = sum(f.stat().st_size for f in self.origin.rglob("*") if f.is_file()); self.assertLess(sz, 5 * 1024 * 1024)

    def test_large_file_already_tracked(self):
        p = self.v / "fat.bin"; p.write_bytes(b"x"); git(self.v, "add", "-A"); git(self.v, "commit", "-qm", "init")
        with open(p, "wb") as f: f.truncate(51 * 1024 * 1024)
        r = self.push(); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("fat.bin", git(self.v, "ls-files").stdout); self.assertTrue(p.exists())

    def test_large_in_cache_skipped(self):
        self.big(".cache/pages/x.png"); r = self.push()
        self.assertNotIn("Kept local", r.stdout)

    def test_maps_failure_continues(self):
        (self.v / "scripts" / "graph.py").write_text("import sys; sys.exit(3)\n")
        r = self.push(); self.assertEqual(r.returncode, 0); self.assertIn("maps not rebuilt", r.stdout)

    def test_push_runs_maps_then_commits_them(self):
        self.push()
        self.assertIn("c/map.md", git(self.v, "show", "--stat", "--format=", "HEAD").stdout.replace("\\", "/"))


if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
