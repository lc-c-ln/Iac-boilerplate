FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY pyproject.toml .
COPY forge ./forge
RUN pip install . && useradd -r -u 10001 forge
COPY specs ./specs
USER forge
ENV SPECS_DIR=/srv/specs
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request as u;u.urlopen('http://localhost:8000/healthz')"
CMD ["uvicorn", "forge.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
