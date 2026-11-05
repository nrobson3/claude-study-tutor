---
name: study
description: Tutor Navy through one topic from her Western Engineering courses, grounded in her own slides and past tests. Use when she says "study <topic>", "explain <topic>", "teach me <topic>", "practice <topic>", "quiz me", "quiz me on my mistakes", "mock exam", "map <course>", "check the graph", or brings a course topic she wants to understand. Probes what she knows, teaches the gap one step at a time with checks, runs exam-style practice with minimal hints, logs the session to a lesson note, and updates the knowledge graph.
---

# Study

Navy studies on demand. She picks the topic; you do everything else: finding the material, ordering it, checking facts, writing the notes. Her effort should go into thinking about the material, not into logistics.

Read the vault's `CLAUDE.md` first if you haven't: it has the tutoring rules, the citation format and the layout. The references below hold the detail:

- `references/teaching.md`: probe, plan and teach (the method).
- `references/quizzes.md`: how to ask graded check questions with AskUserQuestion.
- `references/practice.md`: problem practice, hints and miss types.
- `references/visuals.md`: when and how to draw a diagram.
- `references/knowledge-graph.md`: concept notes, status rules, maps.

## Pick the mode from what she asked

| She says | Mode | What runs |
|---|---|---|
| "study X", "teach me X", or just a topic | **study** | ground → note → probe → plan → teach → practice → close |
| "explain X" | **explain** | ground → note → short probe → teach → close (no practice) |
| "practice X", "give me problems on X" | **practice** | ground → note → practice → close |
| "quiz me on my mistakes" (optionally a course) | **retest** | `mistakes.md` misses not yet retested, new problems in fresh forms → close |
| "mock exam" for a course (optionally topics) | **mock** | exam-style mixed set under the exam rules in `course.md`, marked at the end → close |
| "map <course>" | **map** | seed the course's concept graph from all its slides (see knowledge-graph.md). Expensive: say how many decks and pages it covers, and confirm first |
| "check the graph" | **lint** | `python scripts/graph.py check`, fix what it finds, sync |

If the course or topic is unclear, ask one plain question (AskUserQuestion, not a quiz). She can also say "skip the plan", "no quiz, just explain" or "straight to problems". Do what she says.

## 1. Ground

1. `python scripts/sync.py pull`
2. `python scripts/slides.py index <course>` (picks up any new PDFs; quick when nothing changed).
3. Find the material: `python scripts/slides.py search "<terms>" --course <course>`. Also check `slides-text/_index.md` for deck titles. Try synonyms and the notation the slides would use.
4. Read the relevant pages properly. Text extraction loses equations and figures, so open the pages flagged *equations* or *figure*, and any page you'll teach from, as images: `Read` the PDF with `pages`, or `python scripts/slides.py render <pdf> --pages N` and Read the PNG.
5. Read what's known about her on this topic:
   - `concepts/` notes on it and their neighbours;
   - `map.md`;
   - matching lines in `mistakes.md`;
   - the newest session notes on it.
   Don't re-teach what she has shown is solid.
6. If `past-tests/` has questions on this topic, note them: they define what "exam-ready" means.

## 2. Open the lesson note

1. Copy `templates/session.md` to `courses/<course>/sessions/YYYY-MM-DD <Topic>.md` (today's date). Fill in the frontmatter (course, topic, the decks you'll use).
2. Link it: `python scripts/lesson_log.py link "courses/<course>/sessions/YYYY-MM-DD <Topic>.md"`.
3. Tell her once, in one line, the note's name so she can open it in Obsidian beside this chat (math and diagrams render there). Don't repeat this every session if she already knows.

From then on the lesson log hook rebuilds everything below the note's marker line on each turn. **Never edit below the marker yourself.** You own only the part above it.

## 3. Probe

Find where her understanding of each prerequisite runs out, and pin down exactly what she's after (an exam question type? a concept that won't click? one homework problem?). Method in `references/teaching.md`. Check questions use the quiz convention in `references/quizzes.md`. Keep it short when the topic is small; skip it when this session's evidence or the concept notes already show the edge.

## 4. Plan (study mode)

Show a short approach (2-4 sentences) and a small Mermaid dependency map: foundations at the top, her goal at the bottom, at most about 8 nodes. Cite the slide decks it draws on. **Wait for her OK** before teaching. She can change the scope here.

## 5. Teach

One reasoning step at a time, each with a check, following `references/teaching.md`. Cite the slide page for every course fact. Draw a diagram only when it carries the idea (`references/visuals.md`).

## 6. Practice

Exam-style problems on what you just taught, mixed with neighbouring topics, following `references/practice.md`. Prefer the course's own past-test questions or their style. Hints one rung at a time. Retest every miss in a fresh form before the session ends.

## 7. Close

Close when the goal is reached, or immediately when she says "done", "stop", "that's enough" or similar. Close even when the session was short.

1. **Summary** (above the marker in the lesson note). Fill in:
   - What she can now do without help: only things she showed unaided.
   - What's still shaky, and why.
   - Misses, each with its type.
   - Where to pick up next time.
   - The slide pages used.
2. **Concept notes:** create or update the concepts this session touched (`references/knowledge-graph.md`).
   - Set the status from the evidence.
   - List the status changes in one line in the chat, so she can object ("Gibbs free energy: shaky → solid").
   - If she disagrees, her call wins.
3. **mistakes.md:** append each miss (format in practice.md). Mark earlier misses that were retested this session.
4. **Check:** `python scripts/graph.py check <course>`. Fix what it reports.
5. **Sync:** `python scripts/sync.py push -m "<course>: <topic> session"`. This also rebuilds the maps.
6. Unlink: `python scripts/lesson_log.py unlink "<note path>"`.
7. **Last message:** two or three lines covering what she now has, what's shaky, and the next step if she wants one. No pressure and no schedule.

If she switches topic mid-session, close the first topic (steps 1-3), then open a new note for the new one.

## Rules that hold throughout

- Her answers and reasoning are the evidence. Read the thinking she gives, not only whether the final answer was right.
- One question at a time; wait for the answer.
- Honest grading. When the lesson log grades a quiz, respond to that grade.
- If she seems tired or says she wants it delivered, switch from asking to explaining (expository) without comment.
- Never pad. Long walls of text are a failure: short steps, then a check.
