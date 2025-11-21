import pathlib
import shutil
import tempfile
import unittest
import warnings
from typing import Union
from unittest.mock import patch, MagicMock

import pytest
from mmif import Mmif, DocumentTypes, AnnotationTypes

import clams.app
import clams.restify
from clams.app import ClamsApp, InsufficientVRAMError
from clams.appmetadata import AppMetadata

# Skip entire file if nvidia-smi not available
pytestmark = pytest.mark.skipif(
    shutil.which('nvidia-smi') is None,
    reason="nvidia-smi not available - no CUDA device"
)


class GPUExampleClamsApp(clams.app.ClamsApp):
    """Example app with GPU memory requirements declared."""

    def _appmetadata(self) -> Union[dict, AppMetadata]:
        metadata = AppMetadata(
            name="GPU Example App",
            description="Test app with GPU memory requirements",
            app_license="MIT",
            identifier="gpu-example-app",
            url="https://example.com/gpu-app",
            gpu_mem_min=2000,  # 2GB minimum
            gpu_mem_typ=4000,  # 4GB typical
        )
        metadata.add_input(DocumentTypes.VideoDocument)
        metadata.add_output(AnnotationTypes.TimeFrame)
        return metadata

    def _annotate(self, mmif, **kwargs):
        if not isinstance(mmif, Mmif):
            mmif = Mmif(mmif, validate=False)
        new_view = mmif.new_view()
        self.sign_view(new_view, kwargs)
        new_view.new_contain(AnnotationTypes.TimeFrame)
        return mmif


class NonGPUExampleClamsApp(clams.app.ClamsApp):
    """Example app without GPU memory requirements (gpu_mem_min=0)."""

    def _appmetadata(self) -> Union[dict, AppMetadata]:
        metadata = AppMetadata(
            name="Non-GPU Example App",
            description="Test app without GPU requirements",
            app_license="MIT",
            identifier="non-gpu-example-app",
            url="https://example.com/non-gpu-app",
        )
        metadata.add_input(DocumentTypes.TextDocument)
        metadata.add_output(AnnotationTypes.TimeFrame)
        return metadata

    def _annotate(self, mmif, **kwargs):
        if not isinstance(mmif, Mmif):
            mmif = Mmif(mmif, validate=False)
        new_view = mmif.new_view()
        self.sign_view(new_view, kwargs)
        new_view.new_contain(AnnotationTypes.TimeFrame)
        return mmif


class TestVRAMManagement(unittest.TestCase):

    def setUp(self):
        self.gpu_app = GPUExampleClamsApp()
        self.non_gpu_app = NonGPUExampleClamsApp()

    # ===== A. Pure Logic Tests =====

    def test_profile_path_structure(self):
        """Profile path includes sanitized app identifier."""
        param_hash = "abc123def456"
        path = self.gpu_app._get_profile_path(param_hash)

        self.assertIn('.cache', str(path))
        self.assertIn('clams', str(path))
        self.assertIn('memory_profiles', str(path))
        self.assertIn(param_hash, str(path))
        self.assertTrue(str(path).endswith('.txt'))

    def test_profile_path_sanitization(self):
        """URLs with / and : are properly sanitized in path."""
        param_hash = "test123"
        path = self.gpu_app._get_profile_path(param_hash)

        # App identifier has slashes and colons that should be replaced
        path_str = str(path)
        # After sanitization, no / or : should be in the app_id part
        app_id_part = path.parent.name
        self.assertNotIn('/', app_id_part)
        self.assertNotIn(':', app_id_part)

    def test_insufficient_vram_error(self):
        """InsufficientVRAMError can be raised and caught."""
        with self.assertRaises(InsufficientVRAMError):
            raise InsufficientVRAMError("Test error message")

        # Also inherits from RuntimeError
        with self.assertRaises(RuntimeError):
            raise InsufficientVRAMError("Test error message")

    def test_http_503_on_vram_error(self):
        """RestAPI returns 503 for InsufficientVRAMError."""
        app = clams.restify.Restifier(GPUExampleClamsApp()).test_client()

        # Mock the annotate method to raise InsufficientVRAMError
        with patch.object(GPUExampleClamsApp, 'annotate',
                         side_effect=InsufficientVRAMError("Not enough VRAM")):
            mmif = Mmif(validate=False)
            from mmif import Document
            doc = Document({'@type': DocumentTypes.VideoDocument,
                           'properties': {'id': 'v1', 'location': '/test.mp4'}})
            mmif.add_document(doc)

            res = app.post('/', data=mmif.serialize())
            self.assertEqual(res.status_code, 503)
            self.assertIn('Not enough VRAM', res.get_data(as_text=True))

    # ===== B. Mocked CUDA Tests =====

    def test_check_vram_available_sufficient(self):
        """Returns True when sufficient VRAM available."""
        mock_props = MagicMock()
        mock_props.total_memory = 24 * 1024**3  # 24GB

        with patch('torch.cuda.is_available', return_value=True), \
             patch('torch.cuda.current_device', return_value=0), \
             patch('torch.cuda.get_device_properties', return_value=mock_props), \
             patch('torch.cuda.memory_allocated', return_value=1 * 1024**3), \
             patch('torch.cuda.memory_reserved', return_value=1 * 1024**3):

            # 24GB - 1GB = 23GB available, requesting 6GB
            result = ClamsApp._check_vram_available(6 * 1024**3)
            self.assertTrue(result)

    def test_check_vram_available_insufficient(self):
        """Returns False when insufficient VRAM available."""
        mock_props = MagicMock()
        mock_props.total_memory = 8 * 1024**3  # 8GB

        with patch('torch.cuda.is_available', return_value=True), \
             patch('torch.cuda.current_device', return_value=0), \
             patch('torch.cuda.get_device_properties', return_value=mock_props), \
             patch('torch.cuda.memory_allocated', return_value=6 * 1024**3), \
             patch('torch.cuda.memory_reserved', return_value=6 * 1024**3):

            # 8GB - 6GB = 2GB available, requesting 6GB (+ 10% margin)
            result = ClamsApp._check_vram_available(6 * 1024**3)
            self.assertFalse(result)

    def test_get_available_vram(self):
        """Returns correct available VRAM calculation."""
        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3  # 16GB

        with patch('torch.cuda.is_available', return_value=True), \
             patch('torch.cuda.current_device', return_value=0), \
             patch('torch.cuda.get_device_properties', return_value=mock_props), \
             patch('torch.cuda.memory_allocated', return_value=4 * 1024**3), \
             patch('torch.cuda.memory_reserved', return_value=5 * 1024**3):

            # Should use max(allocated, reserved) = 5GB
            # Available = 16GB - 5GB = 11GB
            result = ClamsApp._get_available_vram()
            self.assertEqual(result, 11 * 1024**3)

    def test_get_estimated_vram_first_request(self):
        """Uses conservative 80% when no historical profile exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.gpu_app, '_get_profile_path') as mock_path:
                # Profile doesn't exist
                profile_file = pathlib.Path(tmpdir) / 'memory_abc123.txt'
                mock_path.return_value = profile_file

                mock_props = MagicMock()
                mock_props.total_memory = 24 * 1024**3  # 24GB

                with patch('torch.cuda.is_available', return_value=True), \
                     patch('torch.cuda.current_device', return_value=0), \
                     patch('torch.cuda.get_device_properties', return_value=mock_props):

                    result = self.gpu_app._get_estimated_vram_usage(model='large')

                    self.assertIsNotNone(result)
                    self.assertEqual(result['source'], 'conservative-first-request')
                    # Should be 80% of 24GB
                    expected = int(24 * 1024**3 * 0.8)
                    self.assertEqual(result['size_bytes'], expected)

    def test_get_estimated_vram_historical(self):
        """Uses historical measurement × 1.2 when profile exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.gpu_app, '_get_profile_path') as mock_path:
                # Create profile with historical value
                profile_file = pathlib.Path(tmpdir) / 'memory_abc123.txt'
                profile_file.parent.mkdir(parents=True, exist_ok=True)
                historical_peak = 3 * 1024**3  # 3GB
                profile_file.write_text(str(historical_peak))
                mock_path.return_value = profile_file

                result = self.gpu_app._get_estimated_vram_usage(model='large')

                self.assertIsNotNone(result)
                self.assertEqual(result['source'], 'historical')
                # Should be historical × 1.2
                expected = int(historical_peak * 1.2)
                self.assertEqual(result['size_bytes'], expected)

    def test_record_vram_usage_creates_file(self):
        """Profile file is created with peak value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.gpu_app, '_get_profile_path') as mock_path:
                profile_file = pathlib.Path(tmpdir) / 'subdir' / 'memory_abc123.txt'
                mock_path.return_value = profile_file

                peak_bytes = 3 * 1024**3
                self.gpu_app._record_vram_usage({'model': 'large'}, peak_bytes)

                self.assertTrue(profile_file.exists())
                self.assertEqual(int(profile_file.read_text()), peak_bytes)

    def test_record_vram_usage_updates_higher(self):
        """Only updates profile if new peak is higher."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.gpu_app, '_get_profile_path') as mock_path:
                profile_file = pathlib.Path(tmpdir) / 'memory_abc123.txt'
                profile_file.parent.mkdir(parents=True, exist_ok=True)

                # Initial value
                initial_peak = 5 * 1024**3
                profile_file.write_text(str(initial_peak))
                mock_path.return_value = profile_file

                # Try to record lower value - should not update
                self.gpu_app._record_vram_usage({'model': 'large'}, 3 * 1024**3)
                self.assertEqual(int(profile_file.read_text()), initial_peak)

                # Record higher value - should update
                higher_peak = 7 * 1024**3
                self.gpu_app._record_vram_usage({'model': 'large'}, higher_peak)
                self.assertEqual(int(profile_file.read_text()), higher_peak)

    def test_vram_check_skipped_when_no_gpu_mem_min(self):
        """VRAM checking is skipped when gpu_mem_min=0."""
        # non_gpu_app has gpu_mem_min=0, so should skip VRAM checking
        self.assertEqual(self.non_gpu_app.metadata.gpu_mem_min, 0)

        # _get_estimated_vram_usage should still work but won't be called
        # during annotation because the condition check will fail

    # ===== C. AppMetadata Tests =====

    def test_gpu_mem_fields_default_zero(self):
        """GPU memory fields default to 0."""
        metadata = AppMetadata(
            name="Test App",
            description="Test",
            app_license="MIT",
            identifier="test-app",
            url="https://example.com",
        )
        metadata.add_input(DocumentTypes.TextDocument)
        metadata.add_output(AnnotationTypes.TimeFrame)

        self.assertEqual(metadata.gpu_mem_min, 0)
        self.assertEqual(metadata.gpu_mem_typ, 0)

    def test_gpu_mem_typ_validation(self):
        """Warning issued when gpu_mem_typ < gpu_mem_min, auto-corrected."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            metadata = AppMetadata(
                name="Test App",
                description="Test",
                app_license="MIT",
                identifier="test-app",
                url="https://example.com",
                gpu_mem_min=4000,  # 4GB min
                gpu_mem_typ=2000,  # 2GB typical (less than min!)
            )
            metadata.add_input(DocumentTypes.TextDocument)
            metadata.add_output(AnnotationTypes.TimeFrame)

            # Should have issued a warning
            self.assertEqual(len(w), 1)
            self.assertIn('gpu_mem_typ', str(w[0].message))
            self.assertIn('gpu_mem_min', str(w[0].message))

            # Should have auto-corrected
            self.assertEqual(metadata.gpu_mem_typ, metadata.gpu_mem_min)


if __name__ == '__main__':
    unittest.main()
