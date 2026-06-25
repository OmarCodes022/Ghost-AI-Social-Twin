"""
Perception (Agent 1) evals.

Validates that Haiku's classifier outputs correct language, emotion, intent,
urgency, and attitude-shift labels on a golden dataset.
"""
import unittest


@unittest.skip("eval harness not wired up")
class ClassifierAccuracyEval(unittest.TestCase):
    def test_language_detection_french(self) -> None:
        """French messages must be labelled language=french."""

    def test_language_detection_english(self) -> None:
        """English messages must be labelled language=english."""

    def test_language_detection_arabic(self) -> None:
        """Arabic messages must be labelled language=arabic."""

    def test_mixed_language_resolved_to_dominant(self) -> None:
        """Franglais messages should resolve to the dominant language, not error."""

    def test_urgency_high_on_emergency_phrases(self) -> None:
        """'help', 'emergency', 'urgent' variants must produce urgency=high."""

    def test_attitude_shift_negative_on_anger(self) -> None:
        """Hostile messages must produce a negative attitude_shift value."""

    def test_attitude_shift_positive_on_affection(self) -> None:
        """Warm messages must produce a positive attitude_shift value."""

    def test_output_is_valid_json(self) -> None:
        """Classifier output must parse as JSON even when wrapped in code fences."""

    def test_no_hallucinated_fields(self) -> None:
        """Output must only contain schema-defined keys."""


@unittest.skip("eval harness not wired up")
class ClassifierLatencyEval(unittest.TestCase):
    def test_p50_under_2s(self) -> None:
        """Median classifier latency must be under 2 seconds."""

    def test_p99_under_5s(self) -> None:
        """99th-percentile classifier latency must stay under 5 seconds."""
