#!/usr/bin/env python3
"""Knowledge graph tools for the study vault.

The graph is the set of concept notes in courses/<c>/concepts/. Each note
links to the concepts it follows from; Obsidian's graph view draws them,
coloured by status (see .obsidian/graph.json).

Commands
    maps [course]
        Rebuild courses/<c>/map.md for each course: concepts grouped by
        status with their one-line statements, links into other courses, and
        slide decks no session or concept has touched yet. Runs on every
        `sync.py push`, so the maps never go stale.
    check [course]
        Lint the graph: missing or conflicting status, broken links, duplicate
        names or aliases, missing statements, circular "follows from" chains.
        Exits 1 when it finds problems.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
COURSES = VAULT / "courses"
STATUSES = ("shaky", "not-yet", "solid")  # order used in maps
STATUS_LABEL = {"solid": "Solid", "shaky": "Shaky", "not-yet": "Not yet"}
# [[target]], [[target#heading]], [[target|alias]]; in tables the pipe is escaped as \|.
WIKILINK = re.compile(r"(!?)\[\[([^\]|#\\]+)(?:#[^\]|\\]*)?(?:\\?\|[^\]]*)?\]\]")


@dataclass
class Concept:
    path: Path
    course: str  # folder it lives in
    name: str
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    declared_course: str | None = None
    statement: str = ""
    follows_from: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    kind: str = ""
    slide: str = ""  # first link on the **Slides:** line, e.g. "courses/c/slides/L1.pdf#page=3"

    @property
    def statuses(self) -> list[str]:
        return [t.split("/", 1)[1] for t in self.tags if t.startswith("status/")]

    @property
    def status(self) -> str | None:
        s = self.statuses
        return s[0] if len(s) == 1 else None


def parse_list(value: str) -> list[str]:
    """Inline YAML list: [a, "b, c", 'd'] -> ['a', 'b, c', 'd']. Commas inside quotes are kept."""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    items, buf, quote = [], [], None
    for ch in value:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf.append(ch)
        elif ch in "'\"":
            quote = ch
        elif ch == ",":
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    items.append("".join(buf))
    return [v.strip().lstrip("#") for v in items if v.strip()]


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    data: dict[str, object] = {}
    key = None
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            return data, "\n".join(lines[i + 1:])
        if re.match(r"^\s*-\s+", line) and key:
            item = line.split("-", 1)[1].strip().strip("'\"").lstrip("#")
            existing = data.get(key)
            if not isinstance(existing, list):
                existing = []
            existing.append(item)
            data[key] = existing
            continue
        k, sep, v = line.partition(":")
        if not sep:
            continue
        key = k.strip()
        v = v.strip()
        if key in ("tags", "aliases"):
            data[key] = parse_list(v) if v else []
        else:
            data[key] = v.strip("'\"")
    return {}, text  # unterminated frontmatter: treat as none


def link_targets(text: str) -> list[str]:
    out = []
    for m in WIKILINK.finditer(text):
        target = m.group(2).strip()
        if target:
            out.append(target)
    return out


def load_concepts(course_filter: str | None = None) -> list[Concept]:
    concepts = []
    if not COURSES.is_dir():
        return concepts
    for course in sorted(p for p in COURSES.iterdir() if p.is_dir()):
        if course_filter and course.name != course_filter:
            continue
        folder = course / "concepts"
        if not folder.is_dir():
            continue
        for md in sorted(folder.glob("*.md")):
            text = md.read_text(encoding="utf-8-sig")
            fm, body = parse_frontmatter(text)
            c = Concept(path=md, course=course.name, name=md.stem)
            tags = fm.get("tags")
            c.tags = list(tags) if isinstance(tags, list) else []
            aliases = fm.get("aliases")
            c.aliases = list(aliases) if isinstance(aliases, list) else []
            dc = fm.get("course")
            c.declared_course = dc if isinstance(dc, str) and dc else None
            kind = fm.get("kind")
            c.kind = kind if isinstance(kind, str) else ""
            for line in body.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("**statement:**"):
                    c.statement = stripped.split(":**", 1)[1].strip()
                elif stripped.lower().startswith("**follows from:**"):
                    c.follows_from = link_targets(stripped)
                elif stripped.lower().startswith("**slides:**") and not c.slide:
                    m = re.search(r"\[\[([^\]|\\]+)", stripped)
                    c.slide = m.group(1).strip() if m else ""
            c.links = link_targets(body)
            concepts.append(c)
    return concepts


def all_note_names() -> dict[str, Path]:
    """Lower-cased basename (no .md) and vault-relative path -> file, for link resolution."""
    names: dict[str, Path] = {}
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for fname in files:
            p = Path(root) / fname
            rel = p.relative_to(VAULT)
            names[rel.as_posix().lower()] = p
            if p.suffix.lower() == ".md":
                names[rel.with_suffix("").as_posix().lower()] = p
                names.setdefault(p.stem.lower(), p)
            else:
                names.setdefault(p.name.lower(), p)
    return names


def concept_index(concepts: list[Concept]) -> dict[str, Concept]:
    idx: dict[str, Concept] = {}
    for c in concepts:
        idx.setdefault(c.name.lower(), c)
        for a in c.aliases:
            idx.setdefault(a.lower(), c)
    return idx


def course_title(course: Path) -> str:
    info = course / "course.md"
    if info.exists():
        fm, _ = parse_frontmatter(info.read_text(encoding="utf-8"))
        t = fm.get("title")
        if isinstance(t, str) and t:
            return t
    return course.name


def untouched_decks(course: Path) -> list[Path]:
    slides = course / "slides"
    if not slides.is_dir():
        return []
    texts = []
    for sub in ("sessions", "concepts"):
        folder = course / sub
        if folder.is_dir():
            texts.extend(md.read_text(encoding="utf-8-sig") for md in folder.glob("*.md"))
    blob = "\n".join(texts).lower()

    def mentioned(pdf: Path) -> bool:
        return re.search(r"(?<![\w-])" + re.escape(pdf.name.lower()), blob) is not None

    return [pdf for pdf in sorted(slides.rglob("*.pdf")) if not mentioned(pdf)]


def line_for(c: Concept) -> str:
    statement = f" — {c.statement}" if c.statement else ""
    return f"- [[{c.name}]]{statement}"


def cmd_maps(args) -> None:
    every = load_concepts()
    idx = concept_index(every)
    for course in sorted(p for p in COURSES.iterdir() if p.is_dir()):
        if args.course and course.name != args.course:
            continue
        mine = [c for c in every if c.course == course.name]
        by_status = {s: [c for c in mine if c.status == s] for s in STATUSES}
        unknown = [c for c in mine if c.status not in STATUSES]
        counts = " · ".join(f"{len(by_status[s])} {STATUS_LABEL[s].lower()}" for s in ("solid", "shaky", "not-yet"))
        lines = [
            "---",
            "tags: [map]",
            "---",
            f"# {course_title(course)}: map",
            "",
            "Rebuilt by `scripts/graph.py maps` on every sync. Don't edit by hand; edit the concept notes.",
            "",
            f"**{len(mine)} concepts:** {counts}" if mine else "_No concepts yet. They appear as you study topics._",
            "",
        ]
        for s in STATUSES:
            if by_status[s]:
                lines.append(f"## {STATUS_LABEL[s]}")
                lines.extend(line_for(c) for c in sorted(by_status[s], key=lambda c: c.name.lower()))
                lines.append("")
        if unknown:
            lines.append("## Status missing (run `scripts/graph.py check`)")
            lines.extend(line_for(c) for c in unknown)
            lines.append("")
        cross = []
        for c in mine:
            for t in c.follows_from:
                other = idx.get(t.lower())
                if other and other.course != course.name:
                    cross.append(f"- [[{c.name}]] follows from [[{other.name}]] ({other.course})")
        if cross:
            lines.append("## Leans on other courses")
            lines.extend(sorted(set(cross)))
            lines.append("")
        untouched = untouched_decks(course)
        if untouched:
            lines.append("## Slide decks not studied yet")
            for pdf in untouched:
                rel = pdf.relative_to(VAULT).as_posix()
                lines.append(f"- [[{rel}|{pdf.name}]]")
            lines.append("")
        (course / "map.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        print(f"map: {course.name} ({len(mine)} concepts)")


def find_cycles(concepts: list[Concept], idx: dict[str, Concept]) -> list[list[str]]:
    graph = {c.name: [idx[t.lower()].name for t in c.follows_from if t.lower() in idx] for c in concepts}
    cycles, state, stack = [], {}, []

    def visit(n: str) -> None:
        state[n] = 1
        stack.append(n)
        for m in graph.get(n, []):
            if state.get(m) == 1:
                cycles.append(stack[stack.index(m):] + [m])
            elif m not in state:
                visit(m)
        stack.pop()
        state[n] = 2

    for n in graph:
        if n not in state:
            visit(n)
    return cycles


def cmd_check(args) -> None:
    every = load_concepts()
    concepts = [c for c in every if not args.course or c.course == args.course]
    idx = concept_index(every)
    names = all_note_names()
    problems: list[str] = []

    seen: dict[str, Concept] = {}
    for c in every:
        for key in [c.name] + c.aliases:
            other = seen.get(key.lower())
            if other and other is not c:
                problems.append(f"duplicate name or alias '{key}': {rel(c.path)} and {rel(other.path)}")
            seen.setdefault(key.lower(), c)

    for c in concepts:
        where = rel(c.path)
        if "concept" not in c.tags:
            problems.append(f"{where}: tag 'concept' missing (it won't show in the graph)")
        if c.course not in c.tags:
            problems.append(f"{where}: course tag '{c.course}' missing")
        if c.declared_course and c.declared_course != c.course:
            problems.append(f"{where}: course says '{c.declared_course}' but the note is in {c.course}/")
        if len(c.statuses) == 0:
            problems.append(f"{where}: no status tag (status/solid, status/shaky or status/not-yet)")
        elif len(c.statuses) > 1:
            problems.append(f"{where}: more than one status tag {c.statuses}")
        elif c.status not in STATUSES:
            problems.append(f"{where}: unknown status '{c.statuses[0]}'")
        if not c.statement:
            problems.append(f"{where}: no **Statement:** line")
        for t in c.links:
            key = t.strip().lower()
            if key.endswith(".md"):
                key = key[:-3]
            if key not in names and key not in idx:
                problems.append(f"{where}: broken link [[{t}]] (make a not-yet stub or fix the name)")
        for t in c.follows_from:
            if t.lower() not in idx:
                if t.lower() in names:
                    problems.append(f"{where}: follows from [[{t}]], which is not a concept note")

    for cyc in find_cycles(concepts, idx):
        problems.append("circular 'follows from' chain: " + " -> ".join(cyc))

    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print(f"Graph OK: {len(concepts)} concept(s) checked.")


def rel(p: Path) -> str:
    return p.relative_to(VAULT).as_posix()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Knowledge graph tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("maps")
    p.add_argument("course", nargs="?")
    p.set_defaults(func=cmd_maps)
    p = sub.add_parser("check")
    p.add_argument("course", nargs="?")
    p.set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    if not COURSES.is_dir():
        sys.exit(f"No courses folder at {COURSES}")
    args.func(args)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
