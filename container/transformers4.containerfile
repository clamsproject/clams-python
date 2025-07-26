ARG clams_version
FROM ghcr.io/clamsproject/clams-python:$clams_version
LABEL org.opencontainers.image.description="clams-python-transformers4 image is shipped with clams-python and HF's transformers4"

RUN pip install --no-cache-dir transformers==4.*
