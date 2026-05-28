"""
Tests for :class:`clams.app.ClamsPromptableApp`.

Covers the behavior documented in
``documentation/app-baseclasses.rst``: parameter discovery via
``inject_promptable_parameters()``, the reservation rule on
promptable-param names, ``build_conversation()`` shape across the
single-turn / turn-taking / user-only modes, and the
``response_to_grounded_textdocument()`` output contract.
"""
import unittest

from mmif import AnnotationTypes, DocumentTypes, Mmif

from clams import AppMetadata, ClamsPromptableApp


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

def make_metadata(call_helper=True, pre_declare=None):
    """
    Build a fresh AppMetadata for tests.

    :param call_helper: if True, calls
        ``ClamsPromptableApp.inject_promptable_parameters(metadata)``
        at the end (simulating a correctly-written ``appmetadata()``).
    :param pre_declare: if set to a parameter spec dict, calls
        ``metadata.add_parameter(**pre_declare)`` BEFORE the helper
        runs — used to test reservation enforcement.
    """
    m = AppMetadata(
        name="Example Promptable App",
        description="Test fixture, creating input TD - output TD alignment",
        app_license="MIT",
        identifier="https://apps.clams.ai/example-promptable/v1",
        url="https://fakegithub.com/some/repository",
    )
    m.add_input(DocumentTypes.TextDocument)
    m.add_output(DocumentTypes.TextDocument)
    m.add_output(AnnotationTypes.Alignment)
    if pre_declare is not None:
        m.add_parameter(**pre_declare)
    if call_helper:
        ClamsPromptableApp.inject_promptable_parameters(m)
    return m


def make_test_app(metadata):
    """
    Factory creating a fresh ClamsPromptableApp subclass that loads the
    given metadata. Each call produces a fresh class so per-test state
    doesn't leak.
    """

    def _load_appmetadata(self):
        return metadata

    cls = type(
        'TestPromptableApp',
        (ClamsPromptableApp,),
        {
            '_load_appmetadata': _load_appmetadata,
            '_appmetadata': lambda self: None,
            '_annotate': lambda self, mmif, **kw: mmif,
            'generate': lambda self, prompt, **kw: [""],
        },
    )
    return cls()


# ---------------------------------------------------------------------------
# Parameter discovery (via the helper)
# ---------------------------------------------------------------------------

class TestParameterDiscovery(unittest.TestCase):

    def test_all_promptable_params_present_after_init(self):
        app = make_test_app(make_metadata(call_helper=True))
        present = {p.name for p in app.metadata.parameters}
        expected_promptable = {p['name']
                               for p in ClamsPromptableApp.promptable_parameters}
        self.assertTrue(expected_promptable.issubset(present))

    def test_prompt_has_no_sdk_default(self):
        app = make_test_app(make_metadata(call_helper=True))
        prompt_param = next(p for p in app.metadata.parameters
                            if p.name == 'prompt')
        self.assertIsNone(prompt_param.default)
        self.assertTrue(prompt_param.multivalued)

    def test_system_prompt_default_empty_string(self):
        app = make_test_app(make_metadata(call_helper=True))
        sysprompt = next(p for p in app.metadata.parameters
                         if p.name == 'systemPrompt')
        self.assertEqual(sysprompt.default, '')

    def test_temperature_default_is_zero(self):
        """When the caller omits ``temperature``, it should arrive in
        ``_annotate()`` as the float ``0.0`` (deterministic decoding)."""
        app = make_test_app(make_metadata(call_helper=True))
        refined = app._refine_params(prompt=['hi'])
        self.assertEqual(refined['temperature'], 0.0)
        self.assertIsInstance(refined['temperature'], float)

    def test_prompt_mode_choices(self):
        app = make_test_app(make_metadata(call_helper=True))
        pm = next(p for p in app.metadata.parameters
                  if p.name == 'promptMode')
        self.assertEqual(set(pm.choices), {'user-only', 'turn-taking'})
        self.assertEqual(pm.default, 'turn-taking')


# ---------------------------------------------------------------------------
# Required-prompt validation
# ---------------------------------------------------------------------------

class TestRequiredPrompt(unittest.TestCase):

    def test_refine_params_raises_when_prompt_missing(self):
        """
        ``prompt`` has no SDK default. ``_refine_params`` must raise
        ``ValueError`` when the caller omits it.
        """
        app = make_test_app(make_metadata(call_helper=True))
        with self.assertRaises(ValueError) as ctx:
            app._refine_params()
        self.assertIn('prompt', str(ctx.exception))


# ---------------------------------------------------------------------------
# Missing-helper validation in __init__
# ---------------------------------------------------------------------------

class TestMissingHelperValidation(unittest.TestCase):

    def test_init_raises_when_helper_not_called(self):
        """
        If ``appmetadata()`` forgets to call
        ``inject_promptable_parameters()``, ``__init__`` must raise
        ``ValueError`` with an instructive message.
        """
        with self.assertRaises(ValueError) as ctx:
            make_test_app(make_metadata(call_helper=False))
        msg = str(ctx.exception)
        self.assertIn('inject_promptable_parameters', msg)


# ---------------------------------------------------------------------------
# Reservation enforcement (via duplicate-name ValueError)
# ---------------------------------------------------------------------------

class TestReservationEnforcement(unittest.TestCase):

    def test_redeclaring_prompt_trips_duplicate_name_error(self):
        """
        An app that calls ``metadata.add_parameter('prompt', ...)``
        before the helper trips the existing duplicate-name
        ``ValueError`` from ``AppMetadata.add_parameter`` (which the
        helper's own ``add_parameter`` call raises).
        """
        with self.assertRaises(ValueError) as ctx:
            make_metadata(
                call_helper=True,
                pre_declare={
                    'name': 'prompt',
                    'description': 'app-defined collision',
                    'type': 'string',
                    'multivalued': True,
                },
            )
        self.assertIn("'prompt'", str(ctx.exception))

    def test_redeclaring_max_new_tokens_trips_error(self):
        with self.assertRaises(ValueError) as ctx:
            make_metadata(
                call_helper=True,
                pre_declare={
                    'name': 'maxNewTokens',
                    'description': 'app-defined collision',
                    'type': 'integer',
                    'default': 1024,
                },
            )
        self.assertIn("'maxNewTokens'", str(ctx.exception))


# ---------------------------------------------------------------------------
# annotate_param_caster covers promptable params (no stale-spec drift)
# ---------------------------------------------------------------------------

class TestAnnotateParamCaster(unittest.TestCase):

    def test_caster_includes_promptable_param_specs(self):
        app = make_test_app(make_metadata(call_helper=True))
        for spec in ClamsPromptableApp.promptable_parameters:
            self.assertIn(spec['name'], app.annotate_param_spec)
            stored_type, stored_multivalued = \
                app.annotate_param_spec[spec['name']]
            self.assertEqual(stored_type, spec['type'])
            self.assertEqual(
                stored_multivalued, spec.get('multivalued', False))

    def test_multivalued_prompt_casts_to_list_of_strings(self):
        app = make_test_app(make_metadata(call_helper=True))
        refined = app._refine_params(prompt=['hello', 'world'])
        self.assertEqual(refined['prompt'], ['hello', 'world'])

    def test_max_new_tokens_casts_to_int(self):
        app = make_test_app(make_metadata(call_helper=True))
        refined = app._refine_params(prompt=['hi'], maxNewTokens=['1024'])
        self.assertEqual(refined['maxNewTokens'], 1024)
        self.assertIsInstance(refined['maxNewTokens'], int)

    def test_temperature_casts_to_float(self):
        app = make_test_app(make_metadata(call_helper=True))
        refined = app._refine_params(prompt=['hi'], temperature=['0.7'])
        self.assertEqual(refined['temperature'], 0.7)
        self.assertIsInstance(refined['temperature'], float)


# ---------------------------------------------------------------------------
# build_conversation
# ---------------------------------------------------------------------------

class TestBuildConversation(unittest.TestCase):
    """
    Covers the shape of ``ClamsPromptableApp.build_conversation()``
    across single-turn, turn-taking, and user-only modes, and the
    pre-built-message pass-through case.
    """

    def setUp(self):
        self.app = make_test_app(make_metadata(call_helper=True))

    def test_string_prompt_single_user_turn(self):
        conv = self.app.build_conversation(prompt="hello")
        self.assertEqual(len(conv), 1)
        self.assertEqual(conv[0]['role'], 'user')

    def test_single_element_list_single_user_turn(self):
        conv = self.app.build_conversation(prompt=['hello'])
        self.assertEqual(len(conv), 1)
        self.assertEqual(conv[0]['role'], 'user')

    def test_turn_taking_alternating_turns(self):
        conv = self.app.build_conversation(
            prompt=['q1', 'a1', 'q2'], prompt_mode='turn-taking')
        self.assertEqual(len(conv), 3)
        self.assertEqual(conv[0]['role'], 'user')
        self.assertEqual(conv[1]['role'], 'assistant')
        self.assertEqual(conv[2]['role'], 'user')

    def test_user_only_returns_progressively_extending_lists(self):
        convs = self.app.build_conversation(
            prompt=['q1', 'q2', 'q3'], prompt_mode='user-only')
        # N progressively-extending message lists, one per turn
        self.assertEqual(len(convs), 3)
        # last conversation has all 3 user turns (+ intermediate
        # assistant turns once the model has filled them in; at
        # build_conversation time the assistants are placeholders or
        # empty — the test pins length, not exact content)
        self.assertGreaterEqual(len(convs[-1]), 3)

    def test_pre_built_list_pass_through(self):
        msgs = [
            {'role': 'system', 'content': 'You are helpful.'},
            {'role': 'user', 'content': 'hi'},
        ]
        conv = self.app.build_conversation(prompt=msgs)
        self.assertEqual(conv, msgs)

    def test_system_prompt_prepended(self):
        conv = self.app.build_conversation(
            prompt='hello', system_prompt='You are helpful.')
        # first turn is a system message
        self.assertEqual(conv[0]['role'], 'system')

    def test_images_carried_in_user_content(self):
        sentinel = object()
        conv = self.app.build_conversation(
            prompt='describe this', images=[sentinel])
        # the sentinel image should appear somewhere in the first
        # user-turn content
        user_turn = next(m for m in conv if m['role'] == 'user')
        # content is typically a list of dicts; flatten to a sequence
        # of values and check for the sentinel
        flat = []

        def _walk(x):
            if isinstance(x, dict):
                for v in x.values():
                    _walk(v)
            elif isinstance(x, list):
                for v in x:
                    _walk(v)
            else:
                flat.append(x)

        _walk(user_turn['content'])
        self.assertIn(sentinel, flat)


# ---------------------------------------------------------------------------
# response_to_grounded_textdocument
# ---------------------------------------------------------------------------

class TestStoreResponse(unittest.TestCase):

    def setUp(self):
        self.app = make_test_app(make_metadata(call_helper=True))
        self.mmif = Mmif(validate=False)
        self.view = self.mmif.new_view()
        self.app.sign_view(self.view, {})
        self.view.new_contain(DocumentTypes.TextDocument)
        self.view.new_contain(AnnotationTypes.Alignment)

    def test_happy_path_creates_textdocument_and_alignment(self):
        td, align = self.app.response_to_grounded_textdocument(
            self.view, source='src1', response='generated text')
        self.assertEqual(td.text_value, 'generated text')
        self.assertEqual(align.get_property('source'), 'src1')
        self.assertEqual(align.get_property('target'), td.id)

    def test_reasoning_trace_none_does_not_raise(self):
        # no exception
        self.app.response_to_grounded_textdocument(
            self.view, source='src1', response='text',
            reasoning_trace=None)

    def test_reasoning_trace_not_none_raises_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.app.response_to_grounded_textdocument(
                self.view, source='src1', response='text',
                reasoning_trace='intermediate reasoning')

    # TODO (krim @ 05/28/26): this test case belongs upstream in the
    # vocabulary type definition (the `origins`/`origination` pairing
    # is a property of the `Document` type, per clams-vocabulary#18,
    # not a behavior of the SDK app layer). Move once clams-vocabulary
    # supports conditional prop validation. For now, this is a sanity
    # check that the SDK correctly forwards both kwargs through to the
    # underlying TD.
    def test_origins_and_origination_written_together(self):
        td, align = self.app.response_to_grounded_textdocument(
            self.view, source='tf1', response='caption text',
            origins=['tp1'], origination='derived')
        self.assertEqual(td.get_property('origins'), ['tp1'])
        self.assertEqual(td.get_property('origination'), 'derived')
        self.assertEqual(align.get_property('source'), 'tf1')
        self.assertEqual(align.get_property('target'), td.id)

    def test_unpaired_origins_or_origination_raises(self):
        unpaired = [
            {'origins': ['tp1']},
            {'origination': 'derived'},
        ]
        for kwargs in unpaired:
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                self.app.response_to_grounded_textdocument(
                    self.view, source='src1', response='text', **kwargs)


# ---------------------------------------------------------------------------
# Transport-neutral parameter casting
# ---------------------------------------------------------------------------

class TestTransportNeutralCasting(unittest.TestCase):
    """
    Just exercises the standard ``ClamsApp`` parameter-casting path.
    Not envelope-specific; the point is that promptable apps see no
    separate transport layer.
    """

    def test_multi_element_prompt_arrives_as_list_of_strings(self):
        app = make_test_app(make_metadata(call_helper=True))
        refined = app._refine_params(prompt=['a', 'b', 'c'])
        self.assertEqual(refined['prompt'], ['a', 'b', 'c'])
        for x in refined['prompt']:
            self.assertIsInstance(x, str)

    def test_single_element_prompt_still_list(self):
        app = make_test_app(make_metadata(call_helper=True))
        refined = app._refine_params(prompt=['only'])
        self.assertEqual(refined['prompt'], ['only'])


# ---------------------------------------------------------------------------
# ClamsHFPromptableApp class-attribute validation
# ---------------------------------------------------------------------------

class TestHFPromptableAppClassAttrs(unittest.TestCase):
    """
    Exercises the class-attribute validation in
    :class:`ClamsHFPromptableApp.__init__`. The actual model loading
    is patched out so these tests don't require torch/transformers.
    End-to-end inference tests live separately.
    """

    def _make_subclass(self, *, model_id=None, model_cls=None, **extra_attrs):
        attrs = {
            '_load_appmetadata': lambda self: make_metadata(call_helper=True),
            '_appmetadata': lambda self: None,
            '_annotate': lambda self, mmif, **kw: mmif,
            'MODEL_ID': model_id,
            'MODEL_CLS': model_cls,
        }
        attrs.update(extra_attrs)
        from clams.app import ClamsHFPromptableApp
        return type('TestHFApp', (ClamsHFPromptableApp,), attrs)

    def test_missing_model_id_raises(self):
        cls = self._make_subclass(model_id=None, model_cls=object)
        with self.assertRaises(ValueError) as ctx:
            cls()
        self.assertIn('MODEL_ID', str(ctx.exception))

    def test_missing_model_cls_raises(self):
        cls = self._make_subclass(model_id='fake-id', model_cls=None)
        with self.assertRaises(ValueError) as ctx:
            cls()
        self.assertIn('MODEL_CLS', str(ctx.exception))

    def test_loads_via_load_hf_model_with_class_attrs(self):
        """
        Patches ``clams.backends.hf.load_hf_model`` and verifies the
        base ``__init__`` forwards the declared class attributes to it.
        """
        import clams.backends.hf as hf_module
        original = hf_module.load_hf_model
        captured = {}

        def fake_load(model_id, model_cls, **kwargs):
            captured['model_id'] = model_id
            captured['model_cls'] = model_cls
            captured.update(kwargs)
            return ('FAKE_PROCESSOR', 'FAKE_MODEL', 'cpu')

        try:
            hf_module.load_hf_model = fake_load
            cls = self._make_subclass(
                model_id='org/fake-model',
                model_cls=object,
                DTYPE='FAKE_DTYPE',
                PADDING_SIDE='left',
                MODEL_KWARGS={'trust_remote_code': True},
            )
            app = cls()
            self.assertEqual(app.processor, 'FAKE_PROCESSOR')
            self.assertEqual(app.model, 'FAKE_MODEL')
            self.assertEqual(app.device, 'cpu')
            self.assertEqual(captured['model_id'], 'org/fake-model')
            self.assertIs(captured['model_cls'], object)
            self.assertEqual(captured['dtype'], 'FAKE_DTYPE')
            self.assertEqual(captured['padding_side'], 'left')
            self.assertEqual(
                captured['model_kwargs'], {'trust_remote_code': True})
        finally:
            hf_module.load_hf_model = original


if __name__ == '__main__':
    unittest.main()
