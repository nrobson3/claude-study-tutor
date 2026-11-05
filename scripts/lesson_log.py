#!/usr/bin/env python3
"""Mirror a study session into its lesson note, so Obsidian renders the math.

Commands
    link <note>      Run by Claude (via Bash) at the start of a lesson. The note
                     must be a session note (courses/<c>/sessions/*.md) with no
                     lesson content yet. The PostToolUse hook on that same Bash
                     call binds the note to the session: it checks the Bash
                     output for the one-time code this command prints.
    unlink <note>    Stop updating a note.
    hook             Hook entry point: reads the hook JSON on stdin. Registered
                     in .claude/settings.json for UserPromptSubmit,
                     PreToolUse(AskUserQuestion), PostToolUse(AskUserQuestion|Bash)
                     and Stop. Always exits 0 and never blocks a tool.
    render <session> Re-render a linked note from its transcript (debugging).

The note has two parts. Everything above the marker line belongs to Claude
(title, summary). Everything below it is rebuilt from the session transcript:
your messages, Claude's text, quiz questions (written before you answer) and
the graded answers.

Quiz convention (see .claude/skills/study/references/quizzes.md): an
AskUserQuestion call whose options are "A", "B", "C" (claims in the
descriptions) plus "I don't know", with metadata.source = "quiz|B". This hook
grades the answer, writes it into the note and tells Claude the grade.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
STATE = VAULT / ".claude" / "state"
PENDING = STATE / "pending-link.json"
LINKS = STATE / "links"
ERRORS = STATE / "lesson-log-errors.log"
MARKER = "%% lesson-log: everything below this line is rebuilt automatically. Don't edit it. %%"
MARKER_PREFIX = "%% lesson-log"
PENDING_MAX_AGE = 300  # seconds
TIME_BUDGET = 10.0  # seconds; the hook timeout is 15
DONT_KNOW = "i don't know"
QUIZ_PREFIX = "quiz|"
STARTED = time.monotonic()

TAG_BLOCKS = re.compile(
    r"<(system-reminder|local-command-stdout|local-command-stderr|command-message|"
    r"user-prompt-submit-hook|pasted_content[^>]*)>.*?</\1\s*>",
    re.S,
)
ANY_TAG = re.compile(r"</?[a-zA-Z][\w-]*(?:\s[^<>]*)?>")
ENTRY_TYPE = re.compile(r'"type":\s?"(?:user|assistant)"')


class OutOfTime(Exception):
    pass


def check_time() -> None:
    if time.monotonic() - STARTED > TIME_BUDGET:
        raise OutOfTime()


def norm(label: str) -> str:
    """Compare labels case-insensitively and with straight apostrophes."""
    return str(label).replace("’", "'").replace("‘", "'").strip().lower()


# ---------------------------------------------------------------- state ----

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _safe_id(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id))[:120] or "unknown"


def link_file(session_id: str) -> Path:
    return LINKS / f"{_safe_id(session_id)}.json"


def resolve_note(arg: str) -> Path:
    p = Path(arg)
    if not p.is_absolute():
        p = VAULT / p
    p = p.resolve()
    try:
        rel = p.relative_to(VAULT)
    except ValueError:
        sys.exit(f"Note must be inside the vault: {p}")
    parts = rel.parts
    if len(parts) != 4 or parts[0] != "courses" or parts[2] != "sessions" or p.suffix.lower() != ".md":
        sys.exit(f"Lesson notes live in courses/<course>/sessions/<name>.md, not {rel.as_posix()}")
    return p


MARKER_LINE = re.compile(r"(?m)^%% lesson-log[^\r\n]*")


def read_raw(path: Path) -> str:
    """Read without newline translation, so the part above the marker round-trips byte for byte."""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write_raw(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def body_below_marker(text: str) -> str | None:
    m = MARKER_LINE.search(text)
    if m is None:
        return None
    return text[m.end():].strip()


# ------------------------------------------------------------- commands ----

def cmd_link(note_arg: str) -> None:
    note = resolve_note(note_arg)
    if not note.is_file():
        sys.exit(f"Create the note first (from templates/session.md): {note}")
    text = read_raw(note)
    below = body_below_marker(text)
    if below:
        sys.exit("That note already holds a lesson. Start a new note (e.g. add ' (2)' to the name) "
                 "so the earlier lesson isn't overwritten.")
    if below is None:
        nl = "\r\n" if "\r\n" in text else "\n"
        sep = nl if text.endswith("\n") else nl + nl
        write_raw(note, text + sep + MARKER + nl)
    nonce = secrets.token_hex(6)
    rel = note.relative_to(VAULT).as_posix()
    _write_json(PENDING, {"note": rel, "created": time.time(), "nonce": nonce})
    print(f"Lesson log linked: {rel} [{nonce}]")


def cmd_unlink(note_arg: str) -> None:
    note = resolve_note(note_arg).relative_to(VAULT).as_posix()
    removed = 0
    if LINKS.is_dir():
        for f in LINKS.glob("*.json"):
            data = _read_json(f)
            if data and data.get("note") == note:
                f.unlink()
                removed += 1
    print(f"Unlinked {note} from {removed} session(s).")


def is_link_command(command: str) -> bool:
    """True if the shell command runs `lesson_log.py link ...` (Bash or PowerShell syntax)."""
    for posix in (True, False):
        try:
            argv = [a.strip("'\"") for a in shlex.split(command, posix=posix)]
        except ValueError:
            continue
        for i, arg in enumerate(argv[:-1]):
            if arg.replace("\\", "/").endswith("lesson_log.py") and argv[i + 1] == "link":
                return True
    return False


def claim_pending(session_id: str, data: dict) -> bool:
    """Bind the pending link to this session if this Bash call is the one that created it."""
    pending = _read_json(PENDING)
    if not pending:
        return False
    try:
        age = time.time() - float(pending.get("created", 0))
    except (TypeError, ValueError):
        age = PENDING_MAX_AGE + 1
    if age > PENDING_MAX_AGE:
        PENDING.unlink(missing_ok=True)
        return False
    tool_input = data.get("tool_input")
    command = str(tool_input.get("command", "")) if isinstance(tool_input, dict) else ""
    if not is_link_command(command):
        return False
    nonce = str(pending.get("nonce", ""))
    response = data.get("tool_response")
    output = response if isinstance(response, str) else json.dumps(response)
    if not nonce or f"[{nonce}]" not in output:
        return False
    _write_json(link_file(session_id), {
        "note": pending["note"],
        "transcript_path": data.get("transcript_path"),
        "start_tool_use_id": data.get("tool_use_id"),
        "linked_at": time.time(),
    })
    PENDING.unlink(missing_ok=True)
    return True


# ----------------------------------------------------------- transcript ----

def read_transcript(path: str | None) -> list[dict]:
    if not path:
        return []
    entries, seen = [], set()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f):
                if n % 200 == 0:
                    check_time()
                # Cheap prefilter: most lines (api blobs, snapshots) are neither.
                if not ENTRY_TYPE.search(line):
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(e, dict) or e.get("type") not in ("user", "assistant"):
                    continue
                if e.get("isSidechain") or e.get("isCompactSummary"):
                    continue
                uid = e.get("uuid")
                if uid:
                    if uid in seen:
                        continue
                    seen.add(uid)
                entries.append(e)
    except OSError:
        return []
    return entries


def clean_user_text(content) -> str:
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif block.get("type") == "image":
                parts.append("_(image attached)_")
        text = "\n".join(parts)
    else:
        text = str(content or "")
    m = re.search(r"<command-name>\s*(.*?)\s*</command-name>", text, re.S)
    if m:
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
        return (m.group(1) + (" " + args.group(1).strip() if args and args.group(1).strip() else "")).strip()
    text = TAG_BLOCKS.sub("", text)
    text = ANY_TAG.sub("", text) if text.lstrip().startswith("<") else text
    text = text.strip()
    if text.startswith("Caveat: The messages below were generated"):
        return ""
    return text


def has_tool_result(content) -> bool:
    return isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def is_prompt(entry: dict) -> bool:
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    content = (entry.get("message") or {}).get("content")
    return not has_tool_result(content) and bool(clean_user_text(content))


def entry_time(entry: dict) -> float | None:
    ts = entry.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def find_start(entries: list[dict], link: dict) -> int:
    """Index of the user prompt that preceded the link command."""
    tool_use_id = link.get("start_tool_use_id")
    target = None
    for i, e in enumerate(entries):
        if e.get("type") != "assistant":
            continue
        for b in (e.get("message") or {}).get("content") or []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            if tool_use_id and b.get("id") == tool_use_id:
                target = i
            elif not tool_use_id and is_link_command(str((b.get("input") or {}).get("command", ""))):
                target = i
    if target is None:
        # Fall back to the last prompt sent before the link was made.
        linked_at = link.get("linked_at")
        if isinstance(linked_at, (int, float)):
            for i in range(len(entries) - 1, -1, -1):
                t = entry_time(entries[i])
                if is_prompt(entries[i]) and t is not None and t <= linked_at:
                    return i
        return 0
    for i in range(target, -1, -1):
        if is_prompt(entries[i]):
            return i
    return 0


def tool_result_text(block: dict) -> str:
    c = block.get("content")
    if isinstance(c, list):
        return "\n".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
    return str(c or "")


def build_blocks(entries: list[dict], start: int) -> list[tuple]:
    blocks: list[tuple] = []
    asked: set = set()
    claude_buf: list[str] = []

    def flush():
        if claude_buf:
            blocks.append(("claude", "\n\n".join(claude_buf)))
            claude_buf.clear()

    for e in entries[start:]:
        content = (e.get("message") or {}).get("content")
        if e.get("type") == "user":
            if has_tool_result(content):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in asked:
                        flush()
                        result = e.get("toolUseResult")
                        if b.get("is_error") or not isinstance(result, dict):
                            result = {"dismissed": True, "text": tool_result_text(b)}
                        blocks.append(("answer", b["tool_use_id"], result))
                continue
            if e.get("isMeta"):
                continue
            text = clean_user_text(content)
            if text:
                flush()
                blocks.append(("you", text))
        else:
            for b in content or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and str(b.get("text", "")).strip():
                    claude_buf.append(str(b["text"]).strip())
                elif b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
                    flush()
                    asked.add(b.get("id"))
                    blocks.append(("question", b.get("id"), b.get("input") or {}))
    flush()
    return blocks


def same_question(block: tuple, qid, qinput) -> bool:
    return block[0] == "question" and ((qid is not None and block[1] == qid) or block[2] == qinput)


def add_extras(blocks: list[tuple], extra: dict) -> list[tuple]:
    if "prompt" in extra:
        text = clean_user_text(extra["prompt"])
        # Only skip it if the transcript already ends with this very prompt.
        if text and not (blocks and blocks[-1][0] == "you" and blocks[-1][1] == text):
            blocks.append(("you", text))
    if "question" in extra:
        qid, qinput = extra["question"]
        if not any(same_question(b, qid, qinput) for b in blocks):
            blocks.append(("question", qid, qinput))
    if "answer" in extra:
        qid, qinput, result = extra["answer"]
        if not any(b[0] == "answer" and b[1] == qid for b in blocks):
            if not any(same_question(b, qid, qinput) for b in blocks):
                blocks.append(("question", qid, qinput))
            pos = max(i for i, b in enumerate(blocks) if same_question(b, qid, qinput))
            blocks.insert(pos + 1, ("answer", qid, result if isinstance(result, dict) else {"text": str(result)}))
    return blocks


# -------------------------------------------------------------- grading ----

def quiz_keys(qinput: dict) -> list[list[str]] | None:
    """Per-question answer keys from metadata.source ("quiz|B", "quiz|B||A;;C")."""
    meta = (qinput or {}).get("metadata") if isinstance(qinput, dict) else None
    source = str((meta or {}).get("source", "")) if isinstance(meta, dict) else ""
    if not source.lower().startswith(QUIZ_PREFIX):
        return None
    body = source[len(QUIZ_PREFIX):]
    keys = [[k.strip() for k in part.split(";;") if k.strip()] for part in body.split("||")]
    return keys if any(keys) else None


def split_choices(given, labels: list[str]) -> list[str]:
    if isinstance(given, list):
        return [str(x) for x in given]
    if given is None:
        return []
    text = str(given)
    normed = {norm(l) for l in labels}
    if norm(text) not in normed and "," in text:
        parts = [p.strip() for p in text.split(",")]
        if parts and all(norm(p) in normed for p in parts):
            return parts
    return [text]


def grade(qinput: dict, result: dict) -> list[dict]:
    """One grade per question: status in correct|incorrect|dontknow|free|skipped|ungraded."""
    qinput = qinput if isinstance(qinput, dict) else {}
    result = result if isinstance(result, dict) else {}
    questions = qinput.get("questions") or result.get("questions") or []
    answers = result.get("answers") or qinput.get("answers") or {}
    annotations = result.get("annotations") or qinput.get("annotations") or {}
    if not isinstance(answers, dict):
        answers = {}
    if not isinstance(annotations, dict):
        annotations = {}
    keys = quiz_keys(qinput)
    grades = []
    for n, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        text = str(q.get("question", ""))
        options = [o for o in (q.get("options") or []) if isinstance(o, dict)]
        labels = [str(o.get("label", "")) for o in options]
        chosen = split_choices(answers.get(text), labels)
        note = ""
        ann = annotations.get(text)
        if isinstance(ann, dict):
            note = str(ann.get("notes") or "").strip()
        key = keys[n] if keys and n < len(keys) and keys[n] else None
        g = {"question": text, "chosen": chosen, "key": key, "note": note, "options": options}
        normed_labels = {norm(l) for l in labels}
        if result.get("dismissed") or not chosen or chosen == ["[No preference]"]:
            g["status"] = "skipped"
        elif any(norm(c) == DONT_KNOW for c in chosen):
            g["status"] = "dontknow"
        elif key is None:
            g["status"] = "ungraded"
        elif not all(norm(c) in normed_labels for c in chosen):
            g["status"] = "free"
        else:
            g["status"] = "correct" if sorted(map(norm, chosen)) == sorted(map(norm, key)) else "incorrect"
        grades.append(g)
    return grades


def describe(label: str, options: list[dict]) -> str:
    for o in options:
        if norm(o.get("label", "")) == norm(label):
            desc = str(o.get("description") or "").strip()
            shown = str(o.get("label", label))
            if desc and len(shown) <= 2:
                return f"**{shown}.** {desc}"
            return f"**{shown}**" + (f": {desc}" if desc else "")
    return label


# ------------------------------------------------------------ rendering ----

def safe(text: str) -> str:
    """Keep Claude's or her text from opening an Obsidian comment (%%)."""
    return str(text).replace("%%", "%​%")


def quote(text: str) -> list[str]:
    return [("> " + line) if line.strip() else ">" for line in safe(text).splitlines()]


def render_question(qinput: dict) -> str:
    out = []
    is_quiz = quiz_keys(qinput) is not None
    for q in (qinput or {}).get("questions") or []:
        if not isinstance(q, dict):
            continue
        header = str(q.get("header") or ("Check" if is_quiz else "Question"))
        lines = [f"> [!question] {safe(header)}"]
        lines += quote(str(q.get("question", "")))
        options = [o for o in (q.get("options") or []) if isinstance(o, dict)]
        if options:
            lines.append(">")
            for o in options:
                label = str(o.get("label", ""))
                desc = safe(str(o.get("description") or "").strip())
                if norm(label) == DONT_KNOW:
                    lines.append(f"> **{safe(label)}**")
                elif is_quiz and len(label) <= 2:
                    lines.append(f"> **{safe(label)}.** {desc}")
                else:
                    lines.append(f"> - **{safe(label)}**" + (f": {desc}" if desc else ""))
        out.append("\n".join(lines))
    return "\n\n".join(out)


def render_answer(qinput: dict, result: dict) -> str:
    result = result if isinstance(result, dict) else {}
    if result.get("dismissed"):
        return "> [!warning] Question dismissed"
    if "answers" not in result and "text" in result:
        return "\n".join(["> [!example] Your answer"] + quote(result["text"]))
    out = []
    for g in grade(qinput, result):
        opts = g["options"]
        chosen = ", ".join(describe(c, opts) for c in g["chosen"]) if g["chosen"] else ""
        key = ", ".join(describe(k, opts) for k in (g["key"] or []))
        s = g["status"]
        if s == "correct":
            lines = ["> [!success] Correct ✓"] + quote(f"You chose {chosen}")
        elif s == "incorrect":
            lines = ["> [!failure] Not quite ✗"] + quote(f"You chose {chosen}") + quote(f"Answer: {key}")
        elif s == "dontknow":
            lines = ["> [!question] You didn't know"] + (quote(f"Answer: {key}") if key else [])
        elif s == "skipped":
            lines = ["> [!warning] Skipped"]
        elif s == "free":
            lines = ["> [!example] Your answer (Claude grades it below)"] + quote(", ".join(g["chosen"]))
        else:
            lines = ["> [!example] You answered"] + quote(", ".join(g["chosen"]))
        if g["note"]:
            lines.append(">")
            lines += quote("Your note: " + g["note"])
        out.append("\n".join(lines))
    return "\n\n".join(out)


def render_blocks(blocks: list[tuple]) -> str:
    questions = {b[1]: b[2] for b in blocks if b[0] == "question"}
    parts = []
    for b in blocks:
        if b[0] == "you":
            parts.append("\n".join(["> [!quote] You"] + quote(b[1])))
        elif b[0] == "claude":
            parts.append(safe(b[1]))
        elif b[0] == "question":
            parts.append(render_question(b[2]))
        elif b[0] == "answer":
            parts.append(render_answer(questions.get(b[1], {}), b[2]))
    return "\n\n".join(p for p in parts if p.strip())


def write_note(note: Path, body: str) -> None:
    text = read_raw(note) if note.exists() else ""
    nl = "\r\n" if "\r\n" in text else "\n"
    m = MARKER_LINE.search(text)
    # Everything up to the end of the marker line is kept exactly as it is.
    head = text[: m.end()] if m else (text.rstrip("\r\n") + nl + nl + MARKER)
    new = head + nl + nl + body.rstrip("\n").replace("\n", nl) + nl
    if new == text:
        return
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = STATE / f"note-{os.getpid()}-{secrets.token_hex(3)}.tmp"
    write_raw(tmp, new)
    try:
        for attempt in range(5):
            try:
                os.replace(tmp, note)
                return
            except PermissionError:  # Windows: another program has the file open
                time.sleep(0.1 * (attempt + 1))
        raise PermissionError(f"could not replace {note} after 5 tries")
    finally:
        tmp.unlink(missing_ok=True)


def render_link(link: dict, transcript_path: str | None, extra: dict) -> None:
    note = VAULT / str(link.get("note", ""))
    if not note.is_file():
        return
    entries = read_transcript(transcript_path or link.get("transcript_path"))
    start = find_start(entries, link)
    blocks = add_extras(build_blocks(entries, start), extra)
    body = render_blocks(blocks)
    check_time()  # out of time: skip the write rather than half-render
    write_note(note, body)


def grade_context(qinput: dict, result) -> str | None:
    if quiz_keys(qinput) is None or not isinstance(result, dict):
        return None
    notes = []
    for g in grade(qinput, result):
        key = ", ".join(g["key"] or [])
        if g["status"] in ("correct", "incorrect"):
            notes.append(f"{g['status'].upper()}: she chose {', '.join(g['chosen'])}; the key is {key}.")
        elif g["status"] == "dontknow":
            notes.append(f"I DON'T KNOW: she chose not to guess; the key is {key}.")
        elif g["status"] == "free":
            notes.append(f"FREE TEXT (grade it yourself against the key {key}): {', '.join(g['chosen'])}")
        elif g["status"] == "skipped":
            notes.append("SKIPPED: she dismissed the question.")
        if g["note"]:
            notes.append(f"Her note: {g['note']}")
    if not notes:
        return None
    return "Lesson log graded the quiz. " + " ".join(notes) + " Respond to this grade; don't re-grade it."


def cmd_hook() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    event = data.get("hook_event_name")
    session_id = data.get("session_id")
    tool = data.get("tool_name")
    if not session_id:
        return
    claimed = False
    if event == "PostToolUse" and tool in ("Bash", "PowerShell"):
        claimed = claim_pending(session_id, data)
        if not claimed:
            return  # other shell calls don't change what the note shows
    link = _read_json(link_file(session_id))
    if not link:
        return
    extra: dict = {}
    qinput, result = None, None
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if event == "UserPromptSubmit":
        extra["prompt"] = str(data.get("prompt") or "")
    elif event == "PreToolUse" and tool == "AskUserQuestion":
        extra["question"] = (data.get("tool_use_id"), tool_input)
    elif event == "PostToolUse" and tool == "AskUserQuestion":
        qinput = tool_input
        result = data.get("tool_response")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except ValueError:
                result = {"text": result}
        extra["answer"] = (data.get("tool_use_id"), qinput, result)

    try:
        render_link(link, data.get("transcript_path"), extra)
    except OutOfTime:
        log_error("render skipped: over the time budget")
    except Exception:
        log_error()

    if qinput is not None:
        try:
            ctx = grade_context(qinput, result)
        except Exception:
            log_error()
            ctx = None
        if ctx:
            out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ctx}}
            try:
                sys.stdout.write(json.dumps(out))
                sys.stdout.flush()
            except OSError:
                pass


def log_error(message: str | None = None) -> None:
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        with ERRORS.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + (message or traceback.format_exc()) + "\n")
    except OSError:
        pass


def main(argv: list[str]) -> None:
    if len(argv) >= 1 and argv[0] == "hook":
        try:
            cmd_hook()
        except Exception:
            log_error()
        try:
            sys.stdout.flush()
        except OSError:
            pass
        os._exit(0)  # never let shutdown errors turn into a non-zero hook exit
    if len(argv) == 2 and argv[0] == "link":
        cmd_link(argv[1])
    elif len(argv) == 2 and argv[0] == "unlink":
        cmd_unlink(argv[1])
    elif len(argv) == 2 and argv[0] == "render":
        link = _read_json(link_file(argv[1]))
        if not link:
            sys.exit(f"No link for session {argv[1]}")
        render_link(link, None, {})
        print(f"Rendered {link['note']}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
