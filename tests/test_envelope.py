import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Union

from mmif import AnnotationTypes, Mmif

import clams
import clams.app
from clams.appmetadata import AppMetadata
from clams.envelop import (
    EnvelopeError, create_envelope, is_envelope,
    main as envelope_cli_main, normalize_params, prep_argparser,
    unwrap_envelope, unwrap_if_envelope,
)
from tests.test_clamsapp import ExampleInputMMIF


class EnvelopeTestApp(clams.app.ClamsApp):
    """
    Minimal test app that exercises the parameter pipeline without
    relying on mmif APIs that have shifted between versions.
    """
    app_version = 'envelope-test'

    def _appmetadata(self) -> Union[dict, AppMetadata]:
        # the metadata.py fallback in tests/ is used by other tests;
        # we don't need extra params here, sign_view records anything
        # in _RAW_PARAMS_KEY anyway.
        pass

    def _annotate(self, mmif, **kwargs):
        if type(mmif) is not Mmif:
            mmif = Mmif(mmif, validate=False)
        new_view = mmif.new_view()
        self.sign_view(new_view, kwargs)
        new_view.new_contain(AnnotationTypes.TimeFrame,
                             producer='envelope-test')
        if kwargs.get('raise_error'):
            raise ValueError('boom')
        return mmif


class TestNormalizeParams(unittest.TestCase):

    def test_string_scalar(self):
        result = normalize_params({'prompt': 'hello'})
        self.assertEqual(result, {'prompt': ['hello']})

    def test_int_scalar(self):
        result = normalize_params({'count': 5})
        self.assertEqual(result, {'count': ['5']})

    def test_float_scalar(self):
        result = normalize_params({'temperature': 0.7})
        self.assertEqual(result, {'temperature': ['0.7']})

    def test_bool_true(self):
        result = normalize_params({'pretty': True})
        self.assertEqual(result, {'pretty': ['True']})

    def test_bool_false(self):
        result = normalize_params({'pretty': False})
        self.assertEqual(result, {'pretty': ['False']})

    def test_array_of_strings(self):
        result = normalize_params({'labels': ['slate', 'chyron']})
        self.assertEqual(result, {'labels': ['slate', 'chyron']})

    def test_array_of_numbers(self):
        result = normalize_params({'ids': [1, 2, 3]})
        self.assertEqual(result, {'ids': ['1', '2', '3']})

    def test_object(self):
        result = normalize_params(
            {'labelMap': {'B': 'bars', 'S': 'slate'}}
        )
        self.assertEqual(
            result,
            {'labelMap': ['B:bars', 'S:slate']},
        )

    def test_mixed(self):
        result = normalize_params({
            'prompt': 'describe this',
            'temperature': 0.7,
            'pretty': True,
            'labels': ['a', 'b'],
            'labelMap': {'X': 'y'},
        })
        self.assertEqual(result['prompt'], ['describe this'])
        self.assertEqual(result['temperature'], ['0.7'])
        self.assertEqual(result['pretty'], ['True'])
        self.assertEqual(result['labels'], ['a', 'b'])
        self.assertEqual(result['labelMap'], ['X:y'])

    def test_empty(self):
        self.assertEqual(normalize_params({}), {})


class TestEnvelopeDetection(unittest.TestCase):

    def test_is_envelope_true(self):
        self.assertTrue(is_envelope({'parameters': {}, 'mmif': {}}))

    def test_is_envelope_false(self):
        self.assertFalse(is_envelope({'metadata': {}, 'views': []}))

    def test_is_envelope_non_dict(self):
        self.assertFalse(is_envelope('not a dict'))
        self.assertFalse(is_envelope(None))
        self.assertFalse(is_envelope([]))

    def test_unwrap_missing_mmif(self):
        with self.assertRaises(EnvelopeError) as ctx:
            unwrap_envelope({'parameters': {}})
        self.assertIn('mmif', str(ctx.exception).lower())

    def test_unwrap_non_dict_parameters(self):
        with self.assertRaises(EnvelopeError) as ctx:
            unwrap_envelope({'parameters': 'bad', 'mmif': {}})
        self.assertIn('object', str(ctx.exception).lower())


class TestEnvelopeCreation(unittest.TestCase):

    def setUp(self):
        self.mmif_str = ExampleInputMMIF.get_mmif()
        self.mmif_obj = Mmif(self.mmif_str)

    def test_from_string(self):
        result = json.loads(
            create_envelope(self.mmif_str, {'pretty': True})
        )
        self.assertIn('parameters', result)
        self.assertIn('mmif', result)
        self.assertEqual(result['parameters']['pretty'], True)

    def test_from_mmif_object(self):
        result = json.loads(
            create_envelope(self.mmif_obj, {'pretty': True})
        )
        self.assertIn('parameters', result)
        self.assertIn('mmif', result)

    def test_from_dict(self):
        mmif_dict = json.loads(self.mmif_str)
        result = json.loads(
            create_envelope(mmif_dict, {'pretty': True})
        )
        self.assertEqual(result['mmif'], mmif_dict)
        self.assertEqual(result['parameters']['pretty'], True)

    def test_no_params(self):
        result = json.loads(create_envelope(self.mmif_str))
        self.assertEqual(result['parameters'], {})
        self.assertIn('mmif', result)

    def test_roundtrip(self):
        params = {'prompt': 'describe', 'labels': ['a', 'b']}
        envelope_str = create_envelope(self.mmif_str, params)
        body = json.loads(envelope_str)
        self.assertTrue(is_envelope(body))
        mmif_str, normalized = unwrap_envelope(body)
        # MMIF should be valid
        Mmif(mmif_str)
        self.assertEqual(normalized['prompt'], ['describe'])
        self.assertEqual(normalized['labels'], ['a', 'b'])


class TestUnwrapIfEnvelope(unittest.TestCase):
    """
    Direct tests for the shared helper used by every entry point.
    """

    def setUp(self):
        self.mmif_str = ExampleInputMMIF.get_mmif()

    def test_str_envelope(self):
        env = create_envelope(self.mmif_str, {'prompt': 'x'})
        data, params = unwrap_if_envelope(env, {})
        Mmif(data)  # inner MMIF extracted and valid
        self.assertEqual(params, {'prompt': ['x']})

    def test_bytes_envelope(self):
        env = create_envelope(
            self.mmif_str, {'prompt': 'x'}).encode('utf-8')
        data, params = unwrap_if_envelope(env, {})
        Mmif(data)
        self.assertEqual(params, {'prompt': ['x']})

    def test_dict_envelope(self):
        env = json.loads(create_envelope(self.mmif_str, {'prompt': 'x'}))
        data, params = unwrap_if_envelope(env, {})
        Mmif(data)
        self.assertEqual(params, {'prompt': ['x']})

    def test_explicit_params_win(self):
        env = create_envelope(self.mmif_str, {'prompt': 'env'})
        data, params = unwrap_if_envelope(env, {'prompt': ['cli']})
        self.assertEqual(params['prompt'], ['cli'])

    def test_non_envelope_str_passthrough(self):
        data, params = unwrap_if_envelope(self.mmif_str, {'a': ['1']})
        self.assertEqual(data, self.mmif_str)
        self.assertEqual(params, {'a': ['1']})

    def test_valid_json_non_dict_passthrough(self):
        data, params = unwrap_if_envelope('123', {})
        self.assertEqual(data, '123')
        self.assertEqual(params, {})


class TestRestifierEnvelope(unittest.TestCase):

    def setUp(self):
        self.client = clams.Restifier(EnvelopeTestApp()).test_client()
        self.mmif_str = ExampleInputMMIF.get_mmif()

    def test_post_envelope(self):
        envelope_str = create_envelope(
            self.mmif_str, {'pretty': True}
        )
        res = self.client.post('/', data=envelope_str)
        self.assertEqual(res.status_code, 200)
        Mmif(res.get_data(as_text=True))

    def test_put_envelope(self):
        envelope_str = create_envelope(
            self.mmif_str, {'pretty': True}
        )
        res = self.client.put('/', data=envelope_str)
        self.assertEqual(res.status_code, 200)
        Mmif(res.get_data(as_text=True))

    PREFIX = "Invalid input data. See below for validation error."

    def test_envelope_missing_mmif(self):
        bad = json.dumps({'parameters': {'pretty': True}})
        res = self.client.post('/', data=bad)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.mimetype, 'text/plain')
        body = res.get_data(as_text=True)
        # EnvelopeError 500 uses the same payload format as the
        # MMIF-validation 500
        self.assertTrue(body.startswith(self.PREFIX))
        self.assertIn('mmif', body)

    def test_envelope_invalid_mmif(self):
        bad = json.dumps({
            'parameters': {},
            'mmif': {'not': 'valid mmif'},
        })
        res = self.client.post('/', data=bad)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.mimetype, 'text/plain')
        body = res.get_data(as_text=True)
        # trimmed: concise jsonschema message, NOT the full schema dump
        self.assertTrue(body.startswith(self.PREFIX))
        self.assertNotIn('$schema', body)
        self.assertLess(len(body), 500)

    def test_raw_mmif_still_works(self):
        res = self.client.post('/', data=self.mmif_str)
        self.assertEqual(res.status_code, 200)
        Mmif(res.get_data(as_text=True))

    def test_invalid_json(self):
        res = self.client.post('/', data='this is not json')
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.mimetype, 'text/plain')

    def test_envelope_app_error_returns_error_view(self):
        # app raises during _annotate with envelope input: the error
        # must come back as an error-view MMIF (application/json),
        # NOT a text/plain input error, and set_error_view must have
        # unwrapped the envelope to record the params.
        envelope_str = create_envelope(
            self.mmif_str, {'prompt': 'p', 'raise_error': True}
        )
        res = self.client.post('/', data=envelope_str)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.mimetype, 'application/json')
        out = Mmif(res.get_data(as_text=True))
        err_meta = json.loads(list(out.views)[-1].metadata.serialize())
        self.assertIn('error', err_meta)
        self.assertEqual(
            err_meta.get('parameters', {}).get('prompt'), 'p')


class TestEnvelopeReproducibility(unittest.TestCase):
    """
    End-to-end tests verifying the issue's key claim: envelope parameters
    are recorded in view metadata via ``sign_view``, providing
    transparent and reproducible app configuration.
    """

    def setUp(self):
        self.client = clams.Restifier(EnvelopeTestApp()).test_client()
        self.mmif_str = ExampleInputMMIF.get_mmif()

    def _get_view_params(self, response_text):
        out = Mmif(response_text)
        # signing view is the last view added by EnvelopeTestApp
        signed = list(out.views)[-1]
        return json.loads(signed.metadata.serialize()).get(
            'parameters', {})

    def test_envelope_param_recorded_in_view_metadata(self):
        envelope_str = create_envelope(
            self.mmif_str,
            {'prompt': 'describe this scene'},
        )
        res = self.client.post('/', data=envelope_str)
        self.assertEqual(res.status_code, 200)
        params = self._get_view_params(res.get_data(as_text=True))
        self.assertEqual(params.get('prompt'), 'describe this scene')

    def test_long_prompt_roundtrip(self):
        # The original motivation: prompts of any length should pass
        # through transparently.  URL length limits don't apply since
        # the envelope rides in the POST body.
        long_prompt = 'word ' * 500
        envelope_str = create_envelope(
            self.mmif_str, {'prompt': long_prompt},
        )
        res = self.client.post('/', data=envelope_str)
        self.assertEqual(res.status_code, 200)
        params = self._get_view_params(res.get_data(as_text=True))
        self.assertEqual(params.get('prompt'), long_prompt)

    def test_query_string_overrides_in_view_metadata(self):
        envelope_str = create_envelope(
            self.mmif_str, {'prompt': 'envelope value'},
        )
        res = self.client.post(
            '/', data=envelope_str,
            query_string={'prompt': 'query value'},
        )
        self.assertEqual(res.status_code, 200)
        params = self._get_view_params(res.get_data(as_text=True))
        self.assertEqual(params.get('prompt'), 'query value')


class TestEnvelopeCLI(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.params_path = tmp / 'params.json'
        self.mmif_path = tmp / 'input.mmif'
        self.params_path.write_text(json.dumps(
            {'prompt': 'hello', 'temperature': 0.5}
        ))
        self.mmif_path.write_text(ExampleInputMMIF.get_mmif())

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run_cli(self, argv):
        parser = prep_argparser()
        args = parser.parse_args(argv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            envelope_cli_main(args)
        return buf.getvalue()

    def test_cli_with_files(self):
        output = self._run_cli([
            str(self.params_path), str(self.mmif_path)
        ])
        body = json.loads(output)
        self.assertTrue(is_envelope(body))
        self.assertEqual(body['parameters']['prompt'], 'hello')
        self.assertEqual(body['parameters']['temperature'], 0.5)
        # extracted MMIF should still be valid
        mmif_str, _ = unwrap_envelope(body)
        Mmif(mmif_str)

    def test_cli_envelope_can_be_consumed_by_restifier(self):
        # The envelope produced by the CLI should be directly POSTable.
        output = self._run_cli([
            str(self.params_path), str(self.mmif_path)
        ])
        client = clams.Restifier(EnvelopeTestApp()).test_client()
        res = client.post('/', data=output)
        self.assertEqual(res.status_code, 200)
        Mmif(res.get_data(as_text=True))


class TestEnvelopeNonHTTPEntrypoints(unittest.TestCase):
    """
    Envelope handling lives in ClamsApp.annotate(), so it must work
    when annotate() is called directly -- i.e. the path used by the
    cli.py entry point and any programmatic use -- not just over HTTP.
    """

    def setUp(self):
        self.app = EnvelopeTestApp()
        self.mmif_str = ExampleInputMMIF.get_mmif()

    def _signed_params(self, out_mmif_str):
        out = Mmif(out_mmif_str)
        signed = list(out.views)[-1]
        return json.loads(signed.metadata.serialize()).get(
            'parameters', {})

    def test_annotate_accepts_envelope_string(self):
        # exactly what cli.py does: clamsapp.annotate(in_data, **params)
        envelope_str = create_envelope(
            self.mmif_str, {'prompt': 'from cli'}
        )
        out = self.app.annotate(envelope_str)
        params = self._signed_params(out)
        self.assertEqual(params.get('prompt'), 'from cli')

    def test_annotate_raw_mmif_still_works(self):
        # raw MMIF (no envelope) passes through; app adds one view
        out = Mmif(self.app.annotate(self.mmif_str))
        self.assertEqual(len(list(out.views)), 1)

    def test_explicit_params_override_envelope(self):
        envelope_str = create_envelope(
            self.mmif_str, {'prompt': 'envelope value'}
        )
        # CLI flags / kwargs arrive as lists, like argparse produces
        out = self.app.annotate(envelope_str, prompt=['kwarg value'])
        params = self._signed_params(out)
        self.assertEqual(params.get('prompt'), 'kwarg value')

    def test_malformed_envelope_raises_envelope_error(self):
        bad = json.dumps({'parameters': {'p': 1}})  # missing "mmif"
        with self.assertRaises(EnvelopeError):
            self.app.annotate(bad)


class TestEnvelopePythonAPI(unittest.TestCase):

    def test_create_envelope_at_package_root(self):
        # `from clams import create_envelope` exposes the fn at root.
        self.assertTrue(callable(clams.create_envelope))
        result = json.loads(
            clams.create_envelope(
                ExampleInputMMIF.get_mmif(), {'pretty': True}
            )
        )
        self.assertTrue(is_envelope(result))
        self.assertEqual(result['parameters']['pretty'], True)


if __name__ == '__main__':
    unittest.main()
