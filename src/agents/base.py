"""
Base class for all specialist agents.

Each specialist wraps a focused system prompt, a set of owned metrics from
the catalog, and the data-tier context needed to answer its class of
questions.  The base class provides the shared scaffolding; subclasses
override ``build_context`` to prepare metric-specific data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.agents.routing import AgentSpec, get_agent_spec
from src.tools.metric_catalog import MetricDefinition, list_metrics
from src.tools.query_tools import apply_tier


@dataclass
class AgentResponse:
    """Structured output from a specialist agent invocation."""

    agent_name: str
    intent: str
    metrics_used: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    caveats: list[str] = field(default_factory=list)
    suggested_follow_ups: list[str] = field(default_factory=list)


class BaseAgent(ABC):
    """Skeleton that every specialist inherits."""

    def __init__(self, name: str) -> None:
        self.spec: AgentSpec = get_agent_spec(name)
        self.owned_metrics: list[MetricDefinition] = list_metrics(
            owner_agent=self.spec.owned_metric_prefix,
        )

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def system_prompt(self) -> str:
        return self.spec.system_prompt

    def prepare_data(self, df: pd.DataFrame, *, tier: int | None = None) -> pd.DataFrame:
        """Filter *df* to the agent's default tier (or an explicit override)."""
        effective_tier = tier if tier is not None else self.spec.default_tier
        return apply_tier(df, effective_tier)

    @abstractmethod
    def build_context(
        self,
        df: pd.DataFrame,
        question: str,
        *,
        period: str | None = None,
        country: str | None = None,
    ) -> AgentResponse:
        """Compute metrics and assemble a response for *question*.

        Subclasses implement the domain-specific logic here.  The supervisor
        calls this method after routing.
        """
