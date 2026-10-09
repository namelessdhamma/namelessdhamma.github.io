import json,unittest,pathlib
J=pathlib.Path(__file__).parent/'SOULX_AWATA_RESULT.json'
class RouteGate(unittest.TestCase):
    def setUp(self): self.j=json.loads(J.read_text(encoding='utf-8'))
    def test_no_false_pass(self): self.assertNotIn('ACCEPT',self.j['audio_quality_decision'])
    def test_source_good(self): self.assertEqual(self.j['source_cer'],0)
    def test_output_bad(self): self.assertGreater(self.j['output_cer'],0.1)
    def test_human_not_approved(self): self.assertNotEqual(self.j['user_acceptance'],'ACCEPTED')
    def test_isolated_master(self): self.assertFalse(self.j['production_master_changed'])
    def test_source_license(self): self.assertFalse(self.j['mimosa_input'])
    def test_whisper_separate(self): self.assertEqual(self.j['whisper'],'deferred')
if __name__=='__main__':unittest.main()