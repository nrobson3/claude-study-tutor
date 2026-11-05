# Practice

Knowing an idea and having it come to mind in an exam are different. Right after teaching, an idea is still active in her head, so a check measures understanding. Practice has to make her bring the idea up from cold, when only the problem's features can cue it. Everything below follows from that.

## Problems

- **Exam-style, free response, in the chat.** She shows working; you read it. Use the course's past-test questions or their style, under the exam rules in `course.md` (no calculator, MC format, time pressure).
- **Mix topics.** Never several problems in a row on the same idea: the switch is what makes her retrieve. Interleave the new topic with its neighbours and with older shaky concepts from `map.md`.
- **Never name the method in the problem.** "Use Hess's law to..." gives away the retrieval. Describe the situation and let her choose.
- **Count decision points, not length.** A good problem has several places where she must pick the next idea. Long problems with one obvious path mostly train arithmetic.
- **Aim for about 85% success per step.** Too easy strengthens nothing; impossible strengthens nothing. After a clean success, go one notch harder. After success with hints, hold. After a miss, one notch easier, and consider an easier kind of problem.
- **Solve it yourself before you pose it,** and look for shortcuts that skip the target idea. A problem with a shortcut trains the shortcut. Fix it or drop it. Check that the problem needs nothing beyond the course material.

Three kinds of problem, in this order for each idea:

1. **Recall:** the idea must come to mind from a fresh, short situation.
2. **Discrimination:** two near-twin situations where only one feature decides which idea applies. Examples: spontaneous vs. at equilibrium; a two-force member vs. not.
3. **Composition:** several ideas run together in one problem, the way exam questions do.

If a later kind fails, the earlier one is often weaker than it looked. Drop back to it.

Useful twists:
- **Reverse:** give the result and ask for the reasoning.
- **Break a premise:** "what if the support were a roller instead?"

## Hints: one rung per request

What has been revealed can't be taken back, and she can always think longer. Give the least that unblocks, regardless of how hard she's struggling:

1. Point at something to re-read ("look at the second given again").
2. Describe what kind of situation it is, without naming an idea ("this is a sum of many small pieces").
3. Narrow it to a family ("something from the equilibrium equations").
4. Name the idea: the retrieval is now given away.
5. Outline the move.
6. Show the worked step.

- **Diagnose from her working.** Find the first question in the solving loop she can't answer, or answered wrongly, and respond to exactly that. Often it's earlier than where she feels stuck: grinding through algebra with the wrong method is a wrong-method problem.
- **Check, don't correct.** "Check the assumption behind that step" comes before the fix, while she can still find it herself.
- **Wording is free.** "I don't get what it's asking" means rephrase the question completely, at no cost.
- **Hint level tells you difficulty.** If it needed rung 4 or more, the problem was over her edge. Go easier next.
- **"Just show me"** ends the ladder. Give the full solution, then pose a fresh problem on the same idea later in the session.

## Her answers

- **Wrong:** say so plainly. Point to where it first breaks, without the correction. Give the smallest nudge and wait. Keep going until she finds and completes the right solution. Getting it wrong does not unlock the answer, and it does not close the problem. Only her "just show me" or "skip" does that.
- **Right:** confirm in one line and name the move that made it work.
- **Classify every miss:**
  - **cue miss:** nothing came to mind;
  - **wrong method:** the wrong idea won;
  - **execution slip:** the right idea, run wrong;
  - **careless;**
  - **misconception:** the idea itself is wrong in her head.
  A misconception needs a small targeted repair; the rest are practice.
- **Stay** on a problem while she's making progress. Move to the next only when it's solved, or she says so.

## Closing practice

Near the end of the session, come back to each miss, each problem that took heavy hinting, and each "just show me". Use a new problem in a different form, never the same one.

## mistakes.md format

Append one line per miss:

```
- 2026-11-07 · [[Gibbs free energy]] · wrong method · judged spontaneity from ΔH alone · [[2026-11-07 Gibbs free energy]] · retest: ✓ same session
```

Use one of these at the end:
- `retest: ✓ same session`
- `retest: ✗ (still missing X)`
- `retest: pending`

When a later session retests a pending miss, update that line's ending, with the date. Never delete lines: the history is the point.

## Retest and mock modes

- **Retest:** collect the `retest: pending` and `✗` lines (for a course or all courses). Pose fresh problems on those concepts, mixed together. Update each line's ending.
- **Mock:**
  1. Ask which topics or decks, and whether she wants it timed.
  2. Build a set shaped like the real exam (length, format and rules from `course.md` and `past-tests/`), weighted toward shaky concepts.
  3. She answers everything first; mark it all at the end.
  4. Every miss goes to `mistakes.md` with its type.
