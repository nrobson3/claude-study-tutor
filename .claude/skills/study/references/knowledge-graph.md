# The knowledge graph

Concept notes are the graph's nodes. A note's **Follows from** links are its edges. Obsidian's graph view draws them, filtered to `tag:#concept` and coloured by status:

- **solid:** green;
- **shaky:** amber;
- **not-yet:** grey.

Arrows point from a concept to what it rests on. The graph is a by-product of studying. She never maintains it; you do, at the end of each session.

## Concept note format

Copy `templates/concept.md` to `courses/<course>/concepts/<Name>.md`:

```markdown
---
tags: [concept, chem-1302, status/shaky]
course: chem-1302
kind: derived
aliases: [Gibbs energy, ΔG]
updated: 2026-11-07
---
# Gibbs free energy

**Statement:** At constant $T$ and $P$, a process is spontaneous when $\Delta G = \Delta H - T\Delta S < 0$.

**Follows from:** [[Second law of thermodynamics (chemistry)]], [[Entropy (chemistry)]], [[Enthalpy]]

**Why:** one or two sentences: the reasoning step that gets from those premises to this statement.

**Slides:** [[courses/chem-1302/slides/L14 Thermo.pdf#page=12|L14 p. 12]]

**Sessions:** [[2026-11-07 Gibbs free energy]]

**Watch out:** misconceptions she has shown (e.g. "judged spontaneity from ΔH alone"), and exam traps.
```

**Fields:**
- **kind:** `foundation` for a fact taken at face value, or `derived` for one that follows from others.
- **Statement:** one sentence, exact, in the course's notation. The course map lists it, so it must stand alone.
- **Follows from:** only the premises this concept directly rests on. Cross-course links are welcome and valuable, for example `[[Newton's second law (physics)]]` from statics. Don't add "related" links here.
- **Watch out:** this is where misconceptions live. Write them as specific claims, not "be careful".

## Names

- Obsidian finds notes by file name across the whole vault, so names must be unique.
- Use the plain name when it's unambiguous ("Gibbs free energy"). Add the course area in brackets when the word means different things in different courses: "Equilibrium (statics)" vs. "Equilibrium (chemistry)", "Stress (materials)".
- Put everyday names and symbols in `aliases`. When you link to a concept in prose, use its exact note name.
- One concept per note, at the grain of one idea someone could test. "Method of joints" is a concept; "Trusses" is a topic, not a concept.

## Status: from evidence only

| Status | When |
|---|---|
| `status/solid` | She retrieved and used it **unaided, cold** (not straight after being taught it), in a form different from how it was taught. |
| `status/shaky` | She needed hints; got it only right after teaching; showed a misconception; or it was solid but she has since missed it. |
| `status/not-yet` | Not studied yet: a prerequisite stub or a seeded concept from the slides. |

- A miss knocks solid down to shaky.
- Shaky becomes solid only through a cold, unaided success, usually in practice or a later session.
- At close, say the changes in one line ("Gibbs free energy: shaky → solid"). If she disagrees, her call wins.

## Stubs

Every concept you link to must exist as a note. If a prerequisite has no note yet, create a stub with `status/not-yet`, a **Statement**, its **Slides** link, and **Follows from** if known. Unresolved links break the lint and leave holes in the graph.

## map mode (seeding a whole course)

When she asks to map a course:
1. Confirm first. Say how many decks and pages are involved.
2. Go deck by deck through `slides-text/`, opening pages as images where flagged.
3. For each testable concept, create a `status/not-yet` stub with its statement, slide link and follows-from links. Don't overwrite existing notes: only add slide links to them.
4. Run `python scripts/graph.py check <course>` and fix everything it reports.
5. Sync.

The grey graph then shows the whole course, and it fills in green and amber as she studies.

## Maps and lint

- `python scripts/graph.py maps` rebuilds each `map.md`: concepts by status with their statements, links into other courses, and decks no session has touched. `sync.py push` runs it for you.
- `python scripts/graph.py check [course]` reports:
  - missing or conflicting status;
  - missing tags or statement;
  - broken links;
  - duplicate names or aliases;
  - circular follows-from chains.
  Fix everything before syncing.
