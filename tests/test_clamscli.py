import unittest
import pytest
from clams import source


class TestSource(unittest.TestCase):
    def test_accept_file_paths(self):
        prefix = None
        doc1 = "video:/a/b/c.mp4"
        source.generate_source_mmif(documents=[doc1], prefix=prefix)
        doc2 = 'text:/a/b/c.txt'
        source.generate_source_mmif(documents=[doc1, doc2], prefix=prefix)
        doc3 = 'audio:a/b/c.mp3'
        with pytest.raises(ValueError):
            source.generate_source_mmif(documents=[doc1, doc2, doc3], prefix=prefix)

    def test_accept_prefixed_file_paths(self):
        prefix = '/a/b'
        doc1 = "video:c.mp4"
        source.generate_source_mmif(documents=[doc1], prefix=prefix)
        doc2 = 'text:c.txt'
        source.generate_source_mmif(documents=[doc1, doc2], prefix=prefix)
        doc3 = 'audio:/c.mp3'
        with pytest.raises(ValueError):
            source.generate_source_mmif(documents=[doc1, doc2, doc3], prefix=prefix)

    def test_reject_unknown_mime(self):
        prefix = None
        doc1 = "unknown_mime/more_unknown:/c.mp4"
        with pytest.raises(ValueError):
            source.generate_source_mmif(documents=[doc1], prefix=prefix)


if __name__ == '__main__':
    unittest.main()
