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

from mmif import AnnotationTypes, Document, DocumentTypes, Mmif

from clams import AppMetadata, ClamsPromptableApp


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

def make_metadata(call_helper=True, pre_declare=None,
                  analyzer_versions=None, hf_helper=False):
    """
    Build a fresh AppMetadata for tests.

    :param call_helper: if True, calls
        ``ClamsPromptableApp.inject_promptable_parameters(metadata)``
        at the end (simulating a correctly-written ``appmetadata()``).
        Mutually exclusive with ``hf_helper``.
    :param pre_declare: if set to a parameter spec dict, calls
        ``metadata.add_parameter(**pre_declare)`` BEFORE the helper
        runs — used to test reservation enforcement.
    :param analyzer_versions: if set, passed through to
        ``AppMetadata(analyzer_versions=...)``. Required when the
        fixture is consumed by ``ClamsHFPromptableApp`` tests.
    :param hf_helper: if True, calls
        ``ClamsHFPromptableApp.inject_promptable_parameters(metadata)``
        (the HF override of the plain promptable helper). Use for HF
        fixture builds.
    """
    kwargs = dict(
        name="Example Promptable App",
        description="Test fixture, creating input TD - output TD alignment",
        app_license="MIT",
        identifier="https://apps.clams.ai/example-promptable/v1",
        url="https://fakegithub.com/some/repository",
    )
    if analyzer_versions is not None:
        kwargs['analyzer_versions'] = analyzer_versions
    m = AppMetadata(**kwargs)
    m.add_input(DocumentTypes.TextDocument)
    m.add_output(DocumentTypes.TextDocument)
    m.add_output(AnnotationTypes.Alignment)
    if pre_declare is not None:
        m.add_parameter(**pre_declare)
    if hf_helper:
        from clams.app import ClamsHFPromptableApp
        ClamsHFPromptableApp.inject_promptable_parameters(m)
    elif call_helper:
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
        # upstream: a media document and an annotation anchored to it, which
        # serves as the response's `source`.
        vdoc = Document()
        vdoc.at_type = DocumentTypes.VideoDocument
        vdoc.id = 'v1'
        vdoc.location = 'file:///video.mp4'
        self.mmif.add_document(vdoc)
        self.doc_id = vdoc.id
        src_view = self.mmif.new_view()
        src_view.metadata.app = 'http://upstream/1'
        self.src = src_view.new_annotation(
            AnnotationTypes.TimeFrame, document=vdoc.id, label='scene')
        # the current app's view
        self.view = self.mmif.new_view()
        self.app.sign_view(self.view, {})
        self.view.new_contain(DocumentTypes.TextDocument)
        self.view.new_contain(AnnotationTypes.Alignment)

    def test_happy_path_creates_textdocument_and_alignment(self):
        td, align = self.app.response_to_grounded_textdocument(
            self.view, source=self.src.id, response='generated text')
        self.assertEqual(td.text_value, 'generated text')
        # the TD inherits the source annotation's document
        self.assertEqual(td.get_property('document'), self.doc_id)
        self.assertEqual(align.get_property('source'), self.src.id)
        self.assertEqual(align.get_property('target'), td.id)

    def test_source_without_document_raises(self):
        # a source annotation carrying no `document` means a malformed input
        ungrounded = self.view.new_annotation(AnnotationTypes.TimeFrame)
        with self.assertRaises(ValueError):
            self.app.response_to_grounded_textdocument(
                self.view, source=ungrounded.id, response='text')

    def test_reasoning_trace_none_stores_no_property(self):
        td, _ = self.app.response_to_grounded_textdocument(
            self.view, source=self.src.id, response='text',
            reasoning_trace=None)
        self.assertNotIn('modelReasoningTrace', td.properties)

    def test_reasoning_trace_stored_on_textdocument(self):
        td, _ = self.app.response_to_grounded_textdocument(
            self.view, source=self.src.id, response='the answer',
            reasoning_trace='step 1 ... step 2 ...')
        # trace lives in the property; the TD text stays answer-only
        self.assertEqual(
            td.get_property('modelReasoningTrace'), 'step 1 ... step 2 ...')
        self.assertEqual(td.text_value, 'the answer')

    # TODO (krim @ 05/28/26): this test case belongs upstream in the
    # vocabulary type definition (the `origins`/`origination` pairing
    # is a property of the `Document` type, per clams-vocabulary#18,
    # not a behavior of the SDK app layer). Move once clams-vocabulary
    # supports conditional prop validation. For now, this is a sanity
    # check that the SDK correctly forwards both kwargs through to the
    # underlying TD.
    def test_origins_and_origination_written_together(self):
        td, align = self.app.response_to_grounded_textdocument(
            self.view, source=self.src.id, response='caption text',
            origins=['tp1'], origination='derived')
        self.assertEqual(td.get_property('origins'), ['tp1'])
        self.assertEqual(td.get_property('origination'), 'derived')
        self.assertEqual(align.get_property('source'), self.src.id)
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
# Reasoning-trace split helper
# ---------------------------------------------------------------------------

class TestSplitReasoningTrace(unittest.TestCase):
    """:meth:`ClamsPromptableApp.split_tagged_reasoning_trace` (static)."""

    split = staticmethod(ClamsPromptableApp.split_tagged_reasoning_trace)

    def test_closed_block_splits_answer_and_trace(self):
        answer, trace = self.split('<think>reasoning</think>The answer.')
        self.assertEqual(answer, 'The answer.')
        self.assertEqual(trace, 'reasoning')

    def test_no_tags_returns_text_as_answer_none_trace(self):
        answer, trace = self.split('just an answer')
        self.assertEqual(answer, 'just an answer')
        self.assertIsNone(trace)

    def test_unterminated_block_not_overstripped(self):
        # No closing tag (e.g. ran out of tokens mid-thought): return the
        # raw text rather than discard a possibly-real answer.
        raw = '<think>thinking with no close'
        answer, trace = self.split(raw)
        self.assertEqual(answer, raw)
        self.assertIsNone(trace)

    def test_uses_final_close_tag(self):
        answer, trace = self.split(
            '<think>a</think>mid<think>b</think>final')
        self.assertEqual(answer, 'final')

    def test_custom_tags(self):
        answer, trace = self.split(
            '[R]why[/R]done', open_tag='[R]', close_tag='[/R]')
        self.assertEqual(answer, 'done')
        self.assertEqual(trace, 'why')

    def test_non_thinking_output_safe_to_call(self):
        # Safe to call unconditionally even when thinking is disabled.
        answer, trace = self.split('   plain caption   ')
        self.assertEqual(answer, 'plain caption')
        self.assertIsNone(trace)


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

    SINGLETON_AV = {'org/fake-model': 'deadbee'}
    MULTI_AV = {
        'org/large-model': 'aaaaaaa',
        'org/small-model': 'bbbbbbb',
    }

    def _make_subclass(
            self, *, model_cls=object,
            analyzer_versions=None, **extra_attrs):
        if analyzer_versions is None:
            analyzer_versions = dict(self.SINGLETON_AV)
        attrs = {
            '_load_appmetadata': lambda self: make_metadata(
                hf_helper=True,
                analyzer_versions=dict(analyzer_versions),
            ),
            '_appmetadata': lambda self: None,
            '_annotate': lambda self, mmif, **kw: mmif,
            'MODEL_CLS': model_cls,
        }
        attrs.update(extra_attrs)
        from clams.app import ClamsHFPromptableApp
        return type('TestHFApp', (ClamsHFPromptableApp,), attrs)

    def test_missing_model_cls_raises(self):
        cls = self._make_subclass(model_cls=None)
        with self.assertRaises(ValueError) as ctx:
            cls()
        self.assertIn('MODEL_CLS', str(ctx.exception))

    def test_missing_analyzer_versions_raises(self):
        # Use the plain promptable helper so promptable params are
        # injected (parent __init__ passes) but analyzer_versions is
        # absent and ``model`` was never injected. HF __init__ should
        # refuse on the analyzer_versions check.
        from clams.app import ClamsHFPromptableApp
        cls = type('TestHFAppBad', (ClamsHFPromptableApp,), {
            '_load_appmetadata': lambda self: make_metadata(
                call_helper=True),  # plain promptable, no analyzer_versions
            '_appmetadata': lambda self: None,
            '_annotate': lambda self, mmif, **kw: mmif,
            'MODEL_CLS': object,
        })
        with self.assertRaises(ValueError) as ctx:
            cls()
        self.assertIn('analyzer_versions', str(ctx.exception))

    def _patch_load(self):
        """
        Context-manager-ish helper that swaps in a fake ``load_hf_model``
        recording every call. Returns ``(restore_fn, calls_list)``.
        """
        import clams.backends.hf as hf_module
        original = hf_module.load_hf_model
        calls = []

        def fake_load(model_id, model_cls, **kwargs):
            calls.append({'model_id': model_id, 'model_cls': model_cls, **kwargs})
            # processor / model / device tuple uniquely identifiable
            return (f'PROC:{model_id}@{kwargs.get("revision")}',
                    f'MODEL:{model_id}@{kwargs.get("revision")}',
                    'cpu')

        hf_module.load_hf_model = fake_load
        return (lambda: setattr(hf_module, 'load_hf_model', original)), calls

    def test_singleton_eagerly_preloads_in_init(self):
        restore, calls = self._patch_load()
        try:
            cls = self._make_subclass(
                analyzer_versions=self.SINGLETON_AV,
                DTYPE='FAKE_DTYPE',
                PADDING_SIDE='left',
                MODEL_KWARGS={'trust_remote_code': True},
            )
            app = cls()
            # eager load on the single family member
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]['model_id'], 'org/fake-model')
            self.assertEqual(calls[0]['revision'], 'deadbee')
            self.assertEqual(calls[0]['dtype'], 'FAKE_DTYPE')
            self.assertEqual(calls[0]['padding_side'], 'left')
            self.assertEqual(
                calls[0]['model_kwargs'], {'trust_remote_code': True})
            # self.processor / self.model / self.device populated
            self.assertEqual(app.processor, 'PROC:org/fake-model@deadbee')
            self.assertEqual(app.model, 'MODEL:org/fake-model@deadbee')
            self.assertEqual(app.device, 'cpu')
        finally:
            restore()

    def test_multimember_defers_loading(self):
        restore, calls = self._patch_load()
        try:
            cls = self._make_subclass(analyzer_versions=self.MULTI_AV)
            app = cls()
            # no eager load for multi-member families
            self.assertEqual(calls, [])
            self.assertIsNone(app.processor)
            self.assertIsNone(app.model)
            self.assertIsNone(app.device)
        finally:
            restore()

    def test_load_model_parses_at_revision_form_and_caches(self):
        restore, calls = self._patch_load()
        try:
            cls = self._make_subclass(analyzer_versions=self.MULTI_AV)
            app = cls()
            # first call -- load via load_hf_model
            app.load_model('org/large-model@aaaaaaa')
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]['model_id'], 'org/large-model')
            self.assertEqual(calls[0]['revision'], 'aaaaaaa')
            self.assertEqual(app.processor, 'PROC:org/large-model@aaaaaaa')
            # second call same model -- cache hit, no new load
            app.load_model('org/large-model@aaaaaaa')
            self.assertEqual(len(calls), 1)
            # switch to other family member -- new load
            app.load_model('org/small-model@bbbbbbb')
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1]['model_id'], 'org/small-model')
            self.assertEqual(calls[1]['revision'], 'bbbbbbb')
            self.assertEqual(app.processor, 'PROC:org/small-model@bbbbbbb')
            # back to first -- still cached
            app.load_model('org/large-model@aaaaaaa')
            self.assertEqual(len(calls), 2)
            self.assertEqual(app.processor, 'PROC:org/large-model@aaaaaaa')
        finally:
            restore()

    def test_load_model_accepts_raw_form_looks_up_revision(self):
        restore, calls = self._patch_load()
        try:
            cls = self._make_subclass(analyzer_versions=self.MULTI_AV)
            app = cls()
            app.load_model('org/small-model')  # no @rev suffix
            self.assertEqual(calls[0]['model_id'], 'org/small-model')
            self.assertEqual(calls[0]['revision'], 'bbbbbbb')
        finally:
            restore()

    def test_refine_params_expands_modelid_to_at_revision(self):
        restore, _ = self._patch_load()
        try:
            cls = self._make_subclass(analyzer_versions=self.MULTI_AV)
            app = cls()
            refined = app._refine_params(
                prompt=['hi'],
                model=['org/large-model'],
            )
            self.assertEqual(refined['model'], 'org/large-model@aaaaaaa')
        finally:
            restore()

    def test_singleton_default_lets_user_omit_modelid(self):
        restore, _ = self._patch_load()
        try:
            cls = self._make_subclass(analyzer_versions=self.SINGLETON_AV)
            app = cls()
            # No model in input -- SDK fills in the singleton default,
            # then our override expands it.
            refined = app._refine_params(prompt=['hi'])
            self.assertEqual(refined['model'], 'org/fake-model@deadbee')
        finally:
            restore()

    def test_build_template_kwargs_default_empty(self):
        restore, _ = self._patch_load()
        try:
            app = self._make_subclass(analyzer_versions=self.SINGLETON_AV)()
            self.assertEqual(app.build_template_kwargs(), {})
        finally:
            restore()

    def test_model_load_kwargs_default_is_model_kwargs_copy(self):
        restore, calls = self._patch_load()
        try:
            app = self._make_subclass(
                analyzer_versions=self.SINGLETON_AV,
                MODEL_KWARGS={'trust_remote_code': True},
            )()
            # eager singleton load forwarded the class-level MODEL_KWARGS
            self.assertEqual(
                calls[0]['model_kwargs'], {'trust_remote_code': True})
            # and it's a copy, not the same object
            self.assertIsNot(
                app.model_load_kwargs('org/fake-model', 'deadbee'),
                app.MODEL_KWARGS)
        finally:
            restore()

    def test_model_load_kwargs_override_is_per_variant(self):
        restore, calls = self._patch_load()
        try:
            def per_variant(self, model_id, revision):
                kw = {'base': True}
                if model_id.endswith('small-model'):
                    kw['quantized'] = True
                return kw

            cls = self._make_subclass(
                analyzer_versions=self.MULTI_AV,
                model_load_kwargs=per_variant,
            )
            app = cls()  # multi-member: no eager load
            self.assertEqual(len(calls), 0)
            app.load_model('org/large-model')
            app.load_model('org/small-model')
            large = next(c for c in calls if c['model_id'] == 'org/large-model')
            small = next(c for c in calls if c['model_id'] == 'org/small-model')
            self.assertEqual(large['model_kwargs'], {'base': True})
            self.assertEqual(
                small['model_kwargs'], {'base': True, 'quantized': True})
        finally:
            restore()


if __name__ == '__main__':
    unittest.main()
