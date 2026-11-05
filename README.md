# claude-study-tutor

The study system I use for my engineering courses at Western: Claude Code as a
tutor that works only from my own course slides and past tests, and Obsidian as
the notebook where every session, concept and mistake ends up as a linked note.

This repository is the system without the material: the tutor's instructions,
the scripts, the tests and the note templates. My working copy, with the slides,
past tests and session notes, is a separate private repo, because that material
belongs to my instructors and the university.

## What it does

Open Claude Code in the vault folder and say what you want:

| Say | You get |
|---|---|
| `study <topic>` | It finds the topic in your slides, checks what you already know, shows a plan, teaches the gap one step at a time with checks, then gives exam-style practice. |
| `explain <topic>` | Teaching only, no practice. |
| `practice <topic>` | Problems only, with hints one small step at a time. |
| `quiz me on my mistakes` | Fresh problems on everything you've missed. |
| `mock exam <course>` | An exam-shaped set under the real exam's rules, marked at the end. |
| `map <course>` | Seeds the whole course into the knowledge graph from the slides (grey until studied). |
| `just show me` | Turns off hints and shows the full solution. |

While a session runs, its lesson note (`courses/<course>/sessions/`) fills in
beside the chat in Obsidian, with the math, diagrams and quiz results rendered.

In Obsidian:
- **Graph view** is the knowledge graph: concepts only, green = solid,
  amber = shaky, grey = not yet. Arrows point to what a concept rests on.
- **`courses/<course>/map.md`** lists every concept by status, plus the slide
  decks not studied yet.
- **`courses/<course>/mistakes.md`** lists every miss and whether it has been
  retested.

## How it is built

The vault has three layers, kept apart (after Andrej Karpathy's "LLM Wiki"
pattern):

1. **Sources:** `slides/` and `past-tests/`, never edited.
2. **The wiki Claude writes:** `sessions/`, `concepts/`, `mistakes.md`, `viz/`.
3. **Derived:** `slides-text/` and `map.md`, written only by the scripts.

| File | Job |
|---|---|
| `CLAUDE.md` | The vault's rules: layout, citation (every course fact links to its slide page), notation, git |
| `.claude/skills/study/` | The tutoring flow and its references: teaching, practice, quizzes, visuals, knowledge graph |
| `scripts/slides.py` | Indexes slide PDFs into page-numbered text, searches it, renders pages |
| `scripts/lesson_log.py` | A Claude Code hook that mirrors the live session into its lesson note |
| `scripts/graph.py` | Builds each course map and lints the graph (broken links, cycles, orphans) |
| `scripts/sync.py` | Pull and push with GitHub, keeping files over 50 MB out of git |
| `scripts/setup_hooks.py` | Writes `.claude/settings.json` for your computer |
| `templates/` | Session and concept note templates |
| `tests/` | unittest suite for the scripts |

## Set it up

You need Claude Code, Obsidian, and Python 3.11 or newer with `pymupdf`.

1. Clone this repo and make **your own copy private** before adding any course
   material. Slides and past tests belong to their authors.
2. Add a folder per course under `courses/`: `slides/`, `past-tests/`,
   `sessions/`, `concepts/`, and a `course.md` with the exam dates and rules.
   Edit the course list in `CLAUDE.md`.
3. Run `python scripts/setup_hooks.py` to point the lesson-log hooks at your
   Python and this folder.
4. Put lecture PDFs in `courses/<course>/slides/` and run
   `python scripts/slides.py index`.
5. Open the folder as a vault in Obsidian, and run Claude Code in it.

Run the tests from the repo root:

```
python -X utf8 -m unittest discover -s tests
```

## Credits

The tutoring method (probe what is known, plan, teach one step at a time with
checks, then retrieval practice with minimal hints) is adapted from Eero Alvar's
[`learn`](https://github.com/amosblomqvist/learn) and
[LearnHarness](https://github.com/amosblomqvist/learnharness). The ideas are
his; the text and code here are written from scratch. The vault layout follows
Andrej Karpathy's "LLM Wiki" pattern. Built with Claude Code.

## License

Copyright © 2026 Navy Robson. All rights reserved. You are welcome to read it;
reuse or redistribution needs written permission.
