# Visuals

Draw only when the idea is geometric, directional or structural, so that words or a single equation would carry it badly. A wrong diagram does more harm than none, so **every picture is checked by looking at it** before she sees it.

## When

Draw a diagram for:
- free-body diagrams;
- vectors and components;
- moments and lever arms;
- geometry (areas, volumes, related rates);
- the graph of a function;
- energy diagrams and phase diagrams;
- crystal structures;
- stress-strain curves.

Use a dependency map for the plan. Use a flowchart for a decision ("which equation applies?").

Skip it when the sentence beside it already says it. If in doubt, don't.

## Which tool

- **Dependency maps and flowcharts:** a Mermaid code block directly in your reply. Obsidian renders Mermaid natively. Keep it to about 8 nodes or fewer with short labels, and use `graph TD` with foundations at the top.
- **Anything with coordinates, angles or data** (FBDs, vectors, plots, geometry): matplotlib. Write a short script, render it to PNG, look at it, and fix it until it's right.

## The draw-and-check loop (matplotlib)

1. Decide the one idea the picture must show. List its elements: about 5-7 at most. Cut anything that isn't needed.
2. Write the script. Save the output as `viz/viz-<short-topic>-<YYYYMMDD-HHMMSS>.png` (unique names, because Obsidian finds embeds by file name).
   - Use a white background, dark strokes and at most one accent colour.
   - Use font size 12 or larger, with labels off the lines.
   - Keep equal axis scaling for geometry (`ax.set_aspect("equal")`) and leave generous margins.
3. Run it, then **Read the PNG and look at it critically**:
   - Is every direction, angle, sign and position correct? Re-derive the geometry if unsure.
   - Does it match the slides' convention (axes, sign of moments, labels)?
   - Is anything overlapping, clipped or too small?
   - Would she get the idea from the picture alone?
4. Fix it and re-render until it's right. If you can't make a correct picture, drop it and explain in words.
5. Embed it in your reply: `![[viz-<short-topic>-<stamp>.png|500]]`. The lesson log copies your reply into the note, where Obsidian shows it. Introduce it in a sentence; don't narrate every element.

Keep the scripts out of the repo. Run them from the scratchpad, or inline with `python -c`. Only the PNG goes in `viz/`.

## Her own images

- If she sends a photo of her working or a textbook figure, read it carefully before replying.
- To mark one up (circling the error, adding an arrow), use matplotlib with `imshow`, run the same check loop, and save the result to `viz/`.
