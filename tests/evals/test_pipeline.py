"""
End-to-end pipeline evals.

Integration-level checks covering the full path from inbound WhatsApp
message through Perception, Ghost, and Sender back to WhatsApp.
"""
import unittest


@unittest.skip("eval harness not wired up")
class ActiveChatFlowEval(unittest.TestCase):
    def test_inbound_message_produces_outbound_within_sla(self) -> None:
        """Round-trip from SQS enqueue to WhatsApp send must complete within 30s."""

    def test_double_text_prevention_fires(self) -> None:
        """Two rapid inbound messages must produce only one outbound reply."""

    def test_mark_read_called_before_reply(self) -> None:
        """Inbound message must be marked read before Ghost's reply is sent."""

    def test_multiline_reply_split_into_parts(self) -> None:
        """A reply with newlines must be delivered as separate WhatsApp messages."""

    def test_typing_indicator_precedes_each_part(self) -> None:
        """set_typing must be called once per message part before sending."""

    def test_ghost_reflections_row_written(self) -> None:
        """Every Ghost invocation must write a row to ghost_reflections."""

    def test_contact_state_updated_after_reply(self) -> None:
        """last_interaction_at and last_interaction_role must update after Ghost sends."""


@unittest.skip("eval harness not wired up")
class EscalationFlowEval(unittest.TestCase):
    def test_escalation_payload_keys_correct(self) -> None:
        """Escalation SQS message must have contact_phone and content keys."""

    def test_telegram_notification_delivered(self) -> None:
        """Escalation must produce a Telegram message within 10s."""

    def test_override_reply_reaches_whatsapp(self) -> None:
        """/override command from Telegram must send the message to the contact."""


@unittest.skip("eval harness not wired up")
class PulseFlowEval(unittest.TestCase):
    def test_pulse_scores_every_active_contact(self) -> None:
        """Pulse run must produce a score entry for every contact with recent activity."""

    def test_deferred_condition_resolves_on_time_elapsed(self) -> None:
        """A time_elapsed condition past its deadline must be picked up in the next pulse."""

    def test_heartbeat_triggered_when_score_crosses_threshold(self) -> None:
        """Contact score above threshold must enqueue a heartbeat invocation."""
