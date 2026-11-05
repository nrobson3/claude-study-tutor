#!/usr/bin/env python3
"""Slide index for the study vault.

Commands
    index [course]
        Extract page-numbered text from every PDF under courses/<c>/slides/ and
        courses/<c>/past-tests/ into courses/<c>/slides-text/. Decks whose hash
        is unchanged are skipped. Text files whose PDF is gone are removed.
        Writes courses/<c>/slides-text/_index.md (one line per deck).
    search <regex> [--course C] [--context N] [--max N]
        Search the extracted text. Prints course, deck, page and the lines.
    render <pdf> --pages SPEC [--dpi N]
        Render pages to PNG under .cache/pages/ and print the paths, for
        reading small print or figures as images.

Page specs: "3", "1-5", "1,3,7", "all".
Only PyMuPDF is needed (already installed with the system Python).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
COURSES = VAULT / "courses"
CACHE = VAULT / ".cache" / "pages"
SOURCE_DIRS = ("slides", "past-tests")
TEXT_DIR = "slides-text"

# Characters that suggest an equation that text extraction will mangle.
# Hyphens, slashes and plus signs are left out: units and prose are full of them.
MATH_CHARS = set("=−×÷±∑∫∂√∞≈≠≤≥∝∆ΔΣΠπθλμσωαβγεφρτηκ^⁰¹²³⁴⁵⁶⁷⁸⁹⁻₀₁₂₃₄₅₆₇₈₉")
PAGE_HEADING = re.compile(r"^## p\. (\d+)\s*$")


def _fitz():
    try:
        import pymupdf  # noqa: F401
        return pymupdf
    except ImportError:
        try:
            import fitz  # type: ignore
            return fitz
        except ImportError:
            sys.exit("PyMuPDF is not installed: run  python -m pip install pymupdf")


def vault_rel(path: Path) -> str:
    """Vault-relative path with forward slashes, as Obsidian links expect."""
    return path.resolve().relative_to(VAULT).as_posix()


def courses(selected: str | None) -> list[Path]:
    if not COURSES.is_dir():
        sys.exit(f"No courses folder at {COURSES}")
    found = sorted(p for p in COURSES.iterdir() if p.is_dir())
    if selected:
        found = [p for p in found if p.name == selected]
        if not found:
            names = ", ".join(p.name for p in sorted(COURSES.iterdir()) if p.is_dir())
            sys.exit(f"Unknown course '{selected}'. Courses: {names}")
    return found


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_frontmatter_value(md: Path, key: str) -> str | None:
    try:
        with md.open(encoding="utf-8") as f:
            if f.readline().strip() != "---":
                return None
            for line in f:
                if line.strip() == "---":
                    return None
                k, _, v = line.partition(":")
                if k.strip() == key:
                    return v.strip().strip('"')
    except OSError:
        return None
    return None


def page_flags(page, text: str) -> list[str]:
    flags = []
    stripped = text.strip()
    if not stripped:
        flags.append("no text layer: read the page image")
    elif len(stripped) < 80:
        flags.append("mostly visual: read the page image")
    if stripped:
        math = sum(1 for ch in stripped if ch in MATH_CHARS)
        if math / max(len(stripped), 1) > 0.03:
            flags.append("equations: read the page image")
    try:
        if page.get_images(full=False):
            flags.append("figure")
    except Exception:
        pass
    return flags


def first_line(text: str) -> str:
    for line in text.splitlines():
        line = " ".join(line.split())
        if len(line) >= 3:
            return line[:90]
    return ""


def text_path_for(course: Path, pdf: Path) -> Path:
    rel = pdf.relative_to(course)  # e.g. slides/L01.pdf
    return course / TEXT_DIR / rel.with_suffix(".md")


def extract(pdf: Path, out: Path, digest: str) -> tuple[int, str]:
    fitz = _fitz()
    doc = fitz.open(pdf)
    title = ""
    pdf_link = vault_rel(pdf)
    lines = [
        "---",
        f'source: "{pdf_link}"',
        f"sha1: {digest}",
        f"pages: {doc.page_count}",
        f"indexed: {date.today().isoformat()}",
        "tags: [slides-text]",
        "---",
        f"# {pdf.stem}",
        "",
        f"Text extracted from [[{pdf_link}|{pdf.name}]]. Equations and figures do not survive"
        " extraction: open the page itself for those.",
        "",
    ]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        if not title:
            title = first_line(text)
        flags = page_flags(page, text)
        lines.append(f"## p. {i}")
        meta = f"[[{pdf_link}#page={i}|open p. {i}]]"
        if flags:
            meta += " · " + " · ".join(f"*{flag}*" for flag in flags)
        lines.append(meta)
        lines.append("")
        body = "\n".join(l.rstrip() for l in text.strip().splitlines())
        # A line starting with '#' would become a heading and break page parsing.
        body = re.sub(r"(?m)^#", r"\\#", body)
        lines.append(body if body else "_(no extractable text)_")
        lines.append("")
    pages = doc.page_count
    doc.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".md.tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(out)
    return pages, title


def write_course_index(course: Path, rows: list[tuple[str, int, str, str]]) -> None:
    out = course / TEXT_DIR / "_index.md"
    lines = [
        "---",
        "tags: [slides-text]",
        "---",
        f"# {course.name}: slide decks",
        "",
        "Written by `scripts/slides.py index`. One row per PDF.",
        "",
        "| Deck | Pages | First line | Text |",
        "|---|---|---|---|",
    ]
    for pdf_link, pages, title, text_link in sorted(rows):
        name = Path(pdf_link).name.replace("|", "/")
        title = title.replace("|", "/")
        lines.append(f"| [[{pdf_link}\\|{name}]] | {pages} | {title} | [[{text_link}\\|text]] |")
    if not rows:
        lines.append("| _no PDFs yet_ | | | |")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_index(args) -> None:
    total_new = 0
    for course in courses(args.course):
        rows = []
        wanted: set[Path] = set()
        for sub in SOURCE_DIRS:
            for pdf in sorted((course / sub).rglob("*")):
                if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
                    continue
                out = text_path_for(course, pdf)
                wanted.add(out.resolve())
                digest = sha1(pdf)
                if out.exists() and read_frontmatter_value(out, "sha1") == digest:
                    pages = int(read_frontmatter_value(out, "pages") or 0)
                    title = ""
                    try:
                        text = out.read_text(encoding="utf-8")
                        m = re.search(r"^## p\. 1\s*\n[^\n]*\n\n(.*?)(?:\n## p\. |\Z)", text, re.S | re.M)
                        title = first_line(m.group(1)) if m else ""
                    except OSError:
                        pass
                else:
                    try:
                        pages, title = extract(pdf, out, digest)
                    except Exception as e:  # damaged or encrypted PDF
                        print(f"  ! {vault_rel(pdf)}: could not read ({e})")
                        continue
                    total_new += 1
                    print(f"  + {vault_rel(pdf)} ({pages} pages)")
                rows.append((vault_rel(pdf), pages, title, vault_rel(out)))
        text_root = course / TEXT_DIR
        if text_root.is_dir():
            for md in text_root.rglob("*.md"):
                if md.name == "_index.md" or md.resolve() in wanted:
                    continue
                if read_frontmatter_value(md, "source") is not None:
                    md.unlink()
                    print(f"  - removed {vault_rel(md)} (its PDF is gone)")
        write_course_index(course, rows)
    print(f"Indexed {total_new} new or changed deck(s).")


def iter_text_files(course_filter: str | None):
    for course in courses(course_filter):
        root = course / TEXT_DIR
        if not root.is_dir():
            continue
        for md in sorted(root.rglob("*.md")):
            if md.name != "_index.md":
                yield course, md


def cmd_search(args) -> None:
    try:
        pattern = re.compile(args.query, re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(args.query), re.IGNORECASE)
    hits = 0
    more = False
    for course, md in iter_text_files(args.course):
        lines = md.read_text(encoding="utf-8").splitlines()
        source = read_frontmatter_value(md, "source") or vault_rel(md)
        page = 0
        page_lines: list[str] = []

        def flush():
            nonlocal hits, more
            for j, line in enumerate(page_lines):
                if not pattern.search(line):
                    continue
                if hits >= args.max:
                    more = True
                    return
                hits += 1
                lo, hi = max(0, j - args.context), min(len(page_lines), j + args.context + 1)
                snippet = "\n".join("    " + l for l in page_lines[lo:hi] if l.strip())
                print(f"{course.name} | {Path(source).name} p. {page} | [[{source}#page={page}]]")
                print(snippet)
                print()

        for line in lines:
            m = PAGE_HEADING.match(line)
            if m:
                if page:
                    flush()
                page, page_lines = int(m.group(1)), []
            elif page and not (line.startswith("[[") and "|open p. " in line):
                page_lines.append(line)  # the "open p. N" link line is not slide text
        if page:
            flush()
        if more:
            break
    if more:
        print(f"(stopped at {args.max} hits; narrow the search or raise --max)")
    if hits == 0:
        print(f"No matches for: {args.query}")


def parse_pages(spec: str, count: int) -> list[int]:
    if spec.strip().lower() == "all":
        return list(range(1, count + 1))
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
            if lo > hi:
                lo, hi = hi, lo
            if lo < 1 or hi > count:
                sys.exit(f"Pages {lo}-{hi} out of range 1-{count}")
            pages.extend(range(lo, hi + 1))
        else:
            p = int(part)
            if p < 1 or p > count:
                sys.exit(f"Page {p} out of range 1-{count}")
            pages.append(p)
    return sorted(set(pages))


def cmd_render(args) -> None:
    fitz = _fitz()
    pdf = Path(args.pdf)
    if not pdf.is_absolute():
        pdf = (VAULT / pdf) if (VAULT / pdf).exists() else pdf.resolve()
    if not pdf.is_file():
        sys.exit(f"No such PDF: {args.pdf}")
    try:
        doc = fitz.open(pdf)
    except Exception as e:
        sys.exit(f"Could not open {args.pdf}: {e}")
    try:
        pages = parse_pages(args.pages, doc.page_count)
    except ValueError:
        sys.exit(f"Bad page spec: {args.pages}")
    CACHE.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", pdf.stem)[:60]
    # Same-named PDFs in different folders, or a replaced PDF, must not share images.
    stat = pdf.stat()
    tag = hashlib.sha1(f"{pdf.resolve()}|{stat.st_mtime_ns}|{stat.st_size}".encode()).hexdigest()[:8]
    for p in pages:
        out = CACHE / f"{safe}-{tag}-p{p}-{args.dpi}.png"
        if not out.exists():
            tmp = out.with_name(out.stem + f".{os.getpid()}.tmp.png")
            doc[p - 1].get_pixmap(dpi=args.dpi).save(tmp)
            os.replace(tmp, out)
        print(out)
    doc.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Slide index for the study vault")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="extract text from new or changed PDFs")
    p.add_argument("course", nargs="?", help="course folder name, e.g. chem-1302")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", help="search extracted slide text")
    p.add_argument("query", help="regex (falls back to literal if invalid)")
    p.add_argument("--course", help="limit to one course folder")
    p.add_argument("--context", type=int, default=2, help="lines of context (default 2)")
    p.add_argument("--max", type=int, default=30, help="stop after N hits (default 30)")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("render", help="render PDF pages to PNG")
    p.add_argument("pdf", help="PDF path (absolute or vault-relative)")
    p.add_argument("--pages", required=True, help='e.g. "3", "1-5", "1,3,7", "all"')
    p.add_argument("--dpi", type=int, default=150)
    p.set_defaults(func=cmd_render)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
