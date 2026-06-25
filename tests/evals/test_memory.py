"""
Memory retrieval evals.

Checks that RAG search returns relevant results and SQL queries
against ghost-owned tables produce correct, well-formed output.
"""
import unittest


@unittest.skip("eval harness not wired up")
class RagRetrievalEval(unittest.TestCase):
    def test_identity_memory_top_result_is_relevant(self) -> None:
        """Query about Omar's habits must surface identity memories, not contact memories."""

    def test_contact_memory_scoped_correctly(self) -> None:
        """Contact-scoped query must not surface memories from unrelated contacts."""

    def test_multilingual_query_retrieves_cross_language(self) -> None:
        """French query must retrieve English-language memories about the same concept."""

    def test_embedding_similarity_threshold(self) -> None:
        """Results with cosine similarity below 0.6 must be filtered out."""

    def test_empty_query_returns_empty(self) -> None:
        """Blank or whitespace-only query must return no results without erroring."""


@unittest.skip("eval harness not wired up")
class SqlToolEval(unittest.TestCase):
    def test_ghost_state_update_persists(self) -> None:
        """sql_query UPDATE to ghost_state must be readable in the next turn."""

    def test_read_only_query_on_protected_tables(self) -> None:
        """Ghost must not be able to DROP or TRUNCATE core tables via sql_query."""

    def test_sql_injection_in_contact_name_is_safe(self) -> None:
        """Contact names with SQL metacharacters must not break queries."""

    def test_ghost_custom_table_free_schema(self) -> None:
        """Ghost can CREATE and INSERT into ghost_custom without schema validation."""


@unittest.skip("eval harness not wired up")
class MemoryIngestionEval(unittest.TestCase):
    def test_freeform_chunks_embedded_correctly(self) -> None:
        """Freeform ingest must produce one embedding per chunk, all dimension=1024."""

    def test_whatsapp_ingest_contact_stub_created(self) -> None:
        """WhatsApp ingest must create or update the contact row before inserting memories."""

    def test_duplicate_ingest_is_idempotent(self) -> None:
        """Re-running ingest on the same file must not create duplicate memory rows."""
