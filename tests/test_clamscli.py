import contextlib
import copy
import io
import os
import unittest

from mmif.serialize import Mmif
from mmif.vocabulary import DocumentTypes, AnnotationTypes

import clams
from clams.mmif_utils import rewind
from clams.mmif_utils import source


class TestCli(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = clams.prep_argparser()

    def test_clams_cli(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stdout(stdout):
            self.parser.parse_args("-v".split())
        self.assertEqual(e.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(),
                         clams.version_template.format(clams.__version__, clams.__specver__))


class TestSource(unittest.TestCase):

    def setUp(self) -> None:
        self.parser = clams.source.prep_argparser()
        self.prefix = None
        self.scheme = None
        self.docs = []

    def get_params(self):
        
        params = []
        if self.prefix:
            params.extend(f'--prefix {self.prefix}'.split())
        if self.scheme:
            params.extend(f'--scheme {self.scheme}'.split())
        params.extend(self.docs)
        return params

    def generate_source_mmif(self):
        
        # to suppress output (otherwise, set to stdout by default
        args = self.parser.parse_args(self.get_params())
        args.output = os.devnull
        
        return source.main(args)

    def test_accept_file_paths(self):
        self.docs.append("video:/a/b/c.mp4")
        self.docs.append('text:/a/b/c.txt')
        source_mmif = Mmif(self.generate_source_mmif())
        self.assertEqual(len(source_mmif.documents), 2)
        self.assertTrue(all(map(lambda x: x.location_scheme() == 'file', source_mmif.documents)))

        # relative path
        self.docs.append('audio:a/b/c.mp3')
        with self.assertRaises(ValueError):
            self.generate_source_mmif()

    def test_accept_prefixed_file_paths(self):
        self.prefix = '/a/b'
        self.docs.append("video:c.mp4")
        self.docs.append("text:c.txt")
        source_mmif = Mmif(self.generate_source_mmif())
        self.assertEqual(len(source_mmif.documents), 2)
        
        # absolute path + prefix flag
        self.docs.append("audio:/c.mp3")
        with self.assertRaises(ValueError):
            self.generate_source_mmif()

    def test_reject_relative_prefix(self):
        self.prefix = '/'
        self.docs.append("video:c.mp4")
        source_mmif = Mmif(self.generate_source_mmif())
        self.assertEqual(len(source_mmif.documents), 1)
        
        self.prefix = '.'
        with self.assertRaises(ValueError):
            self.generate_source_mmif()

    def test_reject_unknown_mime(self):
        self.docs.append("unknown_mime/more_unknown:/c.mp4")
        with self.assertRaises(ValueError):
            self.generate_source_mmif()

    def test_accept_scheme_files(self):
        self.scheme = 'baapb'
        self.docs.append("video:cpb-aacip-123-4567890.video")
        self.docs.append("audio:cpb-aacip-111-1111111.audio")
        source_mmif = Mmif(self.generate_source_mmif())
        self.assertEqual(len(source_mmif.documents), 2)
        self.assertTrue(all(map(lambda x: x.location_scheme() == self.scheme, source_mmif.documents)))

    def test_generate_mixed_scheme(self):
        self.scheme = 'baapb'
        self.docs.append("video:file:///data/cpb-aacip-123-4567890.mp4")
        self.docs.append("audio:cpb-aacip-111-1111111.audio")
        source_mmif = Mmif(self.generate_source_mmif())
        self.assertEqual(len(source_mmif.documents), 2)
        schemes = set(doc.location_scheme() for doc in source_mmif.documents)
        self.assertEqual(len(schemes), 2)
        self.assertTrue('baapb' in schemes)
        self.assertTrue('file' in schemes)


class TestRewind(unittest.TestCase):
    def setUp(self):
        self.dummy_app_one = ExampleApp()
        self.dummy_app_one.metadata.identifier = "dummy_app_one"
        self.dummy_app_two = ExampleApp()
        self.dummy_app_two.metadata.identifier = "dummy_app_two"

        # mmif we add views to
        self.mmif_one = Mmif(
            {
                "metadata": {"mmif": "http://mmif.clams.ai/1.0.0"},
                "documents": [],
                "views": [],
            }
        )

        # baseline empty mmif for comparison
        self.empty_mmif = Mmif(
            {
                "metadata": {"mmif": "http://mmif.clams.ai/1.0.0"},
                "documents": [],
                "views": [],
            }
        )

    def test_view_rewind(self):
        """
        Tests the use of "view-rewiding" to remove multiple views from a single app.
        """
        # Regular Case
        mmif_added_views = self.dummy_app_one.mmif_add_views(self.mmif_one, 10)
        self.assertEqual(len(mmif_added_views.views), 10)
        rewound = rewind.rewind_mmif(mmif_added_views, 5)
        self.assertEqual(len(rewound.views), 5)
        # rewinding is done "in-place"
        self.assertEqual(len(rewound.views), len(mmif_added_views.views))

    def test_app_rewind(self):
        # Regular Case
        app_one_views = 3 
        app_two_views = 2
        app_one_out = self.dummy_app_one.mmif_add_views(self.mmif_one, app_one_views)
        app_two_out = self.dummy_app_two.mmif_add_views(app_one_out, app_two_views)
        self.assertEqual(len(app_two_out.views), app_one_views + app_two_views)
        rewound = rewind.rewind_mmif(app_two_out, 1, choice_is_viewnum=False)
        self.assertEqual(len(rewound.views), app_one_views)
        
def compare_views(a: Mmif, b: Mmif) -> bool:
    perfect_match = True
    for view_a, view_b in zip(a.views, b.views):
        if view_a != view_b:
            perfect_match = False
    return perfect_match


class ExampleApp(clams.app.ClamsApp):
    """This is a barebones implementation of a CLAMS App
    used to generate simple Views within a mmif object
    for testing purposes. The three methods here all streamline
    the mmif annotation process for the purposes of repeated insertion
    and removal.
    """

    app_version = "lorem_ipsum"

    def _appmetadata(self):
        pass

    def _annotate(self, mmif: Mmif, message: str, idx: int, **kwargs):
        if type(mmif) is not Mmif:
            mmif_obj = Mmif(mmif, validate=False)
        else:
            mmif_obj = mmif

        new_view = mmif_obj.new_view()
        self.sign_view(new_view, runtime_conf=kwargs)
        self.gen_annotate(new_view, message, idx)

        d1 = DocumentTypes.VideoDocument
        d2 = DocumentTypes.from_str(f"{str(d1)[:-1]}99")
        if mmif.get_documents_by_type(d2):
            new_view.new_annotation(AnnotationTypes.TimePoint, "tp1")
        if "raise_error" in kwargs and kwargs["raise_error"]:
            raise ValueError
        return mmif

    def gen_annotate(self, mmif_view, message, idx=0):
        mmif_view.new_contain(
            AnnotationTypes.TimeFrame, **{"producer": "dummy-producer"}
        )
        ann = mmif_view.new_annotation(
            AnnotationTypes.TimeFrame, "a1", start=10, end=99
        )
        ann.add_property("f1", message)

    def mmif_add_views(self, mmif_obj, idx: int):
        """Helper Function to add an arbitrary number of views to a mmif"""
        for i in range(idx):
            mmif_obj = self._annotate(mmif_obj, message=f"message {i}", idx=idx)
        return mmif_obj

if __name__ == '__main__':
    unittest.main()
