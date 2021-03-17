import unittest

from mmif import Mmif, Document, DocumentTypes, AnnotationTypes

import clams.app
import clams.restify

AT_TYPE = AnnotationTypes.TimeFrame


class ExampleInputMMIF(object):

    @staticmethod
    def get_mmif():
        mmif = Mmif(validate=False, frozen=False)
        mmif.add_document(Document({'@type': DocumentTypes.VideoDocument.value,
                                    'properties':
                                        {'id': 'm1', 'location': "/dummy/dir/dummy.file.mp4"}}))
        return mmif.serialize()


class TestSerialization(unittest.TestCase):

    def setUp(self):
        self.mmif = Mmif(ExampleInputMMIF.get_mmif())

    def test_view_is_empty(self):
        self.assertEqual(len(self.mmif.views), 0)


class ExampleClamsApp(clams.app.ClamsApp):

    def _appmetadata(self):
        return {"name": "Tesseract OCR",
                "description": "A dummy tool for testing",
                "vendor": "Team CLAMS",
                "requires": [],
                "produces": [AT_TYPE.value]}

    def _annotate(self, mmif):
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
        self.assertIsNotNone(put)
        self.assertEqual(put.status_code, 200)
        self.assertIsNotNone(Mmif(put.get_data()))

    def test_can_pass_params(self):
        mmif = ExampleInputMMIF.get_mmif()
        headers = {"Content-Type": "Application/json"}
        query_string = {'pretty': True}
        pretty_res = self.app.put('/', data=mmif, headers=headers, query_string=query_string)
        self.assertEqual(pretty_res.status_code, 200, pretty_res.get_data(as_text=True))
        self.assertIsNotNone(Mmif(pretty_res.get_data(as_text=True)))
        pretty_to_mmif = Mmif(pretty_res.get_data(as_text=True))
        unpretty_res = self.app.put('/', data=mmif, headers=headers)
        unpretty_to_mmif = Mmif(unpretty_res.get_data(as_text=True))
        self.assertIsNotNone(pretty_to_mmif)
        self.assertIsNotNone(unpretty_to_mmif)
        # TODO (krim @ 12/17/20): __eq__() is not working as expected, possibly realted to https://github.com/clamsproject/mmif/issues/131
        # self.assertEqual(pretty_to_mmif, unpretty_to_mmif)

        # this should raise TypeError because the ExampleClamsApp._annotate() doesn't take kwargs at all
        query_string = {'pretty': True, 'random': 'random'}
        res = self.app.put('/', data=mmif, headers=headers, query_string=query_string)
        self.assertEqual(res.status_code, 415, res.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
