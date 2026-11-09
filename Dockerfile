# The pricing API in a small, non-root image. It serves the frozen price table (site/prices.js) and reports the
# SHA-256 of the frozen model files, so a running container can be checked against VALIDATION.md.
#   docker build -t mcp-api .
#   docker run --rm -p 8000:8000 --read-only --tmpfs /tmp mcp-api        # then http://127.0.0.1:8000/docs
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/src
WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt \
 && useradd --system --uid 10001 --no-create-home api

# only what serving needs: the serving code, the price table and the frozen artefacts it reports hashes for
COPY src/mcp/__init__.py src/mcp/service.py src/mcp/service_gap.py src/mcp/api.py src/mcp/
COPY site/prices.js site/prices_v3.js site/
COPY models/pmiss.joblib models/pmiss_v2.joblib models/

USER api
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "mcp.api:app", "--host", "0.0.0.0", "--port", "8000"]
