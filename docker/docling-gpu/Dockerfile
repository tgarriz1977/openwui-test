FROM ghcr.io/docling-project/docling-serve-cu126:main

USER 0

# 1. repositorio + runtime CUDA/cuDNN
RUN dnf config-manager --add-repo \
      https://developer.download.nvidia.com/compute/cuda/repos/rhel9/x86_64/cuda-rhel9.repo && \
    dnf install -y --allowerasing \
        cuda-toolkit-12-6 \
        cudnn9-cuda-12 && \
    dnf clean all && \
    ldconfig

# 2. quitar la wheel de CPU e instalar la GPU
RUN pip uninstall -y onnxruntime && \
    pip install --no-cache-dir onnxruntime-gpu

USER 1001
