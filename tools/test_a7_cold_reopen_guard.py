#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

MODULE_PATH=pathlib.Path(__file__).with_name("gg_cloud_music_worker.py")
SPEC=importlib.util.spec_from_file_location("worker",MODULE_PATH)
worker=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)

CALLS=[{"name":"tracks_add","arguments":{}}]
RESPONSES=[{"name":"tracks_add","response":{"result":{"structuredContent":{"created":{"routes":[{"id":"219","name":"A7"}]}}}}}]

def cold(routes):
    return [{"name":"tracks_list","response":{"result":{"structuredContent":{"tracks":routes}}}}]

class ColdReopenGuardTest(unittest.TestCase):
    def test_accepts_same_route_after_reopen(self):
        result=worker.verify_cold_reopen_postcondition(CALLS,RESPONSES,cold([{"id":"219","name":"A7"}]))
        self.assertTrue(result["verified"])

    def test_rejects_missing_route(self):
        with self.assertRaisesRegex(RuntimeError,"COLD_REOPEN_POSTCONDITION_FAILED"):
            worker.verify_cold_reopen_postcondition(CALLS,RESPONSES,cold([]))

    def test_rejects_identity_drift(self):
        with self.assertRaisesRegex(RuntimeError,"COLD_REOPEN_POSTCONDITION_FAILED"):
            worker.verify_cold_reopen_postcondition(CALLS,RESPONSES,cold([{"id":"219","name":"OTHER"}]))

    def test_rejects_missing_creation_evidence(self):
        with self.assertRaisesRegex(RuntimeError,"no created routes"):
            worker.verify_cold_reopen_postcondition([],[],cold([]))

if __name__=="__main__": unittest.main()
