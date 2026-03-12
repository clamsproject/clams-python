ARG clams_version
FROM ghcr.io/clamsproject/clams-python-torch2:$clams_version
LABEL org.opencontainers.image.description="clams-python-hf4 image is shipped with clams-python and HuggingFace libraries with transformers 4.x (PyTorch backend)"

RUN pip install --no-cache-dir transformers[torch,tokenizers]==4.*
RUN pip install --no-cache-dir datasets
