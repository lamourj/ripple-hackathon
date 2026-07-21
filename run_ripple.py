"""
Run the Ripple — Change Impact Desk swarm against a one-sentence AI initiative.

Adapted from run_deal_desk.py. Same proven session/multi-agent mechanics — this
just feeds a different trigger and, as a purely additive layer, harvests the
coordinator's inline `@@RIPPLE_EVENT@@ {json}` markers into a live event stream
the frontend renders in real time.

What it does:
  1. Takes the initiative from a CLI arg (with an interactive fallback prompt).
  2. Fills synthetic-data/initiative-trigger.md and inlines it as the trigger.
  3. Starts a session against the Change Impact Lead coordinator.
  4. Streams events — prints the raw parallel fan-out to the console (the demo)
     AND parses @@RIPPLE_EVENT@@ markers into outputs/frontend/events.json,
     flushing after every event so the frontend updates live.
  5. Saves the final Ripple Risk Report to outputs/ripple-risk-report.docx.

The frontend URL embedded in the docx is a fixed convention (default
http://localhost:8000, override with --frontend-url). Serve the frontend with:
    python -m http.server 8000 --directory outputs/frontend

Usage:
    python run_ripple.py "Deploy an AI copilot for our support agents"
    python run_ripple.py "..." --sector "Healthcare" --org-size "5,000 employees"
    python run_ripple.py            # no arg -> interactive prompt
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from anthropic import Anthropic


TRIGGER_TEMPLATE = Path("synthetic-data/initiative-trigger.md")
OUTPUT_DIR = Path("outputs")
FRONTEND_DIR = OUTPUT_DIR / "frontend"
EVENTS_PATH = FRONTEND_DIR / "events.json"
DEFAULT_FRONTEND_URL = "http://localhost:8000"

MARKER = "@@RIPPLE_EVENT@@"


class EventLog:
    """Owns outputs/frontend/events.json: assigns the single monotonic `seq`,
    appends records, and writes the whole array atomically after each append so
    the polling frontend never reads a half-written file."""

    def __init__(self, path: Path):
        self.path = path
        self.events: list[dict] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._flush()  # start every run from a clean, valid empty array

    def append(self, record: dict) -> dict:
        record = {"seq": len(self.events), **record}
        self.events.append(record)
        self._flush()
        return record

    def _flush(self) -> None:
        # Atomic replace: write a temp file in the same dir, then os.replace.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self.events, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


class MarkerParser:
    """Buffers streamed coordinator text and yields parsed @@RIPPLE_EVENT@@
    records as complete marker lines arrive."""

    def __init__(self):
        self._buf = ""

    def feed(self, text: str) -> list[dict]:
        self._buf += text
        out: list[dict] = []
        # Process only fully-terminated lines; keep the trailing partial in buf.
        *lines, self._buf = self._buf.split("\n")
        for line in lines:
            rec = self._parse_line(line)
            if rec is not None:
                out.append(rec)
        return out

    @staticmethod
    def _parse_line(line: str) -> dict | None:
        idx = line.find(MARKER)
        if idx == -1:
            return None
        payload = line[idx + len(MARKER):].strip()
        if not payload:
            return None
        try:
            rec = json.loads(payload)
        except json.JSONDecodeError:
            print(f"\n  [marker: unparseable JSON skipped] {payload[:80]}", flush=True)
            return None
        if isinstance(rec, dict) and "type" in rec:
            return rec
        return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the Ripple Change Impact Desk swarm.")
    p.add_argument("initiative", nargs="?", help="One-sentence AI initiative.")
    p.add_argument("--sector", default=None, help="Optional sector, e.g. 'Healthcare'.")
    p.add_argument("--org-size", dest="org_size", default=None,
                   help="Optional org size, e.g. '5,000 employees'.")
    p.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL,
                   help=f"Live-frontend URL embedded in the docx (default {DEFAULT_FRONTEND_URL}).")
    return p.parse_args()


def resolve_initiative(arg: str | None) -> str:
    """CLI arg is the primary path; fall back to an interactive prompt."""
    if arg and arg.strip():
        return arg.strip()
    try:
        text = input("\nEnter the one-sentence AI initiative:\n> ").strip()
    except EOFError:
        text = ""
    if not text:
        raise SystemExit("No initiative provided. Pass one as an argument or type it in.")
    return text


def build_trigger(initiative: str, sector: str | None, org_size: str | None) -> str:
    """Fill the trigger template and return the filled text. The template itself
    is NEVER overwritten — placeholders must survive for the next run — so the
    filled copy is persisted to outputs/ for the record instead."""
    template = TRIGGER_TEMPLATE.read_text()
    filled = (
        template
        .replace("{{INITIATIVE}}", initiative)
        .replace("{{SECTOR}}", sector or "(not specified)")
        .replace("{{ORG_SIZE}}", org_size or "(not specified)")
    )
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "initiative-trigger.filled.md").write_text(filled)
    return filled


def main() -> None:
    args = parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY before running.")
    if not Path(".coordinator_id").exists() or not Path(".environment_id").exists():
        raise SystemExit(
            "Missing .coordinator_id or .environment_id. Run create_specialists.py, "
            "upload_skills.py, then create_coordinator.py first."
        )

    initiative = resolve_initiative(args.initiative)
    sector, org_size, frontend_url = args.sector, args.org_size, args.frontend_url

    coordinator_id = Path(".coordinator_id").read_text().strip()
    environment_id = Path(".environment_id").read_text().strip()
    client = Anthropic()

    trigger_text = build_trigger(initiative, sector, org_size)

    # Fresh live event stream; emit run_started immediately (seq 0) so the
    # frontend can render the root node before the coordinator produces anything.
    OUTPUT_DIR.mkdir(exist_ok=True)
    events = EventLog(EVENTS_PATH)
    events.append({
        "type": "run_started",
        "initiative": initiative,
        "sector": sector,
        "org_size": org_size,
    })
    print(f"\nLive events -> {EVENTS_PATH}")
    print(f"Serve the frontend with:\n  python -m http.server 8000 --directory {FRONTEND_DIR}\n")

    print(f"Starting session against coordinator {coordinator_id}...")
    session = client.beta.sessions.create(
        agent=coordinator_id,
        environment_id=environment_id,
        title=f"Ripple — {initiative[:60]}",
    )
    Path(".last_session_id").write_text(session.id)

    user_message = (
        "A new AI initiative has been proposed. Run the full Ripple Change Impact "
        "process on it, emitting live @@RIPPLE_EVENT@@ markers as you go, and "
        "produce the Ripple Risk Report as a branded Word document via the docx "
        "skill.\n\n"
        "In the report's Executive Summary, include a clickable hyperlink to the "
        f"live stakeholder negotiation at {frontend_url} with the caption text "
        "\"View the live stakeholder negotiation ->\".\n\n"
        f"{trigger_text}"
    )

    parser = MarkerParser()

    print("\n=== EVENT STREAM (this is the demo) ===\n")
    final_text_parts: list[str] = []

    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[{"type": "user.message",
                     "content": [{"type": "text", "text": user_message}]}],
        )
        for event in stream:
            t = event.type
            if t == "session.thread_created":
                print(f"  [thread spawned]   {event.agent_name}", flush=True)
            elif t == "session.thread_status_running":
                name = getattr(event, "agent_name", "?")
                print(f"  [thread running]   {name}", flush=True)
            elif t == "agent.thread_message_received":
                print(f"  [reply <-]         {event.from_agent_name}", flush=True)
            elif t == "agent.thread_message_sent":
                print(f"  [delegate ->]      {event.to_agent_name}", flush=True)
            elif t == "agent.message":
                for block in event.content:
                    if getattr(block, "type", None) == "text":
                        final_text_parts.append(block.text)
                        # Harvest any complete markers, then show the prose.
                        for rec in parser.feed(block.text):
                            saved = events.append(rec)
                            print(f"\n  [event #{saved['seq']:02d}] "
                                  f"{saved['type']}", flush=True)
                        print(block.text, end="", flush=True)
            elif t == "agent.tool_use":
                print(f"\n  [tool: {getattr(event, 'name', '?')}]", flush=True)
            elif t == "session.status_idle":
                print("\n\n[swarm finished]")
                break

    # Save the coordinator transcript.
    (OUTPUT_DIR / "coordinator-transcript.txt").write_text("".join(final_text_parts))

    # Download deliverables; save the docx as the canonical report name.
    print("\nDownloading deliverables from the session container...")
    files = client.beta.files.list(scope_id=session.id, betas=["managed-agents-2026-04-01"])
    docx_saved = False
    for f in files.data:
        if f.filename.lower().endswith(".docx"):
            out_path = OUTPUT_DIR / "ripple-risk-report.docx"
            docx_saved = True
        else:
            out_path = OUTPUT_DIR / f.filename
        print(f"  {f.filename}  ->  {out_path}")
        client.beta.files.download(f.id).write_to_file(str(out_path))

    if not docx_saved:
        print("  WARNING: no .docx produced — the coordinator may have output text only.")

    events.append({
        "type": "run_finished",
        "docx": "ripple-risk-report.docx" if docx_saved else None,
        "frontend_url": frontend_url,
    })

    print(f"\nRipple Risk Report -> {OUTPUT_DIR / 'ripple-risk-report.docx'}")
    print(f"Live event stream   -> {EVENTS_PATH}  ({len(events.events)} events)")
    print(f"\nView the full session (all sub-agent threads) at:")
    print(f"  https://platform.claude.com/sessions/{session.id}")


if __name__ == "__main__":
    main()
