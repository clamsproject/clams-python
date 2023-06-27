import io
import unittest
import contextlib
import clams
from clams import source


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
        self.docs = []

    def get_params(self):
        if self.prefix:
            params = f'--prefix {self.prefix}'.split() + self.docs
        else:
            params = self.docs
        return params

    def generate_source_mmif_from_file(self):
        return source.generate_source_mmif_from_file(**vars(self.parser.parse_args(self.get_params())))

    def test_accept_file_paths(self):
        self.docs.append("video:/a/b/c.mp4")
        self.generate_source_mmif_from_file()
        self.docs.append('text:/a/b/c.txt')
        self.generate_source_mmif_from_file()
        self.docs.append('audio:a/b/c.mp3')
        with self.assertRaises(ValueError):
            self.generate_source_mmif_from_file()

    def test_accept_prefixed_file_paths(self):
        self.prefix = '/a/b'
        self.docs.append("video:c.mp4")
        self.generate_source_mmif_from_file()
        self.docs.append("text:c.txt")
        self.generate_source_mmif_from_file()
        self.docs.append("audio:/c.mp3")
        with self.assertRaises(ValueError):
            self.generate_source_mmif_from_file()

    def test_reject_relative_prefix(self):
        self.prefix = '/'
        self.docs.append("video:c.mp4")
        self.generate_source_mmif_from_file()
        self.prefix = '.'
        with self.assertRaises(ValueError):
            self.generate_source_mmif_from_file()

    def test_reject_unknown_mime(self):
        self.prefix = None
        self.docs.append("unknown_mime/more_unknown:/c.mp4")
        with self.assertRaises(ValueError):
            self.generate_source_mmif_from_file()

class TestSchemeSupport(unittest.TestCase):

    def setUp(self) -> None:
        self.parser = clams.source.prep_argparser()
        self.scheme = None
        self.docs = []

    def get_params(self):
        if self.scheme:
            params = f'--scheme {self.scheme}'.split() + self.docs
        else:
            params = self.docs
        return params

    def generate_source_mmif_from_customscheme(self):
        return source.generate_source_mmif_from_customscheme(**vars(self.parser.parse_args(self.get_params())))
    
    def test_accept_scheme_files(self):
        self.scheme = 'baapb'
        self.docs.append("video:cpb-aacip-123-4567890.video")
        self.generate_source_mmif_from_customscheme()
        self.docs.append("audio:cpb-aacip-111-1111111.audio")
        self.generate_source_mmif_from_customscheme()

    def test_reject_unknown_mime(self):
        self.scheme = None
        self.docs.append("unknown_mime/more_unknown:cpb-aacip-example.unknown")
        with self.assertRaises(ValueError):
            self.generate_source_mmif_from_customscheme()


if __name__ == '__main__':
    unittest.main()
