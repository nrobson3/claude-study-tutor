import json, sys, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *

Q = "Which is right?"
HEAD = "---\ntags: [session]\n---\n# Lesson\nSummary: α β\n\n\n"


def qin(source=None, multi=False, q=Q):
    d = {"questions": [{"question": q, "header": "Check", "multiSelect": multi, "options": [
        {"label": "A", "description": "claim a"}, {"label": "B", "description": "claim b"},
        {"label": "C", "description": "claim c"}, {"label": "I don't know", "description": ""}]}]}
    if source is not None:
        d["metadata"] = {"source": source}
    return d


def jl(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries: f.write(json.dumps(e) + "\n")


def ev(event, sid="S1", **kw):
    d = {"hook_event_name": event, "session_id": sid}; d.update(kw); return json.dumps(d)


class Lesson(unittest.TestCase):
    def setUp(self):
        self.v = mkvault("lesson")
        self.note = self.v / "courses" / "c" / "sessions" / "n.md"
        self.note.parent.mkdir(parents=True)
        self.note.write_bytes((HEAD + "Trailing text no newline").encode("utf-8"))
        self.tp = self.v / "t.jsonl"
        self.errlog = self.v / ".claude" / "state" / "lesson-log-errors.log"
        self.st = self.v / ".claude" / "state"

    def hook(self, payload):
        r = run(self.v, "lesson_log.py", "hook", stdin=payload)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def link(self, sid="S1", tool_id="t1"):
        r = run(self.v, "lesson_log.py", "link", "courses/c/sessions/n.md"); self.assertEqual(r.returncode, 0, r.stderr)
        cmd = "python scripts/lesson_log.py link courses/c/sessions/n.md"
        # The link's printed one-time code must appear in the Bash output for the claim to succeed.
        return self.hook(ev("PostToolUse", sid, tool_name="Bash", tool_use_id=tool_id, tool_input={"command": cmd},
                            tool_response={"stdout": r.stdout, "stderr": ""}, transcript_path=str(self.tp)))

    def base_entries(self):
        return [
            {"type": "api-request-blob", "blob": "x" * 50},
            {"type": "user", "uuid": "u1", "message": {"content": "start the lesson"}},
            {"type": "assistant", "uuid": "a1", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "python scripts/lesson_log.py link courses/c/sessions/n.md"}}]}},
            {"type": "user", "uuid": "u2", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
            {"type": "assistant", "uuid": "a2", "message": {"content": [{"type": "text", "text": "Hello $x^2$ **math**"}]}},
        ]

    def err(self):
        return self.errlog.read_text(encoding="utf-8") if self.errlog.exists() else ""

    def body(self):
        return self.note.read_bytes().decode("utf-8")

    def test_link_writes_pending_and_marker(self):
        r = run(self.v, "lesson_log.py", "link", "courses/c/sessions/n.md"); self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads((self.st / "pending-link.json").read_text())
        self.assertEqual(p["note"], "courses/c/sessions/n.md"); self.assertLess(abs(time.time() - p["created"]), 30)
        self.assertIn("%% lesson-log", self.body())

    def test_link_errors(self):
        self.assertNotEqual(run(self.v, "lesson_log.py", "link", "courses/c/sessions/none.md").returncode, 0)
        self.assertNotEqual(run(self.v, "lesson_log.py", "link", str(SCR / "outside.md")).returncode, 0)
        self.assertNotEqual(run(self.v, "lesson_log.py", "link", "../x.md").returncode, 0)

    def test_full_flow_and_preserve_above(self):
        jl(self.tp, self.base_entries())
        r = self.link(); self.assertEqual(r.stdout, "")
        self.assertTrue((self.st / "links" / "S1.json").exists())
        self.assertFalse((self.st / "pending-link.json").exists())
        b = self.body()
        self.assertIn("> [!quote] You\n> start the lesson", b); self.assertIn("Hello $x^2$ **math**", b)
        self.assertNotIn("api-request-blob", b); self.assertNotIn("lesson_log.py link", b)
        raw = self.note.read_bytes()
        self.assertTrue(raw.startswith((HEAD + "Trailing text no newline").encode("utf-8")),
                        "above-marker region not byte-identical: " + repr(raw[:120]))
        self.assertNotIn(b"\r\n", raw, "CRLF introduced into LF note (Path.write_text on Windows)")

    def test_rerender_keeps_above_and_updates_below(self):
        jl(self.tp, self.base_entries()); self.link()
        b = self.body()
        jl(self.tp, self.base_entries() + [{"type": "user", "uuid": "u3", "message": {"content": "second prompt"}}])
        self.hook(ev("Stop", transcript_path=str(self.tp)))
        b2 = self.body(); self.assertIn("second prompt", b2)
        self.assertEqual(b2.split("%% lesson-log")[0], b.split("%% lesson-log")[0])
        self.assertEqual(b2.count("%% lesson-log"), 1)
        before = self.note.read_bytes(); self.hook(ev("Stop", transcript_path=str(self.tp))); self.assertEqual(before, self.note.read_bytes())
        raw = self.body().replace("Summary: α β", "Summary: edited ✓ \t ")
        self.note.write_bytes(raw.encode("utf-8"))
        self.hook(ev("Stop", transcript_path=str(self.tp)))
        self.assertIn("Summary: edited ✓ \t \n", self.body())
        self.assertEqual(self.err(), "")

    def test_above_bytes_exotic(self):
        above = "---\ntags: [s]\n---\n\ttab  \nline\x0c ff\nu2028 here\n\n\n\n"
        self.note.write_bytes(above.encode("utf-8")); jl(self.tp, self.base_entries()); self.link()
        self.assertTrue(self.body().startswith(above), repr(self.body()[:120]))
        self.hook(ev("Stop", transcript_path=str(self.tp)))
        self.assertTrue(self.body().startswith(above), "above region changed on re-render: " + repr(self.note.read_bytes()[:120]))

    def test_crlf_note(self):
        orig = b"---\r\ntags: [s]\r\n---\r\n# T\r\nbody\r\n"
        self.note.write_bytes(orig); jl(self.tp, self.base_entries()); self.link()
        self.assertTrue(self.note.read_bytes().startswith(orig), "CRLF above region altered: " + repr(self.note.read_bytes()[:80]))

    def test_noise_and_sidechain_and_dupe(self):
        es = self.base_entries()
        es += [{"type": "queue-operation", "x": 1}, {"type": "summary"}, {"type": "assistant", "uuid": "a2", "message": {"content": [{"type": "text", "text": "DUPLICATE"}]}},
               {"type": "assistant", "uuid": "a9", "isSidechain": True, "message": {"content": [{"type": "text", "text": "SIDE"}]}},
               {"type": "user", "uuid": "u9", "isMeta": True, "message": {"content": "METAPROMPT"}}]
        jl(self.tp, es)
        with open(self.tp, "a") as f: f.write("garbage line\n{bad json\n\n")
        self.link(); b = self.body()
        for bad in ("DUPLICATE", "SIDE", "METAPROMPT", "garbage"): self.assertNotIn(bad, b)
        self.assertEqual(self.err(), "")

    def test_system_reminder_stripped(self):
        es = self.base_entries()
        es.append({"type": "user", "uuid": "u5", "message": {"content": "real question<system-reminder>\nSECRET REMINDER\n</system-reminder>"}})
        es.append({"type": "user", "uuid": "u6", "message": {"content": [{"type": "text", "text": "<system-reminder>ONLY REMINDER</system-reminder>"}]}})
        es.append({"type": "user", "uuid": "u7", "message": {"content": "<command-name>/study</command-name><command-args>chem</command-args>"}})
        jl(self.tp, es); self.link(); b = self.body()
        self.assertIn("real question", b); self.assertNotIn("SECRET", b); self.assertNotIn("ONLY REMINDER", b)
        self.assertNotIn("system-reminder", b); self.assertIn("/study chem", b)
        self.hook(ev("UserPromptSubmit", prompt="live prompt <system-reminder>HIDDEN</system-reminder>", transcript_path=str(self.tp)))
        b = self.body(); self.assertIn("live prompt", b); self.assertNotIn("HIDDEN", b)
        # A new prompt that repeats an earlier one is a new message: it shows twice.
        self.hook(ev("UserPromptSubmit", prompt="real question", transcript_path=str(self.tp)))
        self.assertEqual(self.body().count("> real question"), 2)

    def test_start_before_link_excluded(self):
        es = [{"type": "user", "uuid": "p0", "message": {"content": "old prompt"}}, {"type": "assistant", "uuid": "pa", "message": {"content": [{"type": "text", "text": "old reply"}]}}] + self.base_entries()
        jl(self.tp, es); self.link(); b = self.body()
        self.assertNotIn("old prompt", b); self.assertNotIn("old reply", b); self.assertIn("start the lesson", b)

    def grade_event(self, source, answer, multi=False, annotations=None, as_str=False, tid="q1"):
        qi = qin(source, multi)
        resp = {"questions": qi["questions"], "answers": {Q: answer}}
        if annotations: resp["annotations"] = annotations
        return self.hook(ev("PostToolUse", "S1", tool_name="AskUserQuestion", tool_use_id=tid, tool_input=qi,
                            tool_response=json.dumps(resp) if as_str else resp, transcript_path=str(self.tp)))

    def ctx(self, r):
        if not r.stdout: return None
        o = json.loads(r.stdout)["hookSpecificOutput"]; self.assertEqual(o["hookEventName"], "PostToolUse"); return o["additionalContext"]

    def test_grading_correct(self):
        jl(self.tp, self.base_entries()); self.link()
        c = self.ctx(self.grade_event("quiz|B", "B")); self.assertIn("CORRECT", c); self.assertNotIn("INCORRECT", c)
        self.assertIn("[!success] Correct", self.body())

    def test_grading_incorrect(self):
        jl(self.tp, self.base_entries()); self.link()
        c = self.ctx(self.grade_event("quiz|B", "A")); self.assertIn("INCORRECT", c); self.assertIn("the key is B", c)
        self.assertIn("[!failure] Not quite", self.body())

    def test_grading_dontknow(self):
        jl(self.tp, self.base_entries()); self.link()
        c = self.ctx(self.grade_event("quiz|B", "I don't know")); self.assertIn("I DON'T KNOW", c)
        self.assertIn("You didn't know", self.body())

    def test_grading_free_text(self):
        jl(self.tp, self.base_entries()); self.link()
        c = self.ctx(self.grade_event("quiz|B", "it is probably the second")); self.assertIn("FREE TEXT", c)

    def test_grading_no_preference(self):
        jl(self.tp, self.base_entries()); self.link()
        c = self.ctx(self.grade_event("quiz|B", "[No preference]")); self.assertIn("SKIPPED", c or "")
        self.assertIn("Skipped", self.body())

    def test_grading_multiselect(self):
        jl(self.tp, self.base_entries()); self.link()
        c = self.ctx(self.grade_event("quiz|A;;C", ["C", "A"], multi=True, tid="m1")); self.assertIn("CORRECT", c); self.assertNotIn("INCORRECT", c)
        c = self.ctx(self.grade_event("quiz|A;;C", ["A"], multi=True, tid="m2")); self.assertIn("INCORRECT", c)
        c = self.ctx(self.grade_event("quiz|A;;C", ["A", "B"], multi=True, tid="m3")); self.assertIn("INCORRECT", c)

    def test_grading_no_key(self):
        jl(self.tp, self.base_entries()); self.link()
        self.assertIsNone(self.ctx(self.grade_event(None, "B")))
        self.assertIsNone(self.ctx(self.grade_event("other|B", "B", tid="q2")))
        self.assertIn("You answered", self.body())

    def test_grading_variants(self):
        jl(self.tp, self.base_entries()); self.link()
        self.assertIn("CORRECT", self.ctx(self.grade_event("QUIZ|B", "B")) or "")
        self.assertIn("CORRECT", self.ctx(self.grade_event("quiz|B", "B", as_str=True, tid="q12")) or "", "tool_response as JSON string")
        c = self.ctx(self.grade_event("quiz|B", "B", annotations={Q: {"notes": "my note"}}, tid="q13")); self.assertIn("my note", c)
        self.assertIn("Your note: my note", self.body())
        self.assertEqual(self.err(), "")

    def test_question_rendering_and_order_via_transcript(self):
        es = self.base_entries(); qi = qin("quiz|B")
        es.append({"type": "assistant", "uuid": "a3", "message": {"content": [{"type": "text", "text": "Quiz time"}, {"type": "tool_use", "id": "q1", "name": "AskUserQuestion", "input": qi}]}})
        es.append({"type": "user", "uuid": "u4", "toolUseResult": {"questions": qi["questions"], "answers": {Q: "B"}}, "message": {"content": [{"type": "tool_result", "tool_use_id": "q1"}]}})
        es.append({"type": "assistant", "uuid": "a4", "message": {"content": [{"type": "text", "text": "Nice work"}]}})
        jl(self.tp, es); self.link(); b = self.body()
        order = [b.index(s) for s in ("Quiz time", "[!question] Check", "**A.** claim a", "**I don't know**", "[!success] Correct", "Nice work")]
        self.assertEqual(order, sorted(order)); self.assertNotIn("quiz|B", b)

    def test_unlink(self):
        jl(self.tp, self.base_entries()); self.link()
        r = run(self.v, "lesson_log.py", "unlink", "courses/c/sessions/n.md"); self.assertIn("1 session", r.stdout)
        before = self.note.read_bytes(); self.hook(ev("Stop", transcript_path=str(self.tp)))
        self.assertEqual(before, self.note.read_bytes())

    def test_robustness_unlinked(self):
        jl(self.tp, self.base_entries())
        for g in (b"", b"garbage", b"\xff\xfe\x00", b"[]", b"123", b"null", b'"str"', b"{}", b'{"session_id": 5}', b'{"session_id":"x","hook_event_name":"Stop"}'):
            r = run(self.v, "lesson_log.py", "hook", stdin=g); self.assertEqual(r.returncode, 0, g); self.assertEqual(r.stdout.strip(), "", g)
        r = self.hook(ev("Stop", sid="unlinked", transcript_path=str(self.tp))); self.assertEqual(r.stdout, "")
        r = self.hook(ev("PostToolUse", sid="unlinked", tool_name="AskUserQuestion", tool_input=qin("quiz|B"), tool_response={"answers": {Q: "B"}})); self.assertEqual(r.stdout, "")
        self.assertEqual(self.err(), "", self.err())

    def test_robust_weird_payloads_linked(self):
        jl(self.tp, self.base_entries()); self.link()
        bad = [
            ev("PostToolUse", tool_name="AskUserQuestion", tool_input="notadict", tool_response="plain"),
            ev("PostToolUse", tool_name="AskUserQuestion", tool_input={"questions": [{"question": Q}], "metadata": {"source": "quiz|B"}}, tool_response={"answers": {Q: "B"}}),
            ev("PostToolUse", tool_name="AskUserQuestion", tool_input={"questions": "x", "metadata": {"source": "quiz|B"}}, tool_response={"answers": {Q: "B"}}),
            ev("PostToolUse", tool_name="AskUserQuestion", tool_input=qin("quiz|"), tool_response={"answers": {Q: "B"}}),
            ev("PostToolUse", tool_name="AskUserQuestion", tool_input=qin("quiz|B||A"), tool_response={"answers": {Q: "B"}}),
            ev("PostToolUse", tool_name="AskUserQuestion", tool_input=qin("quiz|B"), tool_response=None),
            ev("PostToolUse", tool_name="AskUserQuestion", tool_input=qin("quiz|B"), tool_response=[1, 2]),
            ev("PreToolUse", tool_name="AskUserQuestion", tool_input=None),
            ev("UserPromptSubmit"),
            ev("UserPromptSubmit", prompt=None),
            ev("UserPromptSubmit", prompt=["a"]),
        ]
        for b in bad: self.hook(b)
        e = self.err()
        self.assertEqual(e, "", "exceptions logged:\n" + e[-1500:])

    def test_missing_transcript(self):
        jl(self.tp, self.base_entries()); self.link()
        before = self.note.read_bytes()
        r = self.hook(ev("Stop", transcript_path=str(self.v / "nonexistent.jsonl"))); self.assertEqual(r.stdout, "")
        r = self.hook(ev("Stop")); self.assertEqual(r.stdout, "")
        self.assertEqual(self.err(), "")
        after = self.note.read_bytes()
        self.assertEqual(before.split(b"%% lesson-log")[0], after.split(b"%% lesson-log")[0])
        self.assertIn(b"start the lesson", after, "note body wiped when transcript missing")

    def test_stale_pending(self):
        jl(self.tp, self.base_entries())
        run(self.v, "lesson_log.py", "link", "courses/c/sessions/n.md")
        pj = self.st / "pending-link.json"; d = json.loads(pj.read_text()); d["created"] = time.time() - 400; pj.write_text(json.dumps(d))
        r = self.hook(ev("PostToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": "python scripts/lesson_log.py link x"}, transcript_path=str(self.tp)))
        self.assertEqual(r.stdout, ""); self.assertFalse((self.st / "links" / "S1.json").exists()); self.assertFalse(pj.exists())

    def test_pending_not_claimed_by_other_bash(self):
        run(self.v, "lesson_log.py", "link", "courses/c/sessions/n.md")
        self.hook(ev("PostToolUse", tool_name="Bash", tool_input={"command": "ls"}, transcript_path=str(self.tp)))
        self.assertTrue((self.st / "pending-link.json").exists())
        self.assertFalse((self.st / "links" / "S1.json").exists())

    def test_note_deleted_after_link(self):
        jl(self.tp, self.base_entries()); self.link(); self.note.unlink()
        r = self.hook(ev("Stop", transcript_path=str(self.tp))); self.assertEqual(r.stdout, ""); self.assertEqual(self.err(), "")
        self.assertFalse(self.note.exists(), "hook must not recreate the deleted note")
        r = self.grade_event("quiz|B", "B"); self.assertIn("CORRECT", self.ctx(r) or "")
        self.assertFalse(self.note.exists())

    def test_marker_removed_by_user(self):
        jl(self.tp, self.base_entries()); self.link()
        t = self.body(); i = t.index("%% lesson-log"); self.note.write_bytes(t[:i].encode("utf-8"))
        self.hook(ev("Stop", transcript_path=str(self.tp))); self.assertIn("%% lesson-log", self.body()); self.assertEqual(self.err(), "")

    def test_two_sessions_two_notes(self):
        jl(self.tp, self.base_entries()); self.link("S1")
        n2 = self.v / "courses" / "c" / "sessions" / "m.md"; n2.write_text("# m\n", encoding="utf-8")
        out = run(self.v, "lesson_log.py", "link", "courses/c/sessions/m.md").stdout
        self.hook(ev("PostToolUse", "S2", tool_name="Bash", tool_use_id="t1", tool_input={"command": "python scripts/lesson_log.py link courses/c/sessions/m.md"},
                     tool_response={"stdout": out}, transcript_path=str(self.tp)))
        self.assertTrue((self.st / "links" / "S2.json").exists())
        self.assertIn("start the lesson", n2.read_text(encoding="utf-8"))

    def test_session_id_path_traversal(self):
        self.hook(ev("Stop", sid="../../evil", transcript_path=str(self.tp)))
        self.hook(ev("PostToolUse", sid="../../evil", tool_name="Bash", tool_input={"command": "python scripts/lesson_log.py link n"}))
        self.assertEqual(self.err(), "")
        self.assertFalse((self.v.parent / "evil.json").exists())

    def test_cli_render(self):
        jl(self.tp, self.base_entries()); self.link()
        r = run(self.v, "lesson_log.py", "render", "S1"); self.assertIn("Rendered", r.stdout)
        r = run(self.v, "lesson_log.py", "render", "nope"); self.assertNotEqual(r.returncode, 0)
        r = run(self.v, "lesson_log.py"); self.assertNotEqual(r.returncode, 0)

    def test_timing_20mb(self):
        big = "word " * 400
        i = 0; size = 0
        with open(self.tp, "w", encoding="utf-8") as f:
            for e in self.base_entries(): f.write(json.dumps(e) + "\n")
            while size < 20 * 1024 * 1024:
                for e in ({"type": "user", "uuid": f"bu{i}", "message": {"content": f"prompt {i} " + big}},
                          {"type": "assistant", "uuid": f"ba{i}", "message": {"content": [{"type": "text", "text": f"reply {i} " + big}]}},
                          {"type": "api-request-blob", "blob": big * 5}):
                    s = json.dumps(e) + "\n"; f.write(s); size += len(s)
                i += 1
        self.link()
        t = time.time(); self.hook(ev("Stop", transcript_path=str(self.tp))); dt = time.time() - t
        print(f"\nTIMING hook on {self.tp.stat().st_size/1e6:.1f} MB transcript ({i} turns): {dt:.2f}s; note {self.note.stat().st_size/1e6:.1f} MB")
        self.assertEqual(self.err(), "")
        self.assertLess(dt, 10, "hook too slow")


if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
