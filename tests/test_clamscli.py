import io
import os
import unittest
import contextlib
import clams
from clams import source
from mmif.serialize import Mmif


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


if __name__ == '__main__':
    unittest.main()
