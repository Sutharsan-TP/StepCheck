# Demo script (under 3 minutes)

## Setup

1. Start the backend with the offline stub. This makes no API calls, so the demo behaves the same every time:
   `cd backend; $env:STEPCHECK_STUB_AI="true"; .venv\Scripts\python -m uvicorn app.main:app --port 8000`
2. Start the frontend: `cd frontend; npm run dev`, then open http://localhost:3000.
3. Have `examples/handwritten_samples/demo2_first_error.png` ready to upload.

If you have tested an OpenRouter key and models, set them instead of the stub to show real handwriting transcription.

| Time | Step | What to show | What to say |
|---|---|---|---|
| 0:00 | **Landing page** | The example card: two valid steps, the first error, then a step that depends on it. | "Most tools only mark the final answer. StepCheck finds the exact step where the reasoning breaks, and a symbolic engine — not AI — decides what is correct." |
| 0:20 | **Demo 1: correct solution** | Workspace → *Correct linear solution* → **Check my steps**. Every step is green and the result says *Correct*. | "Each line is solved exactly and compared with the line before it." |
| 0:40 | **Demo 2: first error** | **Edit steps** → *Arithmetic slip* → check. Step 3 is red, step 4 is grey, and the side panel shows *Lost: x = 5, Added: x = 10*. | "Step 2 is still right. Step 3 changes the solution from 5 to 10, so it is the first error. Step 4 follows from it, so it can't be trusted either." |
| 1:00 | **Explain mistake** | The type of mistake and the explanation. | "The AI only words facts the engine has already proved. If it contradicts them, StepCheck throws its text away." |
| 1:15 | **Guide me through it** | Type `2x = 11` and get *Not quite*. Ask for another hint. Type `2x = 10` and get *Correct!*. Type `x = 5` and get *Solved*. | "Hints come in levels, and the answer is only shown if you ask for it. Every attempt is checked by the engine, and the server never trusts the browser's word for what's been accepted." |
| 1:45 | **Demo 3: lost root** | *Lost quadratic solution* → check → **Show corrected solution**. The corrected line is `x − 2 = 0 or x − 3 = 0`, and the final answer {2, 3} is labelled *re-checked by StepCheck*. | "Dropping a factor loses a solution. StepCheck catches it, says the answer is incomplete, and builds a correction it has checked again from start to finish." |
| 2:10 | **Compare my work** | The side-by-side table: kept, corrected and added rows. | |
| 2:20 | **Handwritten upload** | **Upload photo** → the sample. The review screen shows one highlighted line, and **Confirm** stays disabled until that line is ticked. Confirm to see the results. | "AI reads the handwriting, but the student confirms every line. Nothing is checked until they do." |
| 2:45 | **Close** | | "Exact symbolic checking, the first error located, and corrections that are themselves verified — with AI used only where it is safe." |

## Calculus segment (add 60 seconds)

| Step | What to show | What to say |
|---|---|---|
| **Keypad** | Workspace → *Calculus* examples → *Product rule slip*. Show the keypad's Calculus page. | "Students can type, or tap a calculator-style keypad." |
| **Check** | Step 2 is red: *This step works out to 2x cos(x), but it should equal …*. Open **Explain mistake**: *Product rule*. | "It finds the exact step and names the rule that was misapplied. Same engine rules: no AI decides this." |
| **Visual editor** | Switch to **Visual editor**, type a fraction and an integral, show *Checked as: int(x^2) dx*. | "Or write real maths. It's translated into the same text, and the server checks it again." |
| **Missing + C** | *Missing + C* example → *Unfinished*. | "Every step is right, but an indefinite integral needs + C, and StepCheck says so." |
| **Handwriting** | Upload `examples/handwritten_samples/demo4_calculus.png`. | "Calculus handwriting goes through the same review step." |

## Backup cases

- **Answer already complete, then a wrong step:** `2x + 5 = 15`, `2x = 10`, `x = 5`, `x = 10`. StepCheck recommends removing step 4.
- **Unsupported input:** `x^3 = 8`, `x = 2`. The result is *Unsupported*, and no correction is offered.
- **Undecided calculus:** `lim(x->0, 1/x)`, `oo`. A two-sided limit that doesn't exist is *Needs review*, not a guess.
