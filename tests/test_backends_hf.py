"""
Tests for :func:`clams.backends.hf.load_hf_model`.

Exercises the device / dtype / padding-side / kwargs-passthrough
behavior of the helper against mocked ``transformers`` model and
processor classes.

If ``torch`` is not installed, the whole file is skipped (it is an
optional dep behind the ``[hf]`` extra).
"""
import unittest

import pytest

pytest.importorskip('torch')

from clams.backends.hf import load_hf_model  # noqa: E402


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


if __name__ == '__main__':
    unittest.main()
