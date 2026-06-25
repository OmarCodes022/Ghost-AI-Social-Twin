"""
Decision quality evals.

Validates that Ghost picks the right action (reply / defer / escalate)
across a curated set of canonical scenarios.
"""
import unittest


@unittest.skip("eval harness not wired up")
class DecisionQualityEval(unittest.TestCase):
    def test_replies_to_casual_tier1_message(self) -> None:
        """Tier 1 casual message should produce action=reply."""

    def test_defers_when_context_is_missing(self) -> None:
        """If Ghost can't give a meaningful reply, action must be defer, not escalate."""

    def test_escalates_only_on_genuine_emergency(self) -> None:
        """Medical / suicidal / threat signals should trigger escalate; everything else should not."""

    def test_no_escalation_for_unknown_contact(self) -> None:
        """Not knowing a contact is NOT a reason to escalate — Ghost handles it."""

    def test_defer_condition_is_structured(self) -> None:
        """Defer action must include a well-formed condition object, not a freeform string."""

    def test_close_condition_always_set_on_reply(self) -> None:
        """Every reply action must carry a close_condition so Pulse can clean up."""

    def test_send_delay_is_reasonable(self) -> None:
        """send_delay_minutes must be between 0 and 120 for normal conversations."""

    def test_tool_budget_exhaustion_still_produces_decision(self) -> None:
        """If max tool rounds are hit, Ghost must still output a ghost_decision block."""


@unittest.skip("eval harness not wired up")
class EscalationRateEval(unittest.TestCase):
    """Escalation should be rare — target under 5% of real-world messages."""

    def test_escalation_rate_under_threshold(self) -> None:
        """Run sample corpus and assert escalation rate < 0.05."""

    def test_no_consecutive_escalations_for_same_contact(self) -> None:
        """Two back-to-back escalations for the same contact signals a prompt bug."""
