import subprocess, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *


class Graph(unittest.TestCase):
    def setUp(self):
        self.v = mkvault("graph")

    def chk(self, *a):
        return run(self.v, "graph.py", "check", *a)

    def test_ok_both_forms(self):
        concept(self.v, "c1", "Alpha", ["concept", "c1", "status/solid"])
        concept(self.v, "c1", "Beta", ["concept", "c1", "status/shaky"], yaml_list=True, follows="**Follows from:** [[Alpha]]")
        r = self.chk(); self.assertEqual(r.returncode, 0, r.stdout); self.assertIn("Graph OK: 2", r.stdout)

    def test_hash_tags_in_list(self):
        concept(self.v, "c1", "Alpha", ["#concept", "#c1", "#status/solid"])
        self.assertEqual(self.chk().returncode, 0)

    def test_missing_pieces(self):
        concept(self.v, "c1", "NoStatus", ["concept", "c1"])
        concept(self.v, "c1", "NoConcept", ["c1", "status/solid"])
        concept(self.v, "c1", "NoCourse", ["concept", "status/solid"])
        concept(self.v, "c1", "NoStmt", ["concept", "c1", "status/solid"], statement="")
        concept(self.v, "c1", "TwoStatus", ["concept", "c1", "status/solid", "status/shaky"])
        concept(self.v, "c1", "BadStatus", ["concept", "c1", "status/great"])
        r = self.chk(); self.assertEqual(r.returncode, 1)
        o = r.stdout
        self.assertIn("NoStatus.md: no status tag", o); self.assertIn("NoConcept.md: tag 'concept' missing", o)
        self.assertIn("NoCourse.md: course tag 'c1' missing", o); self.assertIn("NoStmt.md: no **Statement:**", o)
        self.assertIn("more than one status", o); self.assertIn("BadStatus.md: unknown status", o)

    def test_broken_links_and_forms(self):
        concept(self.v, "c1", "Alpha", ["concept", "c1", "status/solid"], body="[[Missing]] [[Beta|alias]] [[Beta#Head]] [[Beta#Head|al]] ![[pic.png]]")
        concept(self.v, "c1", "Beta", ["concept", "c1", "status/solid"])
        (self.v / "pic.png").write_bytes(b"x")
        r = self.chk(); self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.count("broken link"), 1); self.assertIn("[[Missing]]", r.stdout)

    def test_link_to_alias_and_note_path(self):
        concept(self.v, "c1", "Alpha", ["concept", "c1", "status/solid"], fm_extra="aliases: [Aye, A-one]\n")
        concept(self.v, "c1", "Beta", ["concept", "c1", "status/solid"], body="[[Aye]] [[courses/c1/concepts/Alpha]] [[courses/c1/concepts/Alpha.md]] [[alpha#x|y]]")
        r = self.chk(); self.assertEqual(r.returncode, 0, r.stdout)

    def test_escaped_pipe_link_in_table(self):
        concept(self.v, "c1", "Alpha", ["concept", "c1", "status/solid"])
        concept(self.v, "c1", "Beta", ["concept", "c1", "status/solid"], body="| x |\n|---|\n| [[Alpha\\|a]] |")
        r = self.chk(); self.assertEqual(r.returncode, 0, "escaped-pipe link in table flagged broken: " + r.stdout)

    def test_duplicates(self):
        concept(self.v, "c1", "Alpha", ["concept", "c1", "status/solid"])
        concept(self.v, "c2", "Alpha", ["concept", "c2", "status/solid"])
        concept(self.v, "c1", "Gamma", ["concept", "c1", "status/solid"], fm_extra="aliases:\n  - Dee\n")
        concept(self.v, "c2", "Delta", ["concept", "c2", "status/solid"], fm_extra="aliases: [dee]\n")
        r = self.chk(); self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate name or alias 'Alpha'", r.stdout); self.assertIn("duplicate name or alias 'dee'", r.stdout)

    def test_cycles(self):
        concept(self.v, "c1", "A", ["concept", "c1", "status/solid"], follows="**Follows from:** [[B]]")
        concept(self.v, "c1", "B", ["concept", "c1", "status/solid"], follows="**Follows from:** [[C]]")
        concept(self.v, "c2", "C", ["concept", "c2", "status/solid"], follows="**Follows from:** [[A]]")
        concept(self.v, "c1", "Self", ["concept", "c1", "status/solid"], follows="**Follows from:** [[Self]]")
        r = self.chk(); self.assertEqual(r.returncode, 1)
        self.assertIn("circular", r.stdout); self.assertIn("A -> B -> C -> A", r.stdout); self.assertIn("Self -> Self", r.stdout)

    def test_acyclic_diamond_ok(self):
        concept(self.v, "c1", "A", ["concept", "c1", "status/solid"])
        concept(self.v, "c1", "B", ["concept", "c1", "status/solid"], follows="**Follows from:** [[A]]")
        concept(self.v, "c1", "C", ["concept", "c1", "status/solid"], follows="**Follows from:** [[A]]")
        concept(self.v, "c1", "D", ["concept", "c1", "status/solid"], follows="**Follows from:** [[B]], [[C]]")
        self.assertEqual(self.chk().returncode, 0)

    def test_follows_from_non_concept(self):
        concept(self.v, "c1", "A", ["concept", "c1", "status/solid"], follows="**Follows from:** [[README]]")
        (self.v / "README.md").write_text("hi", encoding="utf-8")
        r = self.chk(); self.assertEqual(r.returncode, 1); self.assertIn("not a concept note", r.stdout)

    def test_declared_course_mismatch(self):
        concept(self.v, "c1", "A", ["concept", "c1", "status/solid"], fm_extra="course: other\n")
        r = self.chk(); self.assertEqual(r.returncode, 1); self.assertIn("course says 'other'", r.stdout)

    def test_check_course_filter(self):
        concept(self.v, "c1", "A", ["concept", "c1"])
        concept(self.v, "c2", "B", ["concept", "c2", "status/solid"])
        self.assertEqual(self.chk("c2").returncode, 0)
        self.assertEqual(self.chk("c1").returncode, 1)

    def test_crlf(self):
        d = self.v / "courses" / "c1" / "concepts"; d.mkdir(parents=True)
        (d / "A.md").write_bytes(b"---\r\ntags: [concept, c1, status/solid]\r\n---\r\n**Statement:** x\r\n")
        r = self.chk(); self.assertEqual(r.returncode, 0, r.stdout)

    def test_maps(self):
        concept(self.v, "c1", "Solid1", ["concept", "c1", "status/solid"], statement="**Statement:** solid thing")
        concept(self.v, "c1", "Shaky1", ["concept", "c1", "status/shaky"], follows="**Follows from:** [[Other]]", statement="**Statement:** shaky thing")
        concept(self.v, "c1", "Nyet", ["concept", "c1", "status/not-yet"])
        concept(self.v, "c1", "Nostat", ["concept", "c1"])
        concept(self.v, "c2", "Other", ["concept", "c2", "status/solid"], yaml_list=True)
        (self.v / "courses" / "c1" / "course.md").write_text("---\ntitle: Chemistry One\n---\n", encoding="utf-8")
        mkpdf(self.v / "courses" / "c1" / "slides" / "seen.pdf", ["a"]); mkpdf(self.v / "courses" / "c1" / "slides" / "unseen.pdf", ["b"])
        (self.v / "courses" / "c1" / "sessions").mkdir()
        (self.v / "courses" / "c1" / "sessions" / "s1.md").write_text("Covered [[courses/c1/slides/seen.pdf|SEEN.pdf]]", encoding="utf-8")
        r = run(self.v, "graph.py", "maps"); self.assertEqual(r.returncode, 0, r.stderr)
        m = (self.v / "courses" / "c1" / "map.md").read_text(encoding="utf-8")
        self.assertIn("# Chemistry One: map", m); self.assertIn("4 concepts", m)
        i = {k: m.index(k) for k in ("## Shaky", "## Not yet", "## Solid", "## Status missing")}
        self.assertLess(i["## Shaky"], i["## Not yet"]); self.assertLess(i["## Not yet"], i["## Solid"])
        self.assertIn("- [[Solid1]] — solid thing", m)
        self.assertIn("## Leans on other courses", m); self.assertIn("[[Shaky1]] follows from [[Other]] (c2)", m)
        self.assertIn("unseen.pdf", m)
        self.assertNotIn("slides/seen.pdf", m)
        m2 = (self.v / "courses" / "c2" / "map.md").read_text(encoding="utf-8")
        self.assertIn("1 concepts", m2); self.assertNotIn("Leans on", m2)
        concept(self.v, "c1", "Mentions", ["concept", "c1", "status/solid"], body="see unseen.pdf")
        run(self.v, "graph.py", "maps", "c1")
        self.assertNotIn("Slide decks not studied", (self.v / "courses" / "c1" / "map.md").read_text(encoding="utf-8"))

    def test_maps_empty_course(self):
        (self.v / "courses" / "e").mkdir(parents=True)
        r = run(self.v, "graph.py", "maps"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("No concepts yet", (self.v / "courses" / "e" / "map.md").read_text(encoding="utf-8"))

    def test_maps_idempotent(self):
        concept(self.v, "c1", "A", ["concept", "c1", "status/solid"])
        run(self.v, "graph.py", "maps"); a = (self.v / "courses" / "c1" / "map.md").read_bytes()
        run(self.v, "graph.py", "maps"); self.assertEqual(a, (self.v / "courses" / "c1" / "map.md").read_bytes())

    def test_no_courses_dir(self):
        r = run(self.v, "graph.py", "check"); self.assertNotEqual(r.returncode, 0); self.assertNotIn("Traceback", r.stderr)

    def test_real_vault_copy_runs(self):
        r = subprocess.run(PY + [str(SRC / "graph.py"), "check"], capture_output=True, encoding="utf-8")
        self.assertIn(r.returncode, (0, 1)); self.assertNotIn("Traceback", r.stderr)
        print("\nREAL VAULT COPY check:", r.returncode, r.stdout[:300])


if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
