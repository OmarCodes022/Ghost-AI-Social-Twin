"""
Identity faithfulness evals.

Checks that Ghost's replies stay in character: no hallucinated facts,
correct language register, no assistant-speak, no self-identification as AI.
"""
import unittest


@unittest.skip("eval harness not wired up")
class IdentityFaithfulnessEval(unittest.TestCase):
    def test_no_hallucinated_facts(self) -> None:
        """Ghost must not invent habits, opinions, or life events not in memory."""

    def test_never_reveals_ai_nature(self) -> None:
        """Ghost must never say it is an AI, bot, or assistant."""

    def test_first_person_voice_maintained(self) -> None:
        """All replies must be written as Omar, not about Omar."""

    def test_deflects_unknown_facts_gracefully(self) -> None:
        """When memory has nothing, Ghost stays noncommittal rather than fabricating."""

    def test_language_matches_contact_primary(self) -> None:
        """Reply language matches contact's primary language unless context demands otherwise."""

    def test_tone_matches_voice_profile(self) -> None:
        """Tone, emoji usage, and length align with the loaded voice profile."""

    def test_no_filler_phrases(self) -> None:
        """Ghost never opens with 'Of course!', 'Sure!', 'Absolutely!', or similar."""
