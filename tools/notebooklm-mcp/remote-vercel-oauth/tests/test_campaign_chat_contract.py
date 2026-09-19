from pathlib import Path
import unittest


class CampaignChatContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")

    def test_regular_chat_honors_source_scope_and_conversation_id(self):
        block = self.app.split('elif operation == "chat_ask":', 1)[1].split(
            'elif operation == "chat_reset":', 1
        )[0]
        self.assertIn('_normalize_source_ids(args.get("source_ids"))', block)
        self.assertIn('await _validate_source_ids(client, nb_id, source_ids)', block)
        self.assertIn('source_ids=source_ids', block)
        self.assertIn('conversation_id=conversation_id', block)
        self.assertIn('_out_of_scope_citations(answer_payload, source_ids)', block)
        self.assertIn('"chat_scope_violation"', block)

    def test_chat_reset_deletes_current_conversation(self):
        self.assertIn('async def _reset_current_chat(client, notebook_id: str)', self.app)
        helper = self.app.split(
            'async def _reset_current_chat(client, notebook_id: str)', 1
        )[1].split('async def github_bridge', 1)[0]
        self.assertIn('client.chat.get_conversation_id(notebook_id)', helper)
        self.assertIn('client.chat.delete_conversation(notebook_id, conversation_id)', helper)

    def test_fresh_chat_is_scoped_atomic_and_fail_closed(self):
        block = self.app.split('elif operation == "chat_ask_fresh":', 1)[1].split(
            'elif operation == "notebook_create":', 1
        )[0]
        self.assertIn('args.get("confirm_reset") is not True', block)
        self.assertIn('"source_ids_required"', block)
        self.assertIn('await _validate_source_ids(client, nb_id, source_ids)', block)
        self.assertIn('deleted_conversation_id = await _reset_current_chat(client, nb_id)', block)
        self.assertIn('source_ids=source_ids', block)
        self.assertIn('conversation_id=None', block)
        self.assertIn('_out_of_scope_citations(answer_payload, source_ids)', block)
        self.assertIn('"chat_scope_violation"', block)
        self.assertIn('"fresh_conversation_not_established"', block)
        self.assertIn('"fresh_conversation": True', block)

    def test_scope_validation_rejects_unknown_sources(self):
        self.assertIn('async def _validate_source_ids(', self.app)
        self.assertIn('"unknown_source_ids:" + ",".join(missing)', self.app)


if __name__ == "__main__":
    unittest.main()
