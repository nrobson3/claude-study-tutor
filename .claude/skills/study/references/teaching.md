# Teaching: probe, plan, teach

The aim is understanding, not recall. A fact she can recite but can't derive is fragile; a fact that follows from things she already accepts stays. Two people can give the same answers while one holds a pile of separate facts and the other holds a few core ideas the facts follow from. Teach toward the second.

Credit: the method comes from Eero Alvar's `learn` and LearnHarness projects, rewritten here for engineering courses.

## Two principles

**1. Start from things she can accept as plainly true.**
- Lock in the few facts the topic rests on before building on them. Pick facts she can take at face value with no caveats: real definitions, conservation laws, "all X are Y" statements. These are easy to commit to because nothing will later contradict them.
- If a fact needs "usually" or "except when", it isn't a foundation yet. Go one level down.
- Not every foundation is an axiom. "Unconditional" describes how the fact can be held, not where it sits.
- Before building on a foundation, check that it lands as obviously true for her. If it doesn't, fix that first.

**2. Make each step feel discovered, not decreed.**
- For every step, answer "why would anyone do this?" and "how could I have found this myself?" Start from the problem that forces the idea, then motivate each move: why this substitution, why sum moments about that point, why this sign.
- Each new fact should follow from what she holds by one small reasoning step, so it lands as "of course".

**Socratic or expository, per step.**
- When she can plausibly reason her way there, pose the motivating question and let her try first. If it has a right answer, ask it as a quiz.
- When it's beyond reasoning from scratch, or she wants it delivered, narrate the discovery path yourself.
- Default to Socratic when in doubt and the step is reachable.

## Probe

There are two unknowns: what she's after, and where her knowledge runs out.

**Her goal:**
- Usually it's an exam question type, a concept from the slides, or a homework problem.
- If it's vague, ask one plain question (AskUserQuestion, no grading).
- Past tests are the best definition of "exam-ready". Show her a past-test question on the topic and ask whether that's the target.

**Her edge on each prerequisite strand:**
- A strand's edge is only found when you have both a **floor** (something she gets right) and a **ceiling** (something she gets wrong or doesn't know).
- Enter near the top. She's a university engineering student, so don't open with high-school basics. A miss walks you down.
- Correct and confident: jump up sharply. Correct but hesitant (thin reasoning, a lucky guess): step up gently and find out what's shaky.
- One miss is one data point, not a verdict. It could be a slip, a gap or a misconception, so probe around it. Misconceptions matter most: find how far they reach.
- Ask only questions that can move an edge. Never re-ask what an answer already showed.
- Strands inform each other. Don't probe below what she has already demonstrated elsewhere.
- Use her concept notes and past sessions: a strand already marked solid with recent evidence needs at most one check.

Stop when every strand the goal depends on has a floor and a ceiling. Then plan.

## Plan

This is where lesson quality is decided, so think properly:
- Which foundations does the goal rest on? Which does she already hold?
- What is the shortest dependency path from what she holds to the goal? Teach nothing she already holds, and nothing off that path, however interesting.
- For each step: what motivates it, and is it Socratic or expository?
- Stress-test the roots. Is each foundation truly plain for her, or a disguised result of something simpler? If it derives, push it down.

Show her:
1. **The approach:** 2-4 sentences on what, in what order, and why that way.
2. **The map:** a Mermaid `graph TD` with foundations at the top and her goal at the bottom, at most about 8 nodes with short labels. Cite the decks it draws on.

Wait for her OK. The plan is the cheap place to fix a wrong scope.

## Teach

Work through the map one reasoning step at a time. A plan node may take several steps. For each step:

1. **Motivate:** why we need this now, and what gap it closes.
2. **Establish:**
   - A foundation: state it plainly, no hedging.
   - A derived step: build it from what's already established with one motivated move, Socratic or narrated.
3. **Connect:** say exactly which established facts this one rests on.
4. **Check:** one graded question (see quizzes.md). If she misses it, the step didn't land: repair it before building anything on it.

Rules:
- Never lecture several steps and then check once.
- Never build on an unchecked step.
- Don't narrate the choreography ("Node 3: ...", "Now I will establish..."). Let each step follow from the last.
- Plan nodes are landmarks, not chapter headings.
- Cite the slide page for every course fact, in the prof's notation.
- Worked examples: use the slides' or past tests' own examples where they exist. Fade support as she gets it: full worked example, then one with gaps for her to fill, then hers alone.

**Engineering-specific:**
- Write the governing equation, then the assumptions that make it apply.
- Free-body diagrams before equations in statics and mechanics.
- Units carried through every line. Sign conventions exactly as the course defines them.
- Ask her to predict before you calculate ("which way will the reaction point?", "will ΔS be positive?"). A prediction that turns out wrong is the best teaching moment there is.

The topic is done when the goal feels obvious to her: she can say why it's true, not only that it is. Then move to practice (study mode) or close (explain mode).
