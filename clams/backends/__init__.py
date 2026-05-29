"""
Optional model-backend helpers for CLAMS apps.

Each backend is a separate submodule. Heavy dependencies (e.g.,
``torch``, ``transformers``) are NOT pulled in by the base
``clams-python`` install; users opt in via pip extras such as
``pip install clams-python[hf]`` for the HuggingFace transformers
backend.
"""
