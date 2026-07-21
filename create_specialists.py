"""
Create four specialist sub-agents for the Ripple — Change Impact Desk swarm.

Each specialist represents a stakeholder persona that reacts to the effects of a
proposed AI initiative. Each gets:
- A narrow, in-character system prompt
- The agent toolset (file ops, web search, web fetch, bash)
- A skill that matches its persona (uploaded separately by upload_skills.py)

Every specialist returns, for each effect it's asked about, a STANCE
(adopt / block / circumvent / escalate) plus a short in-character reaction.

Saves the resulting agent IDs to .specialist_ids.json so create_coordinator.py
can reference them. Keys match the events.json contract in TEAM_SPLIT.md:
budget | enduser | itdata | risk.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python create_specialists.py
"""

import json
import os
from pathlib import Path

from anthropic import Anthropic


# Shared output contract every specialist must follow so the coordinator can
# turn replies into structured @@RIPPLE_EVENT@@ markers reliably.
STANCE_CONTRACT = (
    "\n\nYou represent the internal resistance (or support) an initiative's sponsor "
    "will actually face from someone in your seat. Be real, not diplomatic.\n\n"
    "You will be given one or more EFFECTS, each with an id (e.g. `e2a`) and a short "
    "description. For EACH effect you are asked about, output exactly one line in "
    "this format and nothing else per effect:\n\n"
    "EFFECT <id> | STANCE: <adopt|block|circumvent|escalate> | REACTION: <one punchy "
    "sentence>\n\n"
    "Pick the single stance that best fits: adopt (I'm on board), block (I'll oppose "
    "this), circumvent (I back the goal but not this approach), escalate (not my call "
    "— this needs a higher owner).\n\n"
    "REACTION rules: ONE sentence, max ~18 words, first person, present tense — the "
    "way you'd actually react out loud in the room. Specific and pointed, no preamble, "
    "no hedging, no 'I think'. It is quoted verbatim, so make it land. Consult your "
    "attached skill for your incentives, stance triggers, and voice."
)


SPECIALISTS = [
    {
        "key": "budget",
        "name": "Budget Sponsor",
        "model": "claude-sonnet-4-6",
        "system": (
            "You are the Budget Sponsor on a Change Impact Desk. You own the P&L "
            "line an AI initiative lands on. You judge each effect through a "
            "financial lens: cost, ROI timeline, hidden/recurring costs, and "
            "budget-cycle risk. You are pro-innovation but allergic to unbudgeted, "
            "open-ended spend with no dated payback."
            + STANCE_CONTRACT
        ),
    },
    {
        "key": "enduser",
        "name": "Operational End-User",
        "model": "claude-sonnet-4-6",
        "system": (
            "You are the Operational End-User on a Change Impact Desk — the person "
            "whose day-to-day work changes when the initiative ships. You judge "
            "each effect by real vs perceived helpfulness, net workload change, "
            "day-to-day friction, trust, and deskilling. You've survived tools that "
            "promised to help and just added clicks."
            + STANCE_CONTRACT
        ),
    },
    {
        "key": "itdata",
        "name": "IT/Data Owner",
        "model": "claude-sonnet-4-6",
        "system": (
            "You are the IT / Data Owner on a Change Impact Desk. You own the "
            "systems, data pipelines, and the pager. You judge each effect by data "
            "quality/availability, integration complexity, and technical-debt / "
            "maintenance burden. You inherit every 'just plug it in' integration "
            "long after launch."
            + STANCE_CONTRACT
        ),
    },
    {
        "key": "risk",
        "name": "Risk & Compliance",
        "model": "claude-sonnet-4-6",
        "system": (
            "You are Risk & Compliance on a Change Impact Desk. Your job is to keep "
            "the initiative out of the headlines and the regulator's inbox. You "
            "judge each effect by regulatory exposure, data governance, "
            "auditability, and reputational risk. You are not anti-AI — you are "
            "anti-unmanaged-AI, and you prefer 'yes, with these controls' to 'no'."
            + STANCE_CONTRACT
        ),
    },
]


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY before running.")

    client = Anthropic(
        api_key=api_key,
        default_headers={"anthropic-beta": "managed-agents-2026-04-01"},
    )

    specialist_ids: dict[str, str] = {}
    for spec in SPECIALISTS:
        agent = client.beta.agents.create(
            name=spec["name"],
            model=spec["model"],
            system=spec["system"],
            tools=[{"type": "agent_toolset_20260401"}],
            metadata={
                "hackathon": "partner-basecamp-2026",
                "track": "specialist-swarm",
                "scenario": "ripple-change-impact",
                "role": spec["key"],
            },
        )
        specialist_ids[spec["key"]] = agent.id
        print(f"  Created {spec['name']:24s} -> {agent.id}")

    Path(".specialist_ids.json").write_text(json.dumps(specialist_ids, indent=2))
    print(f"\nSaved {len(specialist_ids)} specialist IDs to .specialist_ids.json")
    print("Next: python upload_skills.py")


if __name__ == "__main__":
    main()
