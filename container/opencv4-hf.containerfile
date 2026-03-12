ARG clams_version
FROM ghcr.io/clamsproject/clams-python-opencv4-hf5:$clams_version
LABEL org.opencontainers.image.description="clams-python-opencv4-hf image is an alias for clams-python-opencv4-hf5 (latest HuggingFace/transformers)"
