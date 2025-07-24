ARG clams_version
FROM ghcr.io/clamsproject/clams-python-opencv4:$clams_version
LABEL org.opencontainers.image.description="clams-python-opencv4-transformers4 image is shipped with clams-python, ffmpeg, opencv4, and HF's transformers4"

RUN pip install --no-cache-dir transformers==4.*
