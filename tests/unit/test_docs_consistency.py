from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DocsConsistencyTest(unittest.TestCase):
    def test_agent_docs_are_current(self) -> None:
        readme = (ROOT / "README.md").read_text()
        claude = (ROOT / "CLAUDE.md").read_text()

        self.assertIn("Claude then has 9 tools", readme)
        self.assertNotIn("search_memories` |", readme)
        self.assertIn("Strands `Agent`", claude)
