import itertools
import json
import os
import sys
import tempfile
import unittest
import warnings
from typing import Union

import jsonschema
import pytest
from mmif import Mmif, Document, DocumentTypes, AnnotationTypes, View, __specver__

import clams.app
import clams.restify
from clams.appmetadata import AppMetadata, Input
from clams.restify import ParameterCaster


class ExampleInputMMIF(object):
    EXAMPLE_TEXT = 'this is a temp file.'

    @staticmethod
    def get_rawmmif() -> Mmif:
        mmif = Mmif(validate=False)

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
    app_version = 'no-manual-version',

    def _appmetadata(self) -> Union[dict, AppMetadata]:
        pass
    
    def _annotate(self, mmif, **kwargs):
        if type(mmif) is not Mmif:
            mmif = Mmif(mmif, validate=False)
        new_view = mmif.new_view()
        self.sign_view(new_view, kwargs)
        new_view.new_contain(AnnotationTypes.TimeFrame, **{"producer": "dummy-producer"})
        ann = new_view.new_annotation(AnnotationTypes.TimeFrame, 'a1', start=10, end=99)
        ann.add_property("f1", "hello_world")
        d1 = DocumentTypes.VideoDocument
        d2 = DocumentTypes.from_str(f'{str(d1)[:-1]}99')
        if mmif.get_documents_by_type(d2):
            new_view.new_annotation(AnnotationTypes.TimePoint, 'tp1')
        if 'raise_error' in kwargs and kwargs['raise_error']:
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
    
    def test_generate_app_version(self):
        os.environ.pop(clams.appmetadata.app_version_envvar_key, None)
        # should fail to generate version number if the directory of the app doesn't exist
        self.assertEqual(clams.appmetadata.generate_app_version(cwd='not-existing-app'), 
                         clams.appmetadata.unresolved_app_version_num)

        os.environ.update({clams.appmetadata.app_version_envvar_key:'v10'})
        # should use version value from envvar if the directory of the app doesn't exist
        self.assertEqual(clams.appmetadata.generate_app_version(cwd='not-existing-app'), 'v10')
        os.environ.pop(clams.appmetadata.app_version_envvar_key, None)
        # the version in development should be greater than the version in the last release
        # doesn't necessarily work on GHA VMs, so disabling
        # self.assertTrue(clams.__version__ >=
        #                 clams.appmetadata.generate_app_version(cwd=Path(__file__).parent/'..').split('-')[0])

    def test_appmetadata(self):
        # base metadata setting is done in the ExampleClamsApp class
        # here we will try to add more fields to the metadata and test them
        
        # test base metadata
        metadata = json.loads(self.app.appmetadata())
        self.assertNotEqual(self.app.app_version, metadata['app_version'])
        self.assertEqual(len(metadata['output']), 1)
        self.assertEqual(len(metadata['input']), 2)
        self.assertTrue('properties' not in metadata['output'][0])
        for i in metadata['input']:
            if isinstance(i, dict):
                elem = i
        self.assertTrue('properties' not in elem)
        self.assertTrue(elem['required'])
        
        # test add_X methods
        self.app.metadata.add_output(AnnotationTypes.BoundingBox, boxType='text')
        metadata = json.loads(self.app.appmetadata())
        self.assertEqual(len(metadata['output']), 2)
        # these should not be added as a duplicate
        with self.assertRaises(ValueError):
            self.app.metadata.add_input(at_type=DocumentTypes.TextDocument)
        with self.assertRaises(ValueError):
            self.app.metadata.add_output(AnnotationTypes.BoundingBox, boxType='text')
        # but this should 
        self.app.metadata.add_output(AnnotationTypes.BoundingBox, boxType='face')
        metadata = json.loads(self.app.appmetadata())
        self.assertEqual(len(metadata['input']), 2)
        self.assertTrue('properties' not in metadata['input'][0])
        # adding input with properties
        self.app.metadata.add_input(at_type=AnnotationTypes.TimeFrame, frameType='speech')
        metadata = json.loads(self.app.appmetadata())
        self.assertEqual(len(metadata['input']), 3)
        self.assertTrue('properties' in metadata['input'][-1])
        self.assertEqual(len(metadata['input'][-1]['properties']), 1)
        self.app.metadata.add_input_oneof(AnnotationTypes.Polygon)
        self.assertEqual(len(self.app.metadata.input), 4)
        self.assertFalse(isinstance(self.app.metadata.input[-1], list))
        # adding a list should not contain "optional" types
        i = Input(at_type=AnnotationTypes.BoundingBox, required=False)
        j = Input(at_type=AnnotationTypes.VideoObject)
        with self.assertRaises(ValueError):
            self.app.metadata.add_input_oneof(i, j)
        # now parameters
        # using a custom class
        # this should conflict with existing parameter
        with self.assertRaises(ValueError):
            self.app.metadata.add_parameter(
                name='raise_error', description='force raise a ValueError', 
                type='boolean', default='false')
        # using python dict
        self.app.metadata.add_parameter(
            name='multiple_choice', description='meaningless multiple choice option',
            type='integer', choices=[1, 2, 3, 4, 5], default=3, multivalued=True)
        metadata = json.loads(self.app.appmetadata())
        self.assertEqual(len(metadata['parameters']), 2 + len(self.app.universal_parameters))
        # now more additional metadata
        self.app.metadata.add_more('one', 'more')
        self.assertEqual(self.app.metadata.more['one'], 'more')
        with self.assertRaises(ValueError):
            self.app.metadata.add_more('one', 'thing')
        with self.assertRaises(ValueError):
            self.app.metadata.add_more('one', '')
        
        # finally for an eye exam
        print(self.app.appmetadata(pretty=True))

    @pytest.mark.skip('legacy type version check')
    def test__check_mmif_compatibility(self):
        maj, min, pat = list(map(int, __specver__.split('.')))
        self.assertTrue(self.app._check_mmif_compatibility('0.4.3', '0.4.8'))
        self.assertTrue(self.app._check_mmif_compatibility('0.4.3', '0.4.1'))
        self.assertTrue(self.app._check_mmif_compatibility('0.4.3.dev1', '0.4.3'))
        self.assertFalse(self.app._check_mmif_compatibility('0.4.3', '0.5.8'))
        self.assertFalse(self.app._check_mmif_compatibility('0.4.3', '1.5.8'))
        in_mmif = ExampleInputMMIF.get_rawmmif()
        compat_ver = f"{maj}.{min}.{pat+10}"
        incompat_ver = f"{maj}.{min+2}.{pat}"
        in_mmif.metadata.mmif = f"http://mmif.clams.ai/{compat_ver}"
        try:
            self.app.annotate(in_mmif)
        except ValueError:
            pytest.fail(f"current app ({__specver__}) should be able to process compatible input {compat_ver}.")
        in_mmif.metadata.mmif = f"http://mmif.clams.ai/{incompat_ver}"
        with pytest.raises(ValueError):
            self.app.annotate(in_mmif)
        
    def test_annotate(self):
        # The example app is hard-coded to **always** emit version mismatch warning
        out_mmif = self.app.annotate(self.in_mmif)
        # TODO (krim @ 9/3/19): more robust test cases
        self.assertIsNotNone(out_mmif)
        out_mmif = Mmif(out_mmif)
        self.assertEqual(len(out_mmif.views), 2)
        for v in out_mmif.views:
            if v.metadata.app == self.app.metadata.identifier:
                self.assertEqual(len(v.metadata.parameters), 0)  # no params were passed when `annotate()` was called
        out_mmif = self.app.annotate(self.in_mmif, pretty=False)
        out_mmif = Mmif(out_mmif)
        for v in out_mmif.views:
            if v.metadata.app == self.app.metadata.identifier:
                self.assertEqual(len(v.metadata.parameters), 1)  # 'pretty` parameter was passed 
        out_mmif = Mmif(self.app.annotate(out_mmif))
        self.assertEqual(len(out_mmif.views), 4)
        views = list(out_mmif.views)
        # insertion order is kept
        self.assertTrue(views[0].metadata.timestamp < views[1].metadata.timestamp)
    
    def test_annotate_returns_invalid_mmif(self):
        m = Mmif(self.in_mmif)
        v = m.new_view()
        v.new_contain(AnnotationTypes.TimeFrame)
        v.new_annotation(AnnotationTypes.TimeFrame, start=10, end=30)
        # still, this view is not "signed"
        from unittest.mock import MagicMock
        self.app._annotate = MagicMock(return_value=m)
        with self.assertRaises(jsonschema.ValidationError):
            self.app.annotate(self.in_mmif)
        
        

    def test_open_document_location(self):
        mmif = ExampleInputMMIF.get_rawmmif()
        with self.app.open_document_location(mmif.documents['t1']) as f:
            self.assertEqual(f.read(), ExampleInputMMIF.EXAMPLE_TEXT)

    def test_open_document_location_custom_opener(self):
        from PIL import Image
        mmif = ExampleInputMMIF.get_rawmmif()
        with self.app.open_document_location(mmif.documents['i1'], Image.open) as f:
            self.assertEqual(f.size, (200, 71))
            
    def test_get_configuration(self):
        self.app.metadata.parameters = []
        self.app.metadata.add_parameter('param1', 'first_param', 'string')
        self.app.metadata.add_parameter('param2', 'second_param', 'string', default='second_default')
        self.app.metadata.add_parameter('param3', 'third_param', 'boolean', default='f')
        self.app.metadata.add_parameter('param4', 'fourth_param', 'integer', default='1', choices="1 2 3".split())
        self.app.metadata.add_parameter('param5', 'fifth_param', 'number', default='0.5')
        conf = self.app.get_configuration(param1='okay', non_parameter='should be ignored')
        conf.pop(clams.ClamsApp._RAW_PARAMS_KEY, None)
        self.assertEqual(len(conf), 5)  # 1 from `param1`, 4 from default value
        self.assertFalse('non_parameter' in conf)
        self.assertEqual(type(conf['param1']), str)
        self.assertEqual(type(conf['param2']), str)
        self.assertEqual(type(conf['param3']), bool)
        self.assertEqual(type(conf['param4']), int)
        self.assertEqual(type(conf['param5']), float)
        with self.assertRaises(ValueError):
            # because param1 doesn't have a default value and thus a required param
            self.app.get_configuration(param2='okay')
        with self.assertRaisesRegexp(ValueError, r'.+must be one of.+'):
            # because param4 can't be 4, note that param1 is "required" 
            self.app.get_configuration(param1='p1', param4=4)
            
    def test_error_handling(self):
        params = {'raise_error': True, 'pretty': True}
        in_mmif = Mmif(self.in_mmif)
        try: 
            out_mmif = self.app.annotate(in_mmif, **params)
        except Exception as e:
            out_mmif_from_str = self.app.set_error_view(self.in_mmif, params)
            out_mmif_from_mmif = self.app.set_error_view(in_mmif, params)
            self.assertEqual(out_mmif_from_mmif.views, out_mmif_from_str.views)
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

    def test_can_output_warnings(self):
        mmif = ExampleInputMMIF.get_mmif()
        headers = {"Content-Type": "Application/json"}

        # the ExampleClamsApp._annotate() doesn't take 'randomN' parameters
        query_string = {'pretty': True,
                        'random1': 'value1',
                        'random2': 'value2',
                        'random3': 'value3',
                        }
        res = self.app.put('/', data=mmif, headers=headers, query_string=query_string)
        # BUT it should still return 200
        self.assertEqual(res.status_code, 200)
        # with three warnings (r1, r2, r3)
        req_mmif = Mmif(mmif)
        res_mmif = Mmif(res.get_data(as_text=True))
        self.assertEqual(len(req_mmif.views), len(res_mmif.views) - 2)
        ## warning should be placed in the end of all other views that the app generates 
        self.assertTrue('warnings' in list(res_mmif.views)[-1].metadata)
        self.assertTrue(list(res_mmif.views)[-1].metadata.warnings)

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

    def test_error_on_ill_mmif(self):
        mmif_str = '{"top string": "this is not a mmif"}'
        res = self.app.put('/', data=mmif_str)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.mimetype, 'text/plain')


class TestParameterCaster(unittest.TestCase):
    
    def setUp(self) -> None:
        self.param_spec = {'str_param': (str, False), 
                           'number_param': (float, False),
                           'int_param': (int, False),
                           'bool_param': (bool, False), 
                           'str_multi_param': (str, True)
                           }
        
    def test_cast(self):
        caster = ParameterCaster(self.param_spec)
        params = {
            'str_param': ["a_string"], 
            'number_param': ["1.11"], 
            'int_param': [str(sys.maxsize)], 
            'bool_param': ['true'],
            'str_multi_param': ['value1', 'value2']
        }
        self.assertTrue(all(map(lambda x: isinstance(x, str), itertools.chain.from_iterable(params.values()))))
        casted = caster.cast(params)
        # must push out to the list
        self.assertEqual(casted['str_param'], params['str_param'][0])
        self.assertEqual(casted['number_param'], 1.11)
        self.assertTrue(isinstance(casted['int_param'], int))
        self.assertTrue(casted['bool_param'])
        self.assertEqual(set(casted['str_multi_param']), set(params['str_multi_param']))
        unknown_param_key = 'unknown'
        unknown_param_val = 'dunno'
        params[unknown_param_key] = [unknown_param_val]
        # must not throw any error or warning upon receiving unknown parameters
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            caster.cast(params)
        

if __name__ == '__main__':
    unittest.main()
