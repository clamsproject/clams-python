import json
import unittest
from builtins import object

import clams.restify
import clams.serve
from clams import Mmif, Medium, MediaTypes

dummy_attype = "http://clams.ai/vocab/dummy"


class ExampleInputMMIF(object):

    @staticmethod
    def get_mmif():
        mmif = Mmif(validate=False)
        mmif._context = "mmif-prototype-0.0.1.jsonld"
        mmif.add_medium(Medium({'id': 'm1', 'type': MediaTypes.V, 'location': "/dummy/dir/dummy.file.mp4"}))
        return str(mmif)


class TestSerialization(unittest.TestCase):

    def setUp(self):
        self.mmif = Mmif(ExampleInputMMIF.get_mmif(), validate=False)

    def test_view_is_empty(self):
        self.assertEqual(len(self.mmif.views), 0)


class ExampleClamsApp(clams.serve.ClamsApp):

    def appmetadata(self):
        return  {"name": "Tesseract OCR",
                 "description": "A dummy tool for testing",
                 "vendor": "Team CLAMS",
                 "requires": [],
                 "produces": [dummy_attype]}

    def sniff(self, mmif):
        return True

    def annotate(self, mmif):
        if type(mmif) is not Mmif:
            mmif = Mmif(mmif, validate=False)
        new_view = mmif.new_view()
        new_view.new_contain(dummy_attype, {"producer": "dummy-producer"})
        ann = new_view.new_annotation(dummy_attype, 'a1')
        ann.attype = dummy_attype
        ann.add_property("f1", "hello_world")
        return mmif


class TestClamsApp(unittest.TestCase):
    def setUp(self):
        self.app = ExampleClamsApp()
        self.in_mmif = ExampleInputMMIF.get_mmif()

    def test_appmedata(self):
        metadata = self.app.appmetadata
        # TODO (krim @ 9/3/19): more robust test cases
        self.assertIsNotNone(metadata)

    def test_sniff(self):
        self.assertTrue(self.app.sniff(self.in_mmif))

    def test_annotate(self):
        out_mmif = self.app.annotate(self.in_mmif)
        # TODO (krim @ 9/3/19): more robust test cases
        self.assertIsNotNone(out_mmif)


class TestRestifier(unittest.TestCase):

    def setUp(self):
        self.app = clams.Restifier(ExampleClamsApp()).test_client()

    def test_can_get(self):
        gotten = self.app.get('/')
        print(gotten.get_data())
        self.assertIsNotNone(gotten)

    def test_can_post(self):
        posted = self.app.post('/', data=ExampleInputMMIF.get_mmif())
        print(posted.get_data())
        self.assertIsNotNone(posted)

    def test_can_put(self):
        put = self.app.put('/', data=ExampleInputMMIF.get_mmif())
        print(put.get_data())
        self.assertIsNotNone(put)

    def test_can_put_as_json(self):
        put = self.app.put('/', data=ExampleInputMMIF.get_mmif(), headers={"Content-Type": "Application/json"})
        print(put.get_data())
        self.assertIsNotNone(put)


if __name__ == '__main__':
    unittest.main()
