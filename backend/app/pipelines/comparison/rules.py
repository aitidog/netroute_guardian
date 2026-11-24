"""Pluggable importance classification rules for Stage 3 of the Comparison Pipeline."""

from __future__ import annotations

import ipaddress
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.pipelines.comparison.context import RouteDiffEntry


@dataclass(frozen=True)
class RuleMatchResult:
    """Outcome produced when an ImportanceRule matches a RouteDiffEntry."""

    rule_id: str
    reason: str


class ImportanceRule(ABC):
    """Single-responsibility rule evaluating whether a route difference is high-priority."""

    @abstractmethod
    def evaluate(self, entry: RouteDiffEntry) -> RuleMatchResult | None:
        """Return a RuleMatchResult if the entry triggers this rule, otherwise None."""


class LargePrefixRule(ImportanceRule):
    """Flags broad subnets (prefix length <= threshold, default /20) that are removed or changed."""

    def __init__(self, max_prefix_len: int = 20) -> None:
        self.max_prefix_len = max_prefix_len

    def evaluate(self, entry: RouteDiffEntry) -> RuleMatchResult | None:
        if entry.change_type not in ("removed", "changed"):
            return None
        if entry.prefix_len <= self.max_prefix_len:
            action = "missing" if entry.change_type == "removed" else "changed"
            return RuleMatchResult(
                rule_id="large_prefix",
                reason=(f"Large subnet mask (/{entry.prefix_len} <= /{self.max_prefix_len}) is {action}"),
            )
        return None


class PreSpecifiedRouteRule(ImportanceRule):
    """Flags exact matches against the user-configured list of critical prefixes."""

    def __init__(self, prefixes: list[str]) -> None:
        canonical: set[str] = set()
        for raw in prefixes:
            cleaned = raw.strip()
            if not cleaned:
                continue
            canonical.add(str(ipaddress.ip_network(cleaned, strict=False)))
        self._prefixes = canonical

    def evaluate(self, entry: RouteDiffEntry) -> RuleMatchResult | None:
        if entry.change_type not in ("removed", "changed"):
            return None
        if entry.prefix in self._prefixes:
            action = "missing" if entry.change_type == "removed" else "changed"
            return RuleMatchResult(
                rule_id="pre_specified_route",
                reason=f"Matches pre-specified critical route ({entry.prefix}) and is {action}",
            )
        return None
