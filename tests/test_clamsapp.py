import unittest
from builtins import object
from typing import Union

import clams.restify
import clams.serve
from mmif import Mmif, Document, DocumentTypes, AnnotationTypes


AT_TYPE = AnnotationTypes.TimeFrame


class ExampleInputMMIF(object):

    @staticmethod
    def get_mmif():
        mmif = Mmif(validate=False, frozen=False)
        mmif.add_document(Document({'@type': DocumentTypes.VideoDocument.value,
                                    'properties':
                                        {'id': 'm1', 'location': "/dummy/dir/dummy.file.mp4"}}))
        return str(mmif)


class TestSerialization(unittest.TestCase):

    def setUp(self):
        self.mmif = Mmif(ExampleInputMMIF.get_mmif(), validate=False)

    def test_view_is_empty(self):
        self.assertEqual(len(self.mmif.views), 0)


class ExampleClamsApp(clams.serve.ClamsApp):

    def appmetadata(self):
        return {"name": "Tesseract OCR",
                "description": "A dummy tool for testing",
                "vendor": "Team CLAMS",
                "requires": [],
                "produces": [AT_TYPE]}

    def sniff(self, mmif):
        return True

    def annotate(self, mmif: Union[str, dict, Mmif]):
        if type(mmif) is not Mmif:
            mmif = Mmif(mmif, validate=False)
        new_view = mmif.new_view()
        new_view.new_contain(AT_TYPE, {"producer": "dummy-producer"})
        ann = new_view.new_annotation('a1', AT_TYPE)
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
