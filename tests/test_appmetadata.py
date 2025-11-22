import unittest
from pydantic import ValidationError
from clams.appmetadata import AppMetadata

class TestAppMetadata(unittest.TestCase):
    def test_analyzer_version_simple(self):
        # valid cases
        valid_versions = [
            "1.0.0",
            "v1.2",
            "hf-250619", # Should be allowed as simple string without validation
            None
        ]

        for v in valid_versions:
            try:
                AppMetadata(
                    name="test",
                    description="test",
                    app_license="MIT",
                    identifier="http://test",
                    url="http://test",
                    analyzer_version=v
                )
            except ValidationError as e:
                self.fail(f"Valid version '{v}' failed validation: {e}")

    def test_analyzer_versions_map(self):
        # test analyzer_versions field

        # case 1: simple valid map
        versions_map = {
            "model1": "1.0.0",
            "model2": "commit-hash-123"
        }

        m = AppMetadata(
            name="test",
            description="test",
            app_license="MIT",
            identifier="http://test",
            url="http://test",
            analyzer_versions=versions_map
        )
        self.assertEqual(m.analyzer_versions, versions_map)

        # case 2: mixed with singular analyzer_version (technically allowed by pydantic, logic separation is up to user)
        m2 = AppMetadata(
            name="test",
            description="test",
            app_license="MIT",
            identifier="http://test",
            url="http://test",
            analyzer_version="1.0",
            analyzer_versions=versions_map
        )
        self.assertEqual(m2.analyzer_versions, versions_map)
        self.assertEqual(m2.analyzer_version, "1.0")

    def test_analyzer_versions_invalid(self):
        # invalid type for analyzer_versions
        invalid_map = "not a map"

        with self.assertRaises(ValidationError):
            AppMetadata(
                name="test",
                description="test",
                app_license="MIT",
                identifier="http://test",
                url="http://test",
                analyzer_versions=invalid_map
            )

    def test_analyzer_versions_invalid_values(self):
        # invalid values in map (must be strings)
        invalid_map = {
            "model1": 1.0  # int, might be coerced to string by pydantic? let's see. Pydantic usually coerces.
        }
        # If pydantic coerces, this might pass. Let's check strictness if needed.
        # The field is Dict[str, str]. Pydantic v2 usually coerces unless configured otherwise.

        # Let's test checking list as value, which should fail for Dict[str, str]
        invalid_map_list = {
            "model1": ["1.0"]
        }
        with self.assertRaises(ValidationError):
            AppMetadata(
                name="test",
                description="test",
                app_license="MIT",
                identifier="http://test",
                url="http://test",
                analyzer_versions=invalid_map_list
            )

if __name__ == '__main__':
    unittest.main()
