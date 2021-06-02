import json
import os
import tempfile
import unittest
from typing import Union

import jsonschema
from mmif import Mmif, Document, DocumentTypes, AnnotationTypes, View

import clams.app
import clams.restify
from clams.appmetadata import AppMetadata



class ExampleInputMMIF(object):
    EXAMPLE_TEXT = 'this is a temp file.'

    @staticmethod
    def get_rawmmif() -> Mmif:
        mmif = Mmif(validate=False, frozen=False)

        vdoc = Document({'@type': DocumentTypes.VideoDocument,
                         'properties':
                             {'id': 'v1', 'location': "/dummy/dir/dummy.file.mp4"}})
        mmif.add_document(vdoc)

        idoc: Document = Document({'@type': DocumentTypes.ImageDocument})
        idoc.id = 'i1'
        idoc.location = os.path.join(os.path.dirname(__file__), 'pillow-logo.png')
        mmif.add_document(idoc)

        t = tempfile.NamedTemporaryFile(delete=False)
        with open(t.name, 'w') as t_f:
            t_f.write(ExampleInputMMIF.EXAMPLE_TEXT)
        tdoc: Document = Document({'@type': DocumentTypes.TextDocument})
        tdoc.location = t.name
        tdoc.id = 't1'
        mmif.add_document(tdoc)

        return mmif

    @staticmethod
    def get_mmif() -> str:
        return ExampleInputMMIF.get_rawmmif().serialize()


class TestSerialization(unittest.TestCase):

    def setUp(self):
        self.mmif = Mmif(ExampleInputMMIF.get_mmif())

    def test_view_is_empty(self):
        self.assertEqual(len(self.mmif.views), 0)


class ExampleClamsApp(clams.app.ClamsApp):

    def _appmetadata(self) -> Union[dict, AppMetadata]:
        
        exampleappversion = '0.0.1'
        metadata = AppMetadata(
            name="Example CLAMS App for testing",
            description="This app doesn't do anything",
            app_version=exampleappversion,
            license="MIT",
            identifier=f"https://apps.clams.ai/example/{exampleappversion}",
            output=[{'@type': AnnotationTypes.TimeFrame}],
        )
        metadata.add_input(DocumentTypes.AudioDocument)
        return metadata
    
    def _annotate(self, mmif, raise_error=False):
        if type(mmif) is not Mmif:
            mmif = Mmif(mmif, validate=False)
        new_view = mmif.new_view()
        self.sign_view(new_view, {'raise_error': raise_error})
        new_view.new_contain(AnnotationTypes.TimeFrame, {"producer": "dummy-producer"})
        ann = new_view.new_annotation('a1', AnnotationTypes.TimeFrame)
        ann.add_property("f1", "hello_world")
        if raise_error:
            raise ValueError
        return mmif


class TestClamsApp(unittest.TestCase):
    
    def setUp(self):
        self.appmetadataschema = json.loads(AppMetadata.schema_json())
        self.app = ExampleClamsApp()
        self.in_mmif = ExampleInputMMIF.get_mmif()

    def test_jsonschema_export(self):
        # TODO (krim @ 4/20/21): there may be a better test for this...
        self.assertIsNotNone(self.appmetadataschema)

    def test_appmetadata(self):
        # base metadata setting is done in the ExampleClamsApp class
        # here we will try to add more fields to the metadata and test them
        
        # test base metadata
        metadata = json.loads(self.app.appmetadata())
        self.assertEqual(len(metadata['output']), 1)
        self.assertEqual(len(metadata['input']), 1)
        self.assertTrue('properties' not in metadata['output'][0])
        self.assertTrue('properties' not in metadata['input'][0])
        self.assertTrue(metadata['input'][0]['required'])
        self.assertEqual(len(metadata['parameters']), 0)
        
        # test add_X methods
        self.app.metadata.add_output(AnnotationTypes.BoundingBox)
        metadata = json.loads(self.app.appmetadata())
        self.assertEqual(len(metadata['output']), 2)
        # this should not be added as a duplicate
        self.app.metadata.add_input(at_type=DocumentTypes.AudioDocument)
        metadata = json.loads(self.app.appmetadata())
        self.assertEqual(len(metadata['input']), 1)
        self.assertTrue('properties' not in metadata['input'][0])
        # adding input with properties
        self.app.metadata.add_input(at_type=AnnotationTypes.TimeFrame, frameType='speech')
        metadata = json.loads(self.app.appmetadata())
        self.assertEqual(len(metadata['input']), 2)
        self.assertTrue('properties' in metadata['input'][1])
        self.assertEqual(len(metadata['input'][1]['properties']), 1)
        # now parameters
        # using a custom class
        self.app.metadata.add_parameter(
            name='raise_error', description='force raise a ValueError', 
            type='boolean', default='false')
        # using python dict
        self.app.metadata.add_parameter(
            name='multiple_choice', description='meaningless multiple choice option',
            type='integer', choices=[1, 2, 3, 4, 5], default=3)
        metadata = json.loads(self.app.appmetadata())
        self.assertEqual(len(metadata['parameters']), 2)
        
        # finally for an eye exam
        print(self.app.appmetadata(pretty=True))
        
    def test_annotate(self):
        out_mmif = self.app.annotate(self.in_mmif)
        # TODO (krim @ 9/3/19): more robust test cases
        self.assertIsNotNone(out_mmif)
        out_mmif = Mmif(out_mmif)
        self.assertEqual(len(out_mmif.views), 1)
        out_mmif = Mmif(self.app.annotate(out_mmif))
        self.assertEqual(len(out_mmif.views), 2)
        views = list(out_mmif.views)
        # insertion order is kept
        self.assertTrue(views[0].metadata.timestamp < views[1].metadata.timestamp)

    def test_open_document_location(self):
        mmif = ExampleInputMMIF.get_rawmmif()
        with self.app.open_document_location(mmif.documents['t1']) as f:
            self.assertEqual(f.read(), ExampleInputMMIF.EXAMPLE_TEXT)

    def test_open_document_location_custom_opener(self):
        from PIL import Image
        mmif = ExampleInputMMIF.get_rawmmif()
        with self.app.open_document_location(mmif.documents['i1'], Image.open) as f:
            self.assertEqual(f.size, (200, 71))
            
    def test_error_handling(self):
        params = {'raise_error': True}
        in_mmif = Mmif(self.in_mmif)
        try: 
            out_mmif = self.app.annotate(in_mmif, **params)
        except Exception as e:
            out_mmif_from_str = self.app.set_error_view(self.in_mmif, params)
            out_mmif_from_mmif = self.app.set_error_view(in_mmif, params)
            self.assertEqual(out_mmif_from_mmif, out_mmif_from_str)
            out_mmif = out_mmif_from_str
        self.assertIsNotNone(out_mmif)
        last_view: View = next(reversed(out_mmif.views))
        self.assertEqual(len(last_view.metadata.contains), 0)
        self.assertEqual(len(last_view.metadata.error), 2)


class TestRestifier(unittest.TestCase):

    def setUp(self):
        self.app = clams.Restifier(ExampleClamsApp()).test_client()

    def test_can_get(self):
        gotten = self.app.get('/')
        print(gotten.get_data(as_text=True))
        self.assertIsNotNone(gotten)
        gotten = self.app.get('/', query_string={'pretty': 'true'})
        print(gotten.get_data(as_text=True))
        self.assertIsNotNone(gotten)

    def test_can_post(self):
        posted = self.app.post('/', data=ExampleInputMMIF.get_mmif())
        print(posted.get_data(as_text=True))
        self.assertIsNotNone(posted)

    def test_can_put(self):
        put = self.app.put('/', data=ExampleInputMMIF.get_mmif())
        print(put.get_data(as_text=True))
        self.assertIsNotNone(put)

    def test_can_put_as_json(self):
        put = self.app.put('/', data=ExampleInputMMIF.get_mmif(), headers={"Content-Type": "Application/json"})
        self.assertIsNotNone(put)
        self.assertEqual(put.status_code, 200)
        self.assertIsNotNone(Mmif(put.get_data(as_text=True)))

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
        self.assertEqual(res.status_code, 500, res.get_data(as_text=True))

    def test_can_output_error(self):
        mmif = ExampleInputMMIF.get_mmif()
        query_string = {'pretty': True, 'raise_error': True}
        res = self.app.put('/', data=mmif, query_string=query_string)
        self.assertEqual(res.status_code, 500)
        res_mmif = Mmif(res.get_data())
        self.assertEqual(len(res_mmif.views), 1)
        self.assertEqual(len(list(res_mmif.views)[0].annotations), 0)
        self.assertEqual(len(list(res_mmif.views)[0].metadata.contains), 0)
        res_mmif_json = json.loads(res.get_data())
        self.assertEqual(len(res_mmif_json['views']), 1)
        self.assertEqual(len(res_mmif_json['views'][0]['annotations']), 0)
        self.assertFalse('contains' in res_mmif_json['views'][0]['metadata'])
        self.assertTrue('error' in res_mmif_json['views'][0]['metadata'])

if __name__ == '__main__':
    unittest.main()
