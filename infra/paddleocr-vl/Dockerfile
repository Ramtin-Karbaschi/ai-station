FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:paddleocr3.6-nvidia-gpu-sm120-offline@sha256:0971c409d1cab2b12aa17b76855e36ac8eb9fb1adc97dbeea15e9b09432a4a3b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLEOCR_VL_HOST=0.0.0.0 \
    PADDLEOCR_VL_PORT=8093 \
    PADDLEOCR_VL_PIPELINE_VERSION=v1.6 \
    PADDLEOCR_VL_MAX_BODY_BYTES=268435456 \
    PATH=/opt/station-ocr-venv/bin:${PATH}

# The official offline Blackwell image contains the complete PaddleOCR-VL
# pipeline (layout detector, reading order, element crops, and VLM), not only
# the recognizer weights. Tesseract is retained as an independent comparison
# engine and as the source of word-level confidence/box evidence.
USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      fonts-noto-core \
      fonts-dejavu \
      python3-venv \
      tesseract-ocr \
      tesseract-ocr-eng \
      tesseract-ocr-fas \
    && rm -rf /var/lib/apt/lists/*

# Keep repository additions out of the distribution-managed Python prefix.
# --system-site-packages reuses the fully pinned PaddleOCR runtime from the
# official image while PyMuPDF supplies deterministic PDF overlay/composition.
RUN python -m venv --system-site-packages /opt/station-ocr-venv \
    && /opt/station-ocr-venv/bin/python -m pip install --no-cache-dir \
      PyMuPDF==1.26.4

COPY server.py /opt/station-ocr/server.py
COPY ocr_quality.py /opt/station-ocr/ocr_quality.py
WORKDIR /opt/station-ocr
EXPOSE 8093
HEALTHCHECK --interval=30s --timeout=10s --retries=20 --start-period=300s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8093/health', timeout=5)"
CMD ["python", "/opt/station-ocr/server.py"]
