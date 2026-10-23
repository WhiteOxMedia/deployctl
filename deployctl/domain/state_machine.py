"""Domain state machine for deployments.

This is the authoritative transition contract for the deployment lifecycle.
Right now it is intentionally small: it knows how to answer whether a target
status is a normal promotion target from a current status, and whether that
specific transition is allowed.

PromotionEngine depends on this and on the adapter contracts. It does not own
the adapter calls themselves, so the state machine stays focused on the
deployment lifecycle rules.
"""

from __future__ import annotations

from typing import Any

from deployctl.domain.aggregate.deployment import Deployment


class DomainStateMachine:
    """Rules for deployment status transitions.

    This is deliberately lightweight. It is not trying to model every future
    slice yet. It exists so PromotionEngine can ask two questions:

    - What is the normal promotion target from the current status?
    - Is the requested transition allowed?
    """

    def promotion_target(self, current_status: str) -> str | None:
        """Return the normal promotion target for the current status.

        Returns None when the current status has no promotion target.
        """
        targets: dict[str, str] = {
            "planned": "active",
            "active": "promoted",
            "promoted": "active",
        }
        return targets.get(current_status)

    def can_transition(self, current_status: str, target_status: str) -> bool:
        """Return True if the transition is allowed by the domain rules."""
        if current_status == target_status:
            return True
        if current_status == "planned" and target_status == "active":
            return True
        if current_status == "active" and target_status == "promoted":
            return True
        if current_status == "promoted" and target_status == "active":
            return True
        return False

    def next_status_for(self, deployment: Deployment, **context: Any) -> str | None:
        """Return the next allowed promotion status for a deployment.

        This exists so callers can ask the state machine directly about a
        deployment aggregate instead of extracting the status themselves.
        """
        return self.promotion_target(deployment.status)
