FROM pytorch/pytorch:2.10.0-cuda13.0-cudnn9-runtime@sha256:1f57418aedd9a4d0d3a59646619e1d4f82cacc33817247cead4f749e1f452d4b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLEOCR_VL_HOST=0.0.0.0 \
    PADDLEOCR_VL_PORT=8093

RUN pip install --no-cache-dir \
      transformers==4.57.6 \
      pillow==11.1.0 \
      protobuf==4.25.8

COPY server.py /opt/paddleocr-vl/server.py
WORKDIR /opt/paddleocr-vl
EXPOSE 8093
HEALTHCHECK --interval=30s --timeout=10s --retries=10 --start-period=180s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8093/health')"
CMD ["python", "/opt/paddleocr-vl/server.py"]
