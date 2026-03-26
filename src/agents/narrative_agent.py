"""
Narrative (Storytelling) specialist — translates metric-backed outputs
from other agents into executive-ready summaries.

Responsibilities:
  - Rewrite raw metric outputs in plain business English
  - Highlight the most important insight first
  - Attach data caveats from the Data Quality agent
  - Suggest 2-3 follow-up questions

Does not own any metrics directly and never computes data itself.
In v1 this is a deterministic formatter; v2 can route through an LLM.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.agents.base import AgentResponse, BaseAgent


class NarrativeAgent(BaseAgent):
    """Formats specialist outputs into cohesive executive narratives."""

    def __init__(self) -> None:
        super().__init__("Narrative")

    def build_context(
        self,
        df: pd.DataFrame,
        question: str,
        *,
        period: str | None = None,
        country: str | None = None,
    ) -> AgentResponse:
        return AgentResponse(
            agent_name=self.name,
            intent="narrative",
            summary="[Narrative agent placeholder — see compose_narrative]",
        )

    def compose_narrative(
        self,
        question: str,
        specialist_responses: list[AgentResponse],
        dq_response: AgentResponse | None = None,
    ) -> str:
        """Assemble a final executive-ready narrative from specialist outputs."""
        sections: list[str] = []

        if dq_response and dq_response.caveats:
            caveat_text = "; ".join(dq_response.caveats)
            sections.append(f"**Data note:** {caveat_text}")

        for resp in specialist_responses:
            if resp.summary:
                sections.append(resp.summary)

        follow_ups: list[str] = []
        for resp in specialist_responses:
            follow_ups.extend(resp.suggested_follow_ups)
        unique_follow_ups = list(dict.fromkeys(follow_ups))[:3]

        if unique_follow_ups:
            suggestions = "\n".join(f"  - {q}" for q in unique_follow_ups)
            sections.append(f"**You might also ask:**\n{suggestions}")

        return "\n\n".join(sections)
