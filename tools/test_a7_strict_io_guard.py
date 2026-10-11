#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest

MODULE_PATH=pathlib.Path(__file__).with_name("gg_cloud_music_worker.py")
SPEC=importlib.util.spec_from_file_location("worker",MODULE_PATH)
worker=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)

CALLS=[{"name":"tracks_add","arguments":{"strictIo":True}}]
RESPONSES=[{"name":"tracks_add","response":{"result":{"structuredContent":{"created":{"routes":[{"id":"219","name":"A7"}]}}}}}]

class StrictIoGuardTest(unittest.TestCase):
    def session(self,value):
        p=pathlib.Path(tempfile.mkdtemp())/"test.ardour"
        p.write_text(f'<Session><Routes><Route id="219" name="A7" strict-io="{value}"/></Routes></Session>')
        return p

    def test_accepts_persisted_strict_io(self):
        self.assertTrue(worker.verify_strict_io_postcondition(self.session("1"),CALLS,RESPONSES)["verified"])

    def test_rejects_run74_observed_value(self):
        with self.assertRaisesRegex(RuntimeError,"STRICT_IO_POSTCONDITION_FAILED"):
            worker.verify_strict_io_postcondition(self.session("0"),CALLS,RESPONSES)

    def test_no_request_is_explicit_noop(self):
        result=worker.verify_strict_io_postcondition(self.session("0"),[],[])
        self.assertEqual(result,{"requested":False,"verified":True,"routes":[]})

if __name__=="__main__": unittest.main()
