# Check questions (quizzes)

Use a quiz for any question with a right answer: probe questions, the check after each teaching step, quick recall. Problems that need working go in the chat as free response (practice.md), not here.

## The convention (the lesson log depends on it)

Call `AskUserQuestion` with **one question per call**:

```json
{
  "questions": [{
    "question": "At constant T and P, which condition makes a reaction spontaneous?",
    "header": "Check",
    "multiSelect": false,
    "options": [
      {"label": "A", "description": "ΔH < 0"},
      {"label": "B", "description": "ΔG < 0"},
      {"label": "C", "description": "ΔS > 0"},
      {"label": "I don't know", "description": "No guessing: say so and we'll work it out"}
    ]
  }],
  "metadata": {"source": "quiz|B"}
}
```

- **Options:** labels are exactly `A`, `B`, `C` (up to three real options), plus a last option labelled exactly `I don't know`. Each claim goes in the `description`.
- **The key:** goes in `metadata.source` as `quiz|<label>`, decided **before** you ask. For multiSelect, join the labels with `;;`, as in `quiz|A;;C`. She doesn't see it. The lesson log hook grades her answer, writes ✓/✗ into the lesson note, and tells you the grade. Respond to that grade; don't re-grade.
- **Header:** `Probe` for probing, `Check` after a teaching step, `Recall` for retrieval.
- **Math: plain text, never LaTeX, in `question` and `description`.** The pop-up can't render LaTeX, so `$\mathrm{CO_2}$` shows up as raw code. Write it with Unicode so it reads the same in the pop-up and the lesson note:
  - Subscripts and superscripts: CO₂, H₂O, SO₄²⁻, x², 10⁻³, m/s².
  - Symbols: Δ, °, →, ⇌, ≤, ≥, ≠, ≈, ±, ×, ·, √, π, θ, μ, Σ, ∫.
  - Simple fractions inline: (a + b)/c, ½.
  - Example: "Which process has ΔS° < 0?" with option "2 SO₂(g) + O₂(g) → 2 SO₃(g)".
  - Too complex for one line (a long derivation, a matrix, a nested fraction)? Show it in your teaching text just before the question, where it renders as LaTeX in the note. Label it, for example "(1)", and have the question refer to "(1)".
  - LaTeX everywhere else (your teaching text, the summary, concept notes) is unchanged.
- **Her answer:** she can type in "Other" or add a note. Treat what she writes as her reasoning: read it, and use it to decide the next question.
- Randomise which letter is correct. Don't let B (or any letter) become the usual answer.
- "I don't know" is information, not failure. Never treat it as wrong, and never shame a guess either.

## Writing options that don't give the answer away

Build the options so the right one can't be spotted without knowing the material:

1. **Bare claims only.** No reasons or "because" in any option. Reasoning goes in your reply after she answers. The usual tell is the correct option being longer and more specific because it carries its own justification.
2. **Start from the true statement and bend it.** Each wrong option is what someone holding one specific, real misconception would claim, written in the same structure, length and register. Which one she picks then tells you which misconception she has.
3. **Tempting, not tricky.** Every distractor is unambiguously wrong on the intended reading.
4. **No uneven formatting.** Bold nothing, or the parallel term in every option.

Read the finished set cold. If you can tell the answer without knowing the material, rewrite it from step 1.

## After she answers

- **Correct:** confirm in one line, naming what made it right. Move on.
- **Wrong:**
  - Say so plainly.
  - Name the likely misconception: her pick and her note usually show it.
  - Repair the step before continuing; in a probe, probe around it.
- **"I don't know":** for a probe, the ceiling is found. For a check, re-teach the step more simply, then check again in a different form.
- **Free text in "Other":** grade it yourself against the key. Partial credit is fine; say exactly what was missing.
