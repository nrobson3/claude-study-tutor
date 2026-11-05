import re, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *


class Slides(unittest.TestCase):
    def setUp(self):
        self.v = mkvault("slides")
        self.c = self.v / "courses" / "chem"
        mkpdf(self.c / "slides" / "L01.pdf", ["Intro to thermodynamics lecture one page", "Enthalpy is heat at constant pressure xyzzy", "Entropy and the second law of things"])
        mkpdf(self.c / "past-tests" / "2023" / "mid.pdf", ["Midterm question about kinetics rates"])

    def txt(self, rel):
        return (self.c / "slides-text" / rel).read_text(encoding="utf-8")

    def test_index_basic(self):
        r = run(self.v, "slides.py", "index"); self.assertEqual(r.returncode, 0, r.stderr)
        t = self.txt("slides/L01.md")
        for n in (1, 2, 3): self.assertIn(f"## p. {n}\n", t)
        self.assertIn("pages: 3", t)
        self.assertIn("Enthalpy is heat", t)
        self.assertTrue((self.c / "slides-text" / "past-tests" / "2023" / "mid.md").exists())
        idx = (self.c / "slides-text" / "_index.md").read_text(encoding="utf-8")
        self.assertIn("L01.pdf", idx); self.assertIn("mid.pdf", idx)

    def test_skip_unchanged_and_reextract(self):
        run(self.v, "slides.py", "index")
        r = run(self.v, "slides.py", "index")
        self.assertIn("Indexed 0", r.stdout)
        mkpdf(self.c / "slides" / "L01.pdf", ["Changed content here entirely new"])
        r = run(self.v, "slides.py", "index")
        self.assertIn("Indexed 1", r.stdout)
        self.assertIn("Changed content", self.txt("slides/L01.md"))
        self.assertNotIn("Enthalpy", self.txt("slides/L01.md"))

    def test_index_title_cached_on_skip(self):
        run(self.v, "slides.py", "index"); a = (self.c / "slides-text" / "_index.md").read_text(encoding="utf-8")
        run(self.v, "slides.py", "index"); b = (self.c / "slides-text" / "_index.md").read_text(encoding="utf-8")
        self.assertEqual(a, b)
        self.assertIn("Intro to thermodynamics", b)

    def test_remove_orphan(self):
        run(self.v, "slides.py", "index")
        (self.c / "slides" / "L01.pdf").unlink()
        r = run(self.v, "slides.py", "index")
        self.assertIn("removed", r.stdout)
        self.assertFalse((self.c / "slides-text" / "slides" / "L01.md").exists())
        self.assertTrue((self.c / "slides-text" / "past-tests" / "2023" / "mid.md").exists())
        idx = (self.c / "slides-text" / "_index.md").read_text(encoding="utf-8")
        self.assertNotIn("L01.pdf", idx)

    def test_user_md_in_text_dir_kept(self):
        run(self.v, "slides.py", "index")
        m = self.c / "slides-text" / "mynotes.md"; m.write_text("# mine\n", encoding="utf-8")
        run(self.v, "slides.py", "index")
        self.assertTrue(m.exists())

    def test_search_attribution(self):
        run(self.v, "slides.py", "index")
        r = run(self.v, "slides.py", "search", "xyzzy")
        self.assertIn("L01.pdf p. 2 |", r.stdout); self.assertNotIn("p. 1 |", r.stdout); self.assertNotIn("p. 3 |", r.stdout)
        r = run(self.v, "slides.py", "search", "Entropy")
        self.assertIn("L01.pdf p. 3", r.stdout)
        r = run(self.v, "slides.py", "search", "kinetics", "--course", "chem")
        self.assertIn("mid.pdf p. 1", r.stdout)
        r = run(self.v, "slides.py", "search", "nonexistentword")
        self.assertIn("No matches", r.stdout)

    def test_search_max(self):
        run(self.v, "slides.py", "index")
        r = run(self.v, "slides.py", "search", "e", "--max", "2")
        self.assertIn("stopped at 2 hits", r.stdout)

    def test_search_invalid_regex_literal(self):
        run(self.v, "slides.py", "index")
        r = run(self.v, "slides.py", "search", "(unclosed")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_search_unknown_course(self):
        run(self.v, "slides.py", "index")
        r = run(self.v, "slides.py", "search", "x", "--course", "nope")
        self.assertNotEqual(r.returncode, 0)

    def test_render_specs(self):
        pdf = "courses/chem/slides/L01.pdf"
        def n(spec):
            return run(self.v, "slides.py", "render", pdf, "--pages", spec, "--dpi", "50")
        r = n("3"); self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(len(r.stdout.split()), 1); self.assertIn("-p3-", r.stdout)
        r = n("1-3"); self.assertEqual(len(r.stdout.split()), 3)
        r = n("1,3"); self.assertEqual(len(r.stdout.split()), 2)
        r = n("all"); self.assertEqual(len(r.stdout.split()), 3)
        r = n("ALL"); self.assertEqual(r.returncode, 0)
        for f in r.stdout.split(): self.assertTrue(Path(f).exists())
        r = n("3-1"); self.assertEqual(len(r.stdout.split()), 3)

    def test_render_out_of_range(self):
        pdf = "courses/chem/slides/L01.pdf"
        for spec in ("4", "0", "1-9", "2,99"):
            r = run(self.v, "slides.py", "render", pdf, "--pages", spec)
            self.assertNotEqual(r.returncode, 0, spec); self.assertIn("out of range", r.stderr, spec)
            self.assertNotIn("Traceback", r.stderr)
        for spec in ("abc", "-2", "1-"):
            r = run(self.v, "slides.py", "render", pdf, "--pages", spec)
            self.assertNotEqual(r.returncode, 0, spec); self.assertNotIn("Traceback", r.stderr, spec)

    def test_render_missing_and_corrupt(self):
        r = run(self.v, "slides.py", "render", "nothere.pdf", "--pages", "1")
        self.assertNotEqual(r.returncode, 0); self.assertNotIn("Traceback", r.stderr)
        bad = self.c / "slides" / "bad.pdf"; bad.write_bytes(b"not a pdf at all")
        r = run(self.v, "slides.py", "render", str(bad), "--pages", "1")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr, "render of corrupt PDF crashes with traceback")

    def test_corrupt_pdf_index(self):
        (self.c / "slides" / "bad.pdf").write_bytes(b"garbage\x00\x01")
        (self.c / "slides" / "empty.pdf").write_bytes(b"")
        r = run(self.v, "slides.py", "index")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("could not read", r.stdout)
        self.assertTrue((self.c / "slides-text" / "slides" / "L01.md").exists())
        self.assertFalse((self.c / "slides-text" / "slides" / "bad.md").exists())
        idx = (self.c / "slides-text" / "_index.md").read_text(encoding="utf-8")
        self.assertNotIn("bad.pdf", idx)

    def test_corrupt_replaces_good_pdf(self):
        run(self.v, "slides.py", "index")
        (self.c / "slides" / "L01.pdf").write_bytes(b"broken now")
        r = run(self.v, "slides.py", "index"); self.assertEqual(r.returncode, 0)
        self.assertTrue((self.c / "slides-text" / "slides" / "L01.md").exists())

    def test_hash_lines(self):
        mkpdf(self.c / "slides" / "H.pdf", ["# Heading-like first line\n## p. 99\nnormal line\n### deep"])
        run(self.v, "slides.py", "index")
        t = self.txt("slides/H.md")
        self.assertEqual(len(re.findall(r"(?m)^## p\. ", t)), 1)
        r = run(self.v, "slides.py", "search", "normal line"); self.assertIn("H.pdf p. 1", r.stdout)
        r = run(self.v, "slides.py", "search", "Heading-like"); self.assertIn("H.pdf p. 1", r.stdout)
        r = run(self.v, "slides.py", "search", "p\\. 99"); self.assertIn("H.pdf p. 1", r.stdout)
        self.assertNotIn("p. 99 |", r.stdout)

    def test_blank_page_and_unicode(self):
        d = pymupdf.open(); d.new_page(); p = d.new_page(); p.insert_text((72, 72), "Delta Δ = 5 µm and café", fontsize=11)
        d.save(self.c / "slides" / "B.pdf"); d.close()
        run(self.v, "slides.py", "index"); t = self.txt("slides/B.md")
        self.assertIn("no text layer", t); self.assertIn("(no extractable text)", t)

    def test_pdf_uppercase_ext_and_nested(self):
        mkpdf(self.c / "slides" / "sub" / "Z.PDF", ["Nested deck text content"])
        run(self.v, "slides.py", "index")
        self.assertTrue((self.c / "slides-text" / "slides" / "sub" / "Z.md").exists())

    def test_course_filter_and_no_slides_dir(self):
        (self.v / "courses" / "empty").mkdir()
        r = run(self.v, "slides.py", "index"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no PDFs yet", (self.v / "courses" / "empty" / "slides-text" / "_index.md").read_text(encoding="utf-8"))
        r = run(self.v, "slides.py", "index", "bogus"); self.assertNotEqual(r.returncode, 0)

    def test_same_stem_slides_and_pasttests(self):
        mkpdf(self.c / "past-tests" / "L01.pdf", ["Past test with same stem"])
        run(self.v, "slides.py", "index")
        self.assertTrue((self.c / "slides-text" / "past-tests" / "L01.md").exists())
        self.assertIn("Enthalpy", self.txt("slides/L01.md"))


if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
