ARG clams_version
FROM ghcr.io/clamsproject/clams-python-hf5:$clams_version
LABEL org.opencontainers.image.description="clams-python-hf image is an alias for clams-python-hf5 (latest HuggingFace/transformers)"
