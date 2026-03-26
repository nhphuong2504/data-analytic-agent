"""
Supervisor agent: classifies the business question, routes to specialists,
collects responses, and assembles a unified answer.

The supervisor never computes metrics itself — it delegates to specialist
agents and then optionally wraps the result through the Narrative agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.agents.base import AgentResponse, BaseAgent
from src.agents.routing import (
    Intent,
    RoutePlan,
    build_route,
    get_agent_spec,
)


@dataclass
class SupervisorResult:
    """Final assembled output returned to the UI layer."""

    question: str
    route: RoutePlan
    specialist_responses: list[AgentResponse] = field(default_factory=list)
    data_quality_response: AgentResponse | None = None
    narrative: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)


class SupervisorAgent:
    """Orchestrates the routing and response-assembly pipeline.

    Usage::

        supervisor = SupervisorAgent()
        supervisor.register_specialist("KpiStrategy", kpi_agent)
        supervisor.register_specialist("CustomerAnalytics", customer_agent)
        ...
        result = supervisor.handle(df, "What is total revenue this month?")
    """

    def __init__(self) -> None:
        self._specialists: dict[str, BaseAgent] = {}
        self._narrative_agent: BaseAgent | None = None
        self._dq_agent: BaseAgent | None = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_specialist(self, name: str, agent: BaseAgent) -> None:
        """Register a specialist agent under *name*."""
        if name == "Narrative":
            self._narrative_agent = agent
        elif name == "DataQuality":
            self._dq_agent = agent
        self._specialists[name] = agent

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def handle(
        self,
        df: pd.DataFrame,
        question: str,
        *,
        period: str | None = None,
        country: str | None = None,
    ) -> SupervisorResult:
        """Classify *question*, route to specialists, and return a result."""
        route = build_route(question)

        result = SupervisorResult(question=question, route=route)

        if route.include_data_quality and self._dq_agent is not None:
            result.data_quality_response = self._dq_agent.build_context(
                df, question, period=period, country=country,
            )

        for agent_name in route.primary_agents:
            agent = self._specialists.get(agent_name)
            if agent is None:
                result.specialist_responses.append(
                    AgentResponse(
                        agent_name=agent_name,
                        intent=route.intent.value,
                        summary=f"[{agent_name}] agent not registered — skipped.",
                        caveats=[f"Specialist '{agent_name}' is not available."],
                    )
                )
                continue

            response = agent.build_context(
                df, question, period=period, country=country,
            )
            result.specialist_responses.append(response)

        if route.include_narrative and self._narrative_agent is not None:
            result.narrative = self._assemble_narrative(
                result.specialist_responses,
                result.data_quality_response,
            )

        result.raw_data = self._collect_raw_data(result.specialist_responses)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _assemble_narrative(
        responses: list[AgentResponse],
        dq: AgentResponse | None,
    ) -> str:
        """Combine specialist summaries into a single narrative string.

        In v1 this is a simple concatenation. A future version can pass
        these through an LLM-backed Narrative agent for polishing.
        """
        parts: list[str] = []
        if dq and dq.caveats:
            parts.append("Data caveats: " + "; ".join(dq.caveats))
        for r in responses:
            if r.summary:
                parts.append(r.summary)
        return "\n\n".join(parts)

    @staticmethod
    def _collect_raw_data(responses: list[AgentResponse]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for r in responses:
            merged.update(r.data)
        return merged
