"""
Tests for the code-generation recipes in :mod:`clams.develop`.
"""
import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mmif import AnnotationTypes, Document, DocumentTypes, Mmif

from clams.app import PromptTask
from clams.develop import CookieCutter


class TestUtlTfRecipe(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with contextlib.redirect_stdout(io.StringIO()):
            CookieCutter(
                name='tfapp', outdir=tmp.name, recipes=['utl-tf']).bake()
        path = Path(tmp.name) / 'tfapp' / 'utils' / 'timeframe.py'
        mod_name = f'_baked_timeframe_{id(self)}'
        spec = importlib.util.spec_from_file_location(mod_name, path)
        self.baked = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = self.baked
        self.addCleanup(sys.modules.pop, mod_name, None)
        spec.loader.exec_module(self.baked)

        self.mmif = Mmif(validate=False)
        self.vdoc = Document()
        self.vdoc.at_type = DocumentTypes.VideoDocument
        self.vdoc.id = 'v1'
        self.vdoc.location = 'file:///video.mp4'
        self.mmif.add_document(self.vdoc)
        up_view = self.mmif.new_view()
        up_view.metadata.app = 'http://upstream/1'
        self.tp = up_view.new_annotation(
            AnnotationTypes.TimePoint, document=self.vdoc.id,
            timePoint=500)
        self.tf_a = up_view.new_annotation(
            AnnotationTypes.TimeFrame, document=self.vdoc.id,
            label='scene')
        self.tf_b = up_view.new_annotation(
            AnnotationTypes.TimeFrame, document=self.vdoc.id,
            label='slate')
        self.out_view = self.mmif.new_view()
        self.out_view.metadata.app = 'http://downstream/1'

    def patch_extractor(self, results):
        """
        Patch the extractor used by the baked module.

        :param results: map of TimeFrame id to ``(images, sources)``
        """
        def fake(mmif, tf, **kwargs):
            return results[tf.id]

        return mock.patch.object(
            self.baked.vdh, 'extract_images_by_mode_with_sources', fake)

    def collect(self, labels=()):
        return self.baked.collect_timeframes_of_interest(
            self.mmif, self.out_view, self.vdoc, list(labels))

    def test_baked_module_exposes_helpers(self):
        for name in ('iter_timeframes', 'to_timepoints',
                     'collect_timeframes_of_interest'):
            self.assertTrue(callable(getattr(self.baked, name)))

    def test_tasks_carry_images_sources_and_origins(self):
        results = {
            self.tf_a.id: (['i0', 'i1', 'i2'], [self.tp.id, 1500, 2500]),
            self.tf_b.id: (['j0'], [self.tp.id]),
        }
        with self.patch_extractor(results):
            tasks = self.collect()
        self.assertEqual(len(tasks), 2)
        for task in tasks:
            self.assertIsInstance(task, PromptTask)
            self.assertEqual(len(task.images), len(task.origins))
        task_a, task_b = tasks
        self.assertEqual(task_a.source, self.tf_a.id)
        self.assertEqual(task_a.images, ['i0', 'i1', 'i2'])
        self.assertEqual(task_a.origins[0], self.tp.id)
        out_ids = [a.id for a in self.out_view.get_annotations()]
        for origin, expected_ms in zip(task_a.origins[1:], (1500, 2500)):
            self.assertNotEqual(origin, self.tp.id)
            self.assertIn(origin, out_ids)
            minted = self.mmif[origin]
            self.assertEqual(minted.at_type, AnnotationTypes.TimePoint)
            self.assertEqual(minted.get_property('timePoint'), expected_ms)
            self.assertEqual(
                minted.get_property('document'), self.vdoc.id)
        self.assertEqual(task_b.source, self.tf_b.id)
        self.assertEqual(task_b.images, ['j0'])
        self.assertEqual(task_b.origins, [self.tp.id])
        # only the two int sources mint new TimePoints
        self.assertEqual(len(out_ids), 2)

    def test_label_filter_keeps_only_matching_timeframes(self):
        results = {
            self.tf_a.id: (['i0'], [self.tp.id]),
            self.tf_b.id: (['j0'], [self.tp.id]),
        }
        with self.patch_extractor(results):
            tasks = self.collect(['slate'])
        self.assertEqual([t.source for t in tasks], [self.tf_b.id])

    def test_timeframe_without_images_yields_no_task(self):
        results = {
            self.tf_a.id: ([], []),
            self.tf_b.id: (['j0'], [self.tp.id]),
        }
        with self.patch_extractor(results):
            tasks = self.collect()
        self.assertEqual([t.source for t in tasks], [self.tf_b.id])
