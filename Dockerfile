FROM python:3.12-slim

# CPU-only torch keeps the image a few hundred MB instead of the multi-GB CUDA wheel.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e ".[full]"

ENV LAYA_PRELOAD=1 \
    LAYA_DEVICE=cpu \
    HF_HOME=/app/.cache/huggingface

EXPOSE 8000
CMD ["laya-service", "--host", "0.0.0.0", "--port", "8000"]