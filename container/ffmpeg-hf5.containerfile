ARG clams_version
FROM ghcr.io/clamsproject/clams-python-ffmpeg-torch2:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg-hf5 image is shipped with clams-python, ffmpeg, and HuggingFace libraries with transformers 5.x (PyTorch backend)"

RUN pip install --no-cache-dir transformers[torch,tokenizers]==5.*
RUN pip install --no-cache-dir datasets
