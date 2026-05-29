"""
Tests for :mod:`clams.backends.hf`.

Exercises the device / dtype / padding-side / kwargs-passthrough
behavior of both :func:`load_hf_model` and :func:`load_hf_pipeline`
against mocked ``transformers`` model, processor, and pipeline
constructors.

If ``torch`` is not installed, the whole file is skipped (it is an
optional dep behind the ``[hf]`` extra).
"""
import unittest
from unittest import mock

import pytest

pytest.importorskip('torch')
pytest.importorskip('transformers')

# Force ``transformers.pipeline`` to be eagerly resolved into the
# package's ``__dict__``. ``transformers`` uses a lazy-loading
# ``_LazyModule`` that fetches submodule attributes via
# ``__getattr__`` on first access; before that, the attribute does
# not live in ``__dict__``. The first ``mock.patch('transformers.pipeline', ...)``
# call would then silently fail to redirect ``from transformers import pipeline``
# inside the helper. Touching the attribute here resolves it and
# caches it in the package dict, so subsequent ``mock.patch`` calls
# rewrite the real entry as expected.
import transformers  # noqa: E402
_ = transformers.pipeline

from clams.backends.hf import load_hf_model, load_hf_pipeline  # noqa: E402


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------

class _MockModel:
    """Stand-in for a ``transformers`` model class."""

    # cross-test state — each test should set this to None first
    last_from_pretrained_args = None
    last_from_pretrained_kwargs = None

    @classmethod
    def from_pretrained(cls, model_id, **kwargs):
        cls.last_from_pretrained_args = (model_id,)
        cls.last_from_pretrained_kwargs = dict(kwargs)
        return cls()

    def __init__(self):
        self.device = None
        self.eval_called = False

    def to(self, device):
        self.device = device
        return self

    def eval(self):
        self.eval_called = True
        return self


class _MockTokenizer:
    def __init__(self):
        self.padding_side = 'right'
        self.pad_token = None
        self.eos_token = '<eos>'


class _MockProcessor:
    """Stand-in for ``AutoProcessor`` (or similar)."""

    last_from_pretrained_args = None
    last_from_pretrained_kwargs = None

    @classmethod
    def from_pretrained(cls, model_id, **kwargs):
        cls.last_from_pretrained_args = (model_id,)
        cls.last_from_pretrained_kwargs = dict(kwargs)
        return cls()

    def __init__(self):
        self.tokenizer = _MockTokenizer()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestDefaultsOnly(unittest.TestCase):
    """
    Case (a): caller passes only ``model_id`` + ``model_cls``.
    No dtype, no padding_side, no extra kwargs.
    """

    def setUp(self):
        _MockModel.last_from_pretrained_args = None
        _MockModel.last_from_pretrained_kwargs = None
        _MockProcessor.last_from_pretrained_args = None
        _MockProcessor.last_from_pretrained_kwargs = None

    def test_returns_processor_model_device_tuple(self):
        result = load_hf_model(
            'fake-model-id', _MockModel, processor_cls=_MockProcessor)
        self.assertEqual(len(result), 3)
        processor, model, device = result
        self.assertIsInstance(processor, _MockProcessor)
        self.assertIsInstance(model, _MockModel)
        self.assertIsInstance(device, str)
        # cpu or cuda depending on host — must be one of them
        self.assertIn(device, ('cpu', 'cuda'))

    def test_no_torch_dtype_passed_when_dtype_is_none(self):
        load_hf_model(
            'fake-model-id', _MockModel, processor_cls=_MockProcessor)
        # When dtype is None, helper should NOT inject torch_dtype into
        # model_cls.from_pretrained (let the model class use its own
        # default).
        kwargs = _MockModel.last_from_pretrained_kwargs
        self.assertNotIn('torch_dtype', kwargs)

    def test_padding_side_untouched_when_not_requested(self):
        processor, _, _ = load_hf_model(
            'fake-model-id', _MockModel, processor_cls=_MockProcessor)
        # Default 'right' should persist; helper should NOT have
        # rewritten it.
        self.assertEqual(processor.tokenizer.padding_side, 'right')
        # pad_token should NOT have been forced to EOS.
        self.assertIsNone(processor.tokenizer.pad_token)

    def test_model_put_in_eval_mode(self):
        _, model, _ = load_hf_model(
            'fake-model-id', _MockModel, processor_cls=_MockProcessor)
        self.assertTrue(model.eval_called)


class TestDecoderOnlyMode(unittest.TestCase):
    """
    Case (b): caller passes ``padding_side='left'`` (decoder-only
    batched generation) and an explicit ``dtype``.
    """

    def setUp(self):
        _MockModel.last_from_pretrained_args = None
        _MockModel.last_from_pretrained_kwargs = None
        _MockProcessor.last_from_pretrained_args = None
        _MockProcessor.last_from_pretrained_kwargs = None

    def test_padding_side_set_to_left_on_tokenizer(self):
        processor, _, _ = load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            padding_side='left',
        )
        self.assertEqual(processor.tokenizer.padding_side, 'left')

    def test_pad_token_set_from_eos_when_unset(self):
        processor, _, _ = load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            padding_side='left',
        )
        self.assertEqual(
            processor.tokenizer.pad_token,
            processor.tokenizer.eos_token,
        )

    def test_dtype_forwarded_as_torch_dtype(self):
        import torch
        load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            dtype=torch.bfloat16,
            padding_side='left',
        )
        self.assertEqual(
            _MockModel.last_from_pretrained_kwargs.get('torch_dtype'),
            torch.bfloat16,
        )


class TestKwargsPassThrough(unittest.TestCase):
    """
    Case (c): ``model_kwargs`` and ``processor_kwargs`` reach the
    respective ``from_pretrained`` calls. Validates the SWT-style
    pattern (use_safetensors, use_fast, add_pooling_layer, etc.).
    """

    def setUp(self):
        _MockModel.last_from_pretrained_args = None
        _MockModel.last_from_pretrained_kwargs = None
        _MockProcessor.last_from_pretrained_args = None
        _MockProcessor.last_from_pretrained_kwargs = None

    def test_model_kwargs_reach_from_pretrained(self):
        load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            model_kwargs={'use_safetensors': True,
                          'add_pooling_layer': False},
        )
        kw = _MockModel.last_from_pretrained_kwargs
        self.assertTrue(kw.get('use_safetensors'))
        self.assertFalse(kw.get('add_pooling_layer'))

    def test_processor_kwargs_reach_from_pretrained(self):
        load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            processor_kwargs={'use_safetensors': True, 'use_fast': True},
        )
        kw = _MockProcessor.last_from_pretrained_kwargs
        self.assertTrue(kw.get('use_safetensors'))
        self.assertTrue(kw.get('use_fast'))

    def test_model_id_arrives_first_positional(self):
        load_hf_model(
            'fake-model-id', _MockModel, processor_cls=_MockProcessor)
        self.assertEqual(
            _MockModel.last_from_pretrained_args, ('fake-model-id',))
        self.assertEqual(
            _MockProcessor.last_from_pretrained_args, ('fake-model-id',))

    def test_model_and_processor_kwargs_do_not_cross_contaminate(self):
        """SWT mixes incompatible kwargs across model and processor;
        ensure helper doesn't blindly merge them."""
        load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            model_kwargs={'add_pooling_layer': False},
            processor_kwargs={'use_fast': True},
        )
        # add_pooling_layer is model-only; should NOT reach processor
        self.assertNotIn(
            'add_pooling_layer',
            _MockProcessor.last_from_pretrained_kwargs)
        # use_fast is processor-only; should NOT reach model
        self.assertNotIn(
            'use_fast',
            _MockModel.last_from_pretrained_kwargs)


class TestDeviceResolution(unittest.TestCase):
    """The helper auto-detects cuda/cpu when device is None."""

    def setUp(self):
        _MockModel.last_from_pretrained_args = None
        _MockModel.last_from_pretrained_kwargs = None

    def test_explicit_device_honored(self):
        _, model, device = load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            device='cpu',
        )
        self.assertEqual(device, 'cpu')
        self.assertEqual(model.device, 'cpu')


class TestMoveToDeviceFlag(unittest.TestCase):
    """
    ``move_to_device=False`` skips both the ``.to(device)`` move and
    the ``.eval()`` switch, for library-style HF wrappers that defer
    device placement and inference-mode switching to a downstream
    consumer.
    """

    def setUp(self):
        _MockModel.last_from_pretrained_args = None
        _MockModel.last_from_pretrained_kwargs = None

    def test_move_skipped_when_flag_false(self):
        _, model, _ = load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            move_to_device=False,
        )
        # _MockModel.__init__ leaves device=None; .to() would set it.
        self.assertIsNone(model.device)

    def test_eval_skipped_when_flag_false(self):
        _, model, _ = load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            move_to_device=False,
        )
        self.assertFalse(model.eval_called)

    def test_resolved_device_still_returned(self):
        """Even when not moved, the resolved target is reported so the
        downstream consumer can use it for its own ``.to(device)``."""
        _, _, device = load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            device='cpu',
            move_to_device=False,
        )
        self.assertEqual(device, 'cpu')

    def test_default_still_moves_and_evals(self):
        """Regression guard: the default (omitted) value of the new
        flag preserves prior behavior."""
        _, model, _ = load_hf_model(
            'fake-model-id', _MockModel,
            processor_cls=_MockProcessor,
            device='cpu',
        )
        self.assertEqual(model.device, 'cpu')
        self.assertTrue(model.eval_called)


# ---------------------------------------------------------------------------
# load_hf_pipeline tests
# ---------------------------------------------------------------------------

class _FakePipeline:
    """Captures the args/kwargs the helper forwards to
    ``transformers.pipeline``. Behaves as the returned pipeline object
    too -- just a tagged callable stand-in."""

    last_args = None
    last_kwargs = None

    def __init__(self, *args, **kwargs):
        type(self).last_args = args
        type(self).last_kwargs = dict(kwargs)


def _patch_pipeline():
    """Patch ``transformers.pipeline`` to record its call and return a
    ``_FakePipeline`` instance."""
    _FakePipeline.last_args = None
    _FakePipeline.last_kwargs = None
    return mock.patch('transformers.pipeline', _FakePipeline)


class TestLoadHFPipelineDefaults(unittest.TestCase):
    """The default path: just task + model_id."""

    def test_returns_pipeline_and_device(self):
        with _patch_pipeline():
            pipe, device = load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny')
        self.assertIsInstance(pipe, _FakePipeline)
        self.assertIn(device, ('cpu', 'cuda'))

    def test_task_arrives_first_positional(self):
        with _patch_pipeline():
            load_hf_pipeline(
                'token-classification', 'fake/ner-model')
        self.assertEqual(_FakePipeline.last_args, ('token-classification',))

    def test_model_id_forwarded_as_model_kwarg(self):
        with _patch_pipeline():
            load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny')
        self.assertEqual(
            _FakePipeline.last_kwargs.get('model'), 'openai/whisper-tiny')

    def test_no_revision_kwarg_when_not_specified(self):
        with _patch_pipeline():
            load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny')
        self.assertNotIn('revision', _FakePipeline.last_kwargs)


class TestLoadHFPipelineDevice(unittest.TestCase):
    """Device handling: auto-detect, explicit string, explicit int."""

    def test_auto_detect_when_none(self):
        with _patch_pipeline():
            _, device = load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny')
        self.assertIn(device, ('cpu', 'cuda'))
        # Same value should have been passed to pipeline().
        self.assertEqual(_FakePipeline.last_kwargs.get('device'), device)

    def test_explicit_string_device_honored(self):
        with _patch_pipeline():
            _, device = load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny',
                device='cpu')
        self.assertEqual(device, 'cpu')
        self.assertEqual(_FakePipeline.last_kwargs.get('device'), 'cpu')

    def test_explicit_int_device_honored(self):
        """``pipeline()`` natively accepts ``-1`` for CPU, ``0+`` for
        a specific GPU index. The helper passes it through unchanged."""
        with _patch_pipeline():
            _, device = load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny',
                device=-1)
        self.assertEqual(device, -1)
        self.assertEqual(_FakePipeline.last_kwargs.get('device'), -1)


class TestLoadHFPipelineKwargsPassThrough(unittest.TestCase):
    """``model_kwargs`` lands inside ``pipeline(model_kwargs={...})``;
    ``pipeline_kwargs`` is spread directly into the pipeline call."""

    def test_pipeline_kwargs_spread_into_call(self):
        with _patch_pipeline():
            load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny',
                pipeline_kwargs={
                    'generate_kwargs': {'num_beams': 5},
                    'batch_size': 8,
                })
        kw = _FakePipeline.last_kwargs
        self.assertEqual(kw.get('generate_kwargs'), {'num_beams': 5})
        self.assertEqual(kw.get('batch_size'), 8)

    def test_model_kwargs_nested_under_model_kwargs(self):
        with _patch_pipeline():
            load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny',
                model_kwargs={'use_safetensors': True})
        kw = _FakePipeline.last_kwargs
        self.assertEqual(kw.get('model_kwargs'),
                         {'use_safetensors': True})

    def test_revision_forwarded(self):
        with _patch_pipeline():
            load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny',
                revision='abc1234')
        self.assertEqual(_FakePipeline.last_kwargs.get('revision'), 'abc1234')

    def test_explicit_helper_args_take_precedence(self):
        """If the caller smuggles ``model`` / ``device`` / ``revision``
        through ``pipeline_kwargs``, the helper's own args win."""
        with _patch_pipeline():
            load_hf_pipeline(
                'automatic-speech-recognition', 'openai/whisper-tiny',
                device='cpu', revision='abc1234',
                pipeline_kwargs={
                    'model': 'should-be-overridden',
                    'device': 'should-be-overridden',
                    'revision': 'should-be-overridden',
                })
        kw = _FakePipeline.last_kwargs
        self.assertEqual(kw['model'], 'openai/whisper-tiny')
        self.assertEqual(kw['device'], 'cpu')
        self.assertEqual(kw['revision'], 'abc1234')


if __name__ == '__main__':
    unittest.main()
