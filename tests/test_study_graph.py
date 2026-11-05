import json, re, subprocess, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *

REPO = SRC.parent
TOOLS = REPO / "tools" / "study-graph"
PLUGIN = Path(".obsidian") / "plugins" / "study-graph"


def mkgraphvault(name):
    v = mkvault(name)
    shutil.copytree(TOOLS, v / "tools" / "study-graph")
    (v / "courses").mkdir(exist_ok=True)
    return v


def tags(status=None, course="c1"):
    t = ["concept", course]
    if status:
        t.append("status/" + status)
    return t


class Base(unittest.TestCase):
    def setUp(self):
        self.v = mkgraphvault(self.__class__.__name__.lower())

    def sg(self, *args):
        return run(self.v, "study_graph.py", *args)

    def export(self):
        r = self.sg("export")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


class Export(Base):
    def test_nodes_and_fields(self):
        concept(self.v, "c1", "Alpha", tags("solid"), statement="**Statement:** Alpha is first.",
                fm_extra="aliases: [A, Alef]\nkind: definition\n",
                body="**Slides:** [[courses/c1/slides/L1.pdf#page=3]] and [[courses/c1/slides/L2.pdf#page=9]]")
        d = self.export()
        self.assertEqual(d["vault"], self.v.name)
        self.assertEqual(len(d["nodes"]), 1)
        n = d["nodes"][0]
        self.assertEqual(n["id"], "courses/c1/concepts/Alpha.md")
        self.assertEqual(n["name"], "Alpha")
        self.assertEqual(n["course"], "c1")
        self.assertEqual(n["status"], "solid")
        self.assertEqual(n["kind"], "definition")
        self.assertEqual(n["statement"], "Alpha is first.")
        self.assertEqual(n["aliases"], ["A", "Alef"])
        self.assertEqual(n["slide"], "courses/c1/slides/L1.pdf#page=3")
        self.assertEqual(d["edges"], [])

    def test_defaults_when_fields_absent(self):
        concept(self.v, "c1", "Bare", ["concept", "c1"], statement="")
        n = self.export()["nodes"][0]
        self.assertEqual(n["status"], "unknown")
        self.assertEqual(n["kind"], "")
        self.assertEqual(n["aliases"], [])
        self.assertEqual(n["slide"], "")
        self.assertEqual(n["statement"], "")

    def test_status_unknown_cases(self):
        concept(self.v, "c1", "Two", ["concept", "c1", "status/solid", "status/shaky"])
        concept(self.v, "c1", "Weird", ["concept", "c1", "status/great"])
        concept(self.v, "c1", "None1", ["concept", "c1"])
        concept(self.v, "c1", "Shaky", tags("shaky"))
        concept(self.v, "c1", "Ny", tags("not-yet"))
        st = {n["name"]: n["status"] for n in self.export()["nodes"]}
        self.assertEqual(st, {"Two": "unknown", "Weird": "unknown", "None1": "unknown", "Shaky": "shaky", "Ny": "not-yet"})

    def test_yaml_list_aliases(self):
        concept(self.v, "c1", "Alpha", tags("solid"), fm_extra="aliases:\n  - Al\n  - Alf\n")
        self.assertEqual(self.export()["nodes"][0]["aliases"], ["Al", "Alf"])

    def test_edges_with_alias_resolution(self):
        concept(self.v, "c1", "Alpha", tags("solid"), fm_extra="aliases: [Alef]\n")
        concept(self.v, "c1", "Beta", tags("shaky"), follows="**Follows from:** [[Alef]]")
        concept(self.v, "c1", "Gamma", tags("not-yet"), follows="**Follows from:** [[alpha]], [[BETA#Heading]]")
        d = self.export()
        A, B, G = (f"courses/c1/concepts/{x}.md" for x in ("Alpha", "Beta", "Gamma"))
        got = {(e["source"], e["target"]) for e in d["edges"]}
        self.assertEqual(got, {(B, A), (G, A), (G, B)})

    def test_edges_pipe_alias_and_cross_course(self):
        concept(self.v, "c1", "Alpha", tags("solid"))
        concept(self.v, "c2", "Beta", tags("solid", "c2"), follows="**Follows from:** [[Alpha|the first]]")
        d = self.export()
        self.assertEqual(d["edges"], [{"source": "courses/c2/concepts/Beta.md", "target": "courses/c1/concepts/Alpha.md"}])

    def test_edges_to_missing_dropped(self):
        concept(self.v, "c1", "Alpha", tags("solid"), follows="**Follows from:** [[Nope]], [[Also Nope]]")
        concept(self.v, "c1", "Beta", tags("solid"), follows="**Follows from:** [[Nope]], [[Alpha]]")
        d = self.export()
        self.assertEqual(d["edges"], [{"source": "courses/c1/concepts/Beta.md", "target": "courses/c1/concepts/Alpha.md"}])

    def test_self_edge_dropped(self):
        concept(self.v, "c1", "Alpha", tags("solid"), fm_extra="aliases: [Self]\n", follows="**Follows from:** [[Alpha]], [[Self]]")
        self.assertEqual(self.export()["edges"], [])

    def test_slide_without_pagenum_and_with_label(self):
        concept(self.v, "c1", "A", tags("solid"), body="**Slides:** [[courses/c1/slides/L1.pdf]]")
        concept(self.v, "c1", "B", tags("solid"), body="**Slides:** [[courses/c1/slides/L2.pdf#page=4|Lecture 2]]")
        concept(self.v, "c1", "C", tags("solid"), body="**Slides:** none yet")
        s = {n["name"]: n["slide"] for n in self.export()["nodes"]}
        self.assertEqual(s["A"], "courses/c1/slides/L1.pdf")
        self.assertEqual(s["B"], "courses/c1/slides/L2.pdf#page=4")
        self.assertEqual(s["C"], "")

    def test_slide_first_line_wins(self):
        concept(self.v, "c1", "A", tags("solid"), body="**Slides:** [[one.pdf#page=1]]\n**Slides:** [[two.pdf#page=2]]")
        self.assertEqual(self.export()["nodes"][0]["slide"], "one.pdf#page=1")

    def test_unicode_survives(self):
        concept(self.v, "c1", "Schrödinger", tags("solid"), statement="**Statement:** ΔE = hν → √2")
        n = self.export()["nodes"][0]
        self.assertEqual(n["name"], "Schrödinger")
        self.assertEqual(n["statement"], "ΔE = hν → √2")

    def test_export_to_file(self):
        concept(self.v, "c1", "Alpha", tags("solid"))
        out = self.v / "out.json"
        r = self.sg("export", "-o", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(json.loads(out.read_text(encoding="utf-8"))["nodes"]), 1)

    def test_empty_vault_with_courses_dir(self):
        d = self.export()
        self.assertEqual(d["nodes"], [])
        self.assertEqual(d["edges"], [])

    def test_course_without_concepts_folder(self):
        (self.v / "courses" / "empty").mkdir()
        self.assertEqual(self.export()["nodes"], [])

    def test_no_courses_dir_at_all(self):
        force_rmtree(self.v / "courses")
        r = self.sg("export")
        self.assertEqual(r.returncode, 0, "export crashes without courses/: " + r.stderr[-300:])

    def test_duplicate_follows_links_produce_unique_edges(self):
        concept(self.v, "c1", "Alpha", tags("solid"))
        concept(self.v, "c1", "Beta", tags("solid"), follows="**Follows from:** [[Alpha]], [[Alpha]]")
        # The JS analyser de-duplicates anyway; this documents what export emits.
        self.assertLessEqual(len(self.export()["edges"]), 1, "duplicate edges exported")


class Html(Base):
    def out(self):
        return self.v / ".cache" / "study-graph.html"

    def build_html(self):
        r = self.sg("html")
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.out().read_text(encoding="utf-8")

    @staticmethod
    def extract_data(html):
        m = re.search(r"const DATA = (.*);\nStudyGraph\.createGraphView", html, re.S)
        assert m, "DATA marker not found"
        return json.loads(m.group(1))

    def test_writes_file_with_data_embedded(self):
        concept(self.v, "c1", "Alpha", tags("solid"), statement="**Statement:** hello")
        concept(self.v, "c1", "Beta", tags("shaky"), follows="**Follows from:** [[Alpha]]")
        html = self.build_html()
        self.assertTrue(self.out().exists())
        data = self.extract_data(html)
        self.assertEqual(data, self.export())
        for marker in ("/*DATA*/", "/*CORE*/", "/*STYLES*/"):
            self.assertNotIn(marker, html)
        self.assertEqual(html.count("function StudyGraphFactory"), 1)
        self.assertIn(".sg-canvas", html)  # styles inlined

    def test_script_close_in_statement_does_not_break_page(self):
        concept(self.v, "c1", "Evil", tags("solid"), statement="**Statement:** </script><script>alert(1)</script> x")
        html = self.build_html()
        self.assertEqual(len(re.findall(r"</script", html, re.I)), 4, "only the template's 4 script closers expected")
        self.assertEqual(len(re.findall(r"<script", html, re.I)), 4, "payload must not carry a raw <script")
        data = self.extract_data(html)
        self.assertEqual(data["nodes"][0]["statement"], "</script><script>alert(1)</script> x")

    def test_html_comment_open_plus_script_in_statement_is_escaped(self):
        # HTML "script data double escaped" state: "<!--" followed by "<script" makes the parser ignore the
        # next real </script>, swallowing the rest of the page. The payload must not carry both literally.
        concept(self.v, "c1", "Evil", tags("solid"), statement="**Statement:** <!--<script> x")
        html = self.build_html()
        self.assertNotIn("<!--<script", html, "<!--<script> survives in the page payload")

    def test_core_marker_in_statement_not_replaced(self):
        concept(self.v, "c1", "Mk", tags("solid"), statement="**Statement:** literally /*CORE*/ and /*DATA*/ and /*STYLES*/ end")
        html = self.build_html()
        data = self.extract_data(html)
        self.assertEqual(data["nodes"][0]["statement"], "literally /*CORE*/ and /*DATA*/ and /*STYLES*/ end")
        self.assertEqual(html.count("function StudyGraphFactory"), 1, "CORE injected twice")
        self.assertEqual(html.count(".sg-canvas {") + html.count(".sg-canvas{"), (html.count(".sg-canvas {") + html.count(".sg-canvas{")))  # sanity
        css = (TOOLS / "styles.css").read_text(encoding="utf-8")
        self.assertEqual(html.count(css), 1, "styles injected more than once")

    def test_marker_in_name_and_alias(self):
        concept(self.v, "c1", "Alpha", tags("solid"), fm_extra="aliases: [\"/*CORE*/\"]\n")
        html = self.build_html()
        self.assertEqual(html.count("function StudyGraphFactory"), 1)
        self.assertIn("/*CORE*/", html)

    def test_u2028_escaped(self):
        # Notes are split with str.splitlines(), so U+2028 cannot arrive through a note; call render_html directly.
        data = {"nodes": [{"id": "a", "name": "a\u2028b\u2029c", "course": "c1", "status": "solid", "kind": "",
                           "statement": "x\u2028y </script>", "aliases": [], "slide": ""}], "edges": [], "vault": "v"}
        (self.v / "data.json").write_text(json.dumps(data), encoding="utf-8")
        code = ("import json,sys; sys.path.insert(0, r'%s'); import study_graph; "
                "d=json.load(open(r'%s', encoding='utf-8')); "
                "open(r'%s','w',encoding='utf-8').write(study_graph.render_html(d))"
                % (self.v / "scripts", self.v / "data.json", self.v / "page.html"))
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True, encoding="utf-8", cwd=str(self.v))
        self.assertEqual(r.returncode, 0, r.stderr)
        html = (self.v / "page.html").read_text(encoding="utf-8")
        self.assertNotIn("\u2028", html)
        self.assertNotIn("\u2029", html)
        self.assertIn("\\u2028", html)
        got = self.extract_data(html)
        self.assertEqual(got["nodes"][0]["statement"], "x\u2028y </script>")
        self.assertEqual(got["nodes"][0]["name"], "a\u2028b\u2029c")

    def test_no_concepts_still_valid_page(self):
        html = self.build_html()
        self.assertEqual(self.extract_data(html)["nodes"], [])

    def test_html_is_utf8_with_unicode(self):
        concept(self.v, "c1", "Schö", tags("solid"), statement="**Statement:** Δ")
        self.build_html()
        raw = self.out().read_bytes().decode("utf-8")
        self.assertIn("Schö", raw)

    def test_embedded_core_js_parses_in_node(self):
        concept(self.v, "c1", "Alpha", tags("solid"), statement="**Statement:** </script> /*CORE*/")
        html = self.build_html()
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertEqual(len(scripts), 2)
        (self.v / "core_embedded.js").write_text(scripts[0], encoding="utf-8")
        (self.v / "data_embedded.js").write_text(scripts[1].replace("StudyGraph.createGraphView", "//"), encoding="utf-8")
        r = subprocess.run(["node", "--check", str(self.v / "core_embedded.js")], capture_output=True, encoding="utf-8")
        if r.returncode == 127 or "not found" in (r.stderr or "").lower():
            self.skipTest("node not available")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run(["node", "--check", str(self.v / "data_embedded.js")], capture_output=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)


class Build(Base):
    def main_js(self):
        return self.v / PLUGIN / "main.js"

    def test_check_before_build_fails(self):
        r = self.sg("check-build")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Out of date", r.stdout)

    def test_build_then_check_ok(self):
        r = self.sg("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        for f in ("main.js", "styles.css", "manifest.json"):
            self.assertTrue((self.v / PLUGIN / f).exists(), f)
        r = self.sg("check-build")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("up to date", r.stdout)

    def test_main_js_is_header_core_plugin(self):
        self.sg("build")
        text = self.main_js().read_text(encoding="utf-8")
        self.assertTrue(text.startswith("/* GENERATED by scripts/study_graph.py build"))
        core = (TOOLS / "core.js").read_text(encoding="utf-8").rstrip()
        plugin = (TOOLS / "plugin.js").read_text(encoding="utf-8").rstrip()
        self.assertIn(core, text)
        self.assertTrue(text.index(core) < text.index(plugin))
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn(b"\r\n", self.main_js().read_bytes())

    def test_edit_core_makes_stale(self):
        self.sg("build")
        core = self.v / "tools" / "study-graph" / "core.js"
        core.write_text(core.read_text(encoding="utf-8") + "\n// edit\n", encoding="utf-8")
        r = self.sg("check-build")
        self.assertEqual(r.returncode, 1)
        self.assertIn(".obsidian/plugins/study-graph/main.js", r.stdout)
        self.assertEqual(self.sg("build").returncode, 0)
        self.assertEqual(self.sg("check-build").returncode, 0)

    def test_edit_plugin_styles_manifest_make_stale(self):
        for fname in ("plugin.js", "styles.css", "manifest.json"):
            self.sg("build")
            p = self.v / "tools" / "study-graph" / fname
            orig = p.read_bytes()
            p.write_bytes(orig + b"\n// x\n" if fname != "manifest.json" else orig + b"\n\n ")
            self.assertEqual(self.sg("check-build").returncode, 1, fname)
            p.write_bytes(orig)
            self.assertEqual(self.sg("check-build").returncode, 0, fname + " restored")

    def test_crlf_built_file_still_up_to_date(self):
        self.sg("build")
        for f in ("main.js", "styles.css", "manifest.json"):
            p = self.v / PLUGIN / f
            p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertIn(b"\r\n", self.main_js().read_bytes())
        r = self.sg("check-build")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_crlf_source_still_builds_clean(self):
        for f in ("core.js", "plugin.js"):
            p = self.v / "tools" / "study-graph" / f
            p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.sg("build")
        self.assertNotIn(b"\r\n", self.main_js().read_bytes())
        self.assertEqual(self.sg("check-build").returncode, 0)

    def test_built_file_hand_edited_is_stale(self):
        self.sg("build")
        self.main_js().write_text(self.main_js().read_text(encoding="utf-8") + "// tamper\n", encoding="utf-8")
        self.assertEqual(self.sg("check-build").returncode, 1)

    def test_missing_built_file_is_stale(self):
        self.sg("build")
        (self.v / PLUGIN / "styles.css").unlink()
        r = self.sg("check-build")
        self.assertEqual(r.returncode, 1)
        self.assertIn("styles.css", r.stdout)

    def test_missing_source_file_errors(self):
        (self.v / "tools" / "study-graph" / "plugin.js").unlink()
        r = self.sg("build")
        self.assertNotEqual(r.returncode, 0)

    def test_built_main_js_parses_in_node(self):
        self.sg("build")
        r = subprocess.run(["node", "--check", str(self.main_js())], capture_output=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)


class Cli(Base):
    def test_no_command_is_usage_error(self):
        r = self.sg()
        self.assertEqual(r.returncode, 2)

    def test_unknown_command(self):
        self.assertEqual(self.sg("bogus").returncode, 2)


if __name__ == "__main__":
    unittest.main()
