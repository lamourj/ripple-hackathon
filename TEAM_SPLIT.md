# Ripple — Change Impact Desk · Team Split

## What we're building (and what "done" looks like)
Ripple reuses the proven Card A specialist-swarm mechanics for a new scenario. You give the **Change Impact Lead** coordinator a one-sentence AI initiative (plus optional sector / org size). It generates a **causal effect tree** (3–4 direct effects, 1–2 second-order effects each, ~10–12 nodes total, including plausible negative/perverse ones), assigns each effect to whichever of 4 specialists is most relevant, calls those specialists **in parallel** for a stance (`adopt` / `block` / `circumvent` / `escalate`) + a short in-character reaction, prunes second-order children of any *blocked* direct effect (marked `pre-empted`), and synthesizes a **"Ripple Risk Report" .docx** via the required docx Skills API mechanism. As it runs, it streams structured events to `outputs/frontend/events.json`, which a **live static frontend** renders as a growing, color-coded tree. **Done = you type an initiative, watch the tree build + specialists react live in the browser, and open a branded .docx whose Executive Summary links to `http://localhost:8000`.**

## The contract both workstreams build against
`outputs/frontend/events.json` is a **JSON array** of event records, rewritten-and-flushed after every append (always valid JSON; ~25 events max). The frontend folds events into state in `seq` order and re-renders. Person B builds against a hand-written fake file with this exact shape; the real backend swaps in at the end.

```jsonc
// outputs/frontend/events.json  — a JSON array of these records, in `seq` order.
// Specialist keys are exactly: "budget" | "enduser" | "itdata" | "risk"
[
  { "seq": 0, "type": "run_started",
    "initiative": "Deploy an AI copilot for our support agents",
    "sector": "SaaS", "org_size": "800 employees" },      // sector/org_size may be null

  { "seq": 1, "type": "node_created",
    "id": "e1", "parent_id": null,          // parent_id null => child of the root initiative node
    "label": "Support agents resolve tickets faster",
    "depth": 1,                             // 1 = direct effect, 2 = second-order effect
    "polarity": "positive",                 // "positive" | "negative" | "perverse"
    "assigned": ["enduser", "budget"] },    // 1+ specialist keys most relevant to this effect

  { "seq": 5, "type": "node_created",
    "id": "e1a", "parent_id": "e1",
    "label": "Agents deskill / over-rely on the copilot",
    "depth": 2, "polarity": "perverse", "assigned": ["enduser"] },

  { "seq": 8, "type": "specialist_called",  // marks specialist active + those nodes "awaiting" (pulse)
    "specialist": "enduser", "node_ids": ["e1", "e1a"] },

  { "seq": 12, "type": "stance_received",
    "specialist": "enduser", "node_id": "e1",
    "stance": "adopt",                      // "adopt" | "block" | "circumvent" | "escalate"
    "reaction": "Finally, something that clears the queue instead of adding to it." },  // verbatim quote

  { "seq": 16, "type": "node_pruned",       // fired when a DIRECT effect is blocked
    "node_id": "e2a",
    "reason": "Parent effect e2 blocked by IT/Data Owner" },

  { "seq": 20, "type": "run_finished",
    "docx": "ripple-risk-report.docx",
    "frontend_url": "http://localhost:8000" }
]
```

**Frontend status derivation (per node):** created ⇒ `pending` (grey, pulse while any assigned specialist hasn't returned). Any assigned stance `block` ⇒ `blocked` (red/grey). All assigned stances back, none block ⇒ `propagates` (green). `node_pruned` ⇒ `pre-empted` (muted grey), overrides everything. Clicking a node shows its `stance_received.reaction` quotes (grouped by specialist) in the side panel. Specialists panel = fixed 4, each showing its most recent stance as a color chip.

## Work split

| Person A — backend / scenario | Person B — frontend |
| --- | --- |
| 4 new `skills/*/SKILL.md` (budget-sponsor, end-user, it-data-owner, risk-compliance): incentives, 3–4 block/escalate triggers, voice guide | `outputs/frontend/index.html`: single self-contained vanilla-JS + inline-CSS page, no build step |
| Rewrite `create_specialists.py` → 4 new specialists (keep toolset + model mix) | Poll `events.json` every ~1s with cache-bust; fold events into state in `seq` order |
| Rewrite `create_coordinator.py` → "Change Impact Lead", new process instructions, emits `@@RIPPLE_EVENT@@ {json}` markers; **keep `multiagent: coordinator` config unchanged** | Render tree: root → direct → second-order via positioned divs / basic SVG lines; colors green/red-grey/muted-grey |
| Update `upload_skills.py` `SKILL_TO_SPECIALIST` map to the 4 new skills | Specialists panel (4 names + live stance color chips); click-node side panel with verbatim reaction |
| `synthetic-data/initiative-trigger.md` template (placeholders: initiative, optional sector, optional org size) | Pulse/"typing" indicator on `pending` nodes awaiting a stance |
| `run_ripple.py` (from `run_deal_desk.py`): CLI-arg initiative w/ interactive `input()` fallback; write trigger file; stream session; parse `@@RIPPLE_EVENT@@` markers and append+flush each to `outputs/frontend/events.json`; save `outputs/ripple-risk-report.docx` | Document exact serve command as a top-of-file comment: `python -m http.server 8000 --directory outputs/frontend` |
| Instruct coordinator to embed the `http://localhost:8000` **hyperlink** (caption "View the live stakeholder negotiation ->") in the docx Executive Summary via the docx skill | Build/test against a **hand-written fake `events.json`** (below) until integration |

**How the tree data actually flows:** the raw session stream only exposes generic thread/message events (same as Card A), so it *can't* describe individual effect nodes. The coordinator therefore emits one-line machine markers — `@@RIPPLE_EVENT@@ {…record…}` — as it works (one per node created, specialist called, stance received, prune, and finish). `run_ripple.py` scans the streamed `agent.message` text, parses each complete marker line, and appends it to `events.json`. Raw thread events still print to the console, so the **visible parallelism demo is unchanged**. This is the one additive change to coordinator instructions; the session/multiagent config is untouched.

**Why `events.json` lives at `outputs/frontend/events.json` (not a copy/symlink):** `run_ripple.py` writes directly there so `python -m http.server --directory outputs/frontend` serves both the page and its data with zero extra steps. Single source of truth, no sync.

**How the docx knows the frontend URL:** it's a fixed convention we own on both sides, not something discovered at runtime. `run_ripple.py` holds a constant `FRONTEND_URL = "http://localhost:8000"` (overridable via `--frontend-url`); the serve command pins the same port (`--directory outputs/frontend`, port 8000). Both hardcode 8000, so they always agree — `python -m http.server` is reachable at `http://localhost:8000` deterministically. `run_ripple.py` injects that string into the coordinator prompt, and the coordinator embeds it as a real hyperlink in the Executive Summary via the docx skill. If you serve on a different port, pass `--frontend-url http://localhost:PORT` and change the serve port to match.

## How to work in parallel
Person B does **not** wait for the backend. Start immediately against a hand-written `outputs/frontend/events.json` containing 5–6 sample records that match the schema above (one `run_started`, 2–3 `node_created` across both depths, a `specialist_called`, a `stance_received`, optionally a `node_pruned`). Build and eyeball the whole UI against that fake file. Only at integration do we run the real `run_ripple.py`, which overwrites that same file with live data — no frontend code changes needed if the schema held.

## Final integration checklist (do together, ~last 10 min)
1. Person A: `create_specialists.py` → `upload_skills.py` → `create_coordinator.py` all run clean (IDs written).
2. Start the frontend server: `python -m http.server 8000 --directory outputs/frontend`; open `http://localhost:8000`.
3. Run `python run_ripple.py "your demo initiative"` and confirm the tree grows + specialists react live in the browser.
4. Open `outputs/ripple-risk-report.docx`; confirm the Executive Summary hyperlink opens `http://localhost:8000`.
5. One full dry run end-to-end, narrating the parallel fan-out on the console.

## If we run out of time
- **Safe to cut:** frontend polish (SVG line elegance, pulse animation), any Round-2 persona back-and-forth, click-to-inspect side panel (tree + colors alone still demo well). Frontend can ship partially working or be dropped entirely.
- **Non-negotiable:** Part A must work **standalone with zero frontend** — the coordinator + 4 specialists + parallel fan-out + the **.docx produced via the required docx Skills API mechanism**. That is the hackathon's mandatory pattern; everything else is upside.
