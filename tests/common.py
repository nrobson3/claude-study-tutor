"""Shared helpers for the vault script tests.

Run from the repo root:  python -X utf8 -m unittest discover -s tests
Each test builds a throwaway mini-vault (a copy of scripts/) under the system temp folder,
so the real vault is never touched.
"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
import pymupdf

SRC = Path(__file__).resolve().parent.parent / "scripts"
SCR = Path(tempfile.gettempdir()) / "study-vault-tests"
WORK = SCR / "work"
WORK.mkdir(parents=True, exist_ok=True)
PY = [sys.executable, "-X", "utf8", "-I"]


def force_rmtree(path):
    """shutil.rmtree that also removes git's read-only object files on Windows."""
    import os, stat

    def onexc(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if Path(path).exists():
        shutil.rmtree(path, onexc=onexc)


def mkvault(name):
    v = WORK / name
    if v.exists():
        force_rmtree(v)
    (v / "scripts").mkdir(parents=True)
    for f in SRC.glob("*.py"):
        shutil.copy(f, v / "scripts" / f.name)
    return v


def run(v, script, *args, stdin=None):
    if stdin is None or isinstance(stdin, str):
        return subprocess.run(PY + [str(v / "scripts" / script), *args], input=stdin, capture_output=True,
                              cwd=str(v), encoding="utf-8", errors="replace")
    r = subprocess.run(PY + [str(v / "scripts" / script), *args], input=stdin, capture_output=True, cwd=str(v))
    r.stdout = r.stdout.decode("utf-8", "replace"); r.stderr = r.stderr.decode("utf-8", "replace")
    return r


def mkpdf(path, pages):
    path.parent.mkdir(parents=True, exist_ok=True)
    d = pymupdf.open()
    for t in pages:
        p = d.new_page()
        y = 72
        for line in t.split("\n"):
            p.insert_text((72, y), line, fontsize=11)
            y += 16
    d.save(path)
    d.close()


def concept(v, course, name, tags, statement="**Statement:** s", follows="", body="", fm_extra="", yaml_list=False):
    d = v / "courses" / course / "concepts"
    d.mkdir(parents=True, exist_ok=True)
    if yaml_list:
        tagtxt = "tags:\n" + "".join(f"  - {t}\n" for t in tags)
    else:
        tagtxt = f"tags: [{', '.join(tags)}]\n"
    txt = f"---\n{tagtxt}{fm_extra}---\n# {name}\n{statement}\n{follows}\n{body}\n"
    (d / f"{name}.md").write_text(txt, encoding="utf-8")
