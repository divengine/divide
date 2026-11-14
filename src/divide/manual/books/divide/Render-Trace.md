# Render Trace

**Debug > Render trace** (**F7** in a template) renders the template as [[Ctrl+F9|Rendering]] does, and keeps every change Div made on the way, so you can replay how the template became its output.

![the row where Div decides a condition: what stays, in green](images/trace.png)

## Why not line by line

A Div template is not run from top to bottom. Div rewrites the whole template again and again: it decides the conditions, pastes the includes in, unrolls the lists, replaces the variables, formats the numbers… Each rewrite can bring new tags (an include brings its own), so Div keeps going until a whole cycle changes nothing: a **fixed point**. Parts of the template are parsed apart, each with an engine of its own: every item of a list, the expression of a condition.

So the trace is not a list of lines but a list of **mutations**: what the template was, what it became, and which step of Div did it.

## The window

- **The rows**, at the bottom, one per mutation, in the order Div made them:
  - `► Template`: the template as Div starts on it.
  - `-30   Condition: {$cart.items} > 0 > The condition 2 > 0 is true`: a change. The number is how many characters it added or took away; the words are Div's own, from its log of what it was doing.
  - `► Sub-parse: Item 0 of the list 'products'`: Div starts parsing a part apart. Its rows are indented below it.
  - `■ Fixed point: nothing changes after 3 cycles`: that parse is done.
  - `■ Output: what Div returns`: the result, the same as Ctrl+F9 gives.
- **The template**, at the top, as it was after the selected row. What the mutation wrote is marked green.
- **The frame** says where you are: `6/33 · cycle 1 · -30 · after`. The status line shows the row in full.

**Space** shows the template *before* the selected mutation instead, with what it took away marked red. Space again goes back to after.

![the same row before the mutation: the condition that went away, in red](images/trace-before.png)

## Keys

The debugger's keys, on the rows:

| Key | Action |
|---|---|
| **↑ / ↓** | the previous / next row |
| **F8** | the next row of the same parse, over its sub-parses |
| **F7** | the next row, into the sub-parses |
| **Shift+F8** | out: the next row of the parse that started this one |
| **Space** | before / after the mutation |

## How it works

Div is not changed. divide renders with a subclass of Div whose `logger()` (Div calls it at every step of its parser when its log mode is on, `div::logOn()`) notes the step, the engine and the whole template whenever it changed. The labels are Div's log messages, shortened. The output is what Div rendered, the same as without the trace.

## Limits

- It is a replay: the render has already happened when the window opens. You move through it in both directions, but you cannot change the data halfway.
- Div's parser decides how much each row covers: one step can make several changes at once (all the matches of a cycle, for example), and a step that changes nothing has no row.
- Very long renders are cut (64 MB of snapshots, 50 000 steps); the progress box says so.

Back: [[Rendering]].
