# Judge-facing dashboard. Read-only: it serves committed evidence and holds no
# credentials. The decision path and the execution gateway are not started here.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# Remove the build tree after installing: it is a by-product, and shipping it
# puts a second copy of the source in the image.
RUN pip install --no-cache-dir uv \
 && uv pip install --system --no-cache . \
 && rm -rf build *.egg-info

COPY app.py ./
COPY demo ./demo
COPY artifacts ./artifacts
COPY .streamlit ./.streamlit

# No ALPACA or OPENAI credential is baked in or required: this image cannot
# reach a broker or a model provider.
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
