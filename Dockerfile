FROM python:3.12-slim

WORKDIR /app

# LibreOffice converts Office documents (.pptx/.docx/.xlsx) to PDF so the
# measured PDF pipeline — page renders, table detection, crops, citations —
# applies to them unchanged (see tablerag/ingestion/convert.py). The fonts are
# not optional: without them a converted deck renders in fallback glyphs and its
# text layer degrades, which is exactly what table parsing reads.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-impress \
        libreoffice-writer \
        libreoffice-calc \
        fonts-liberation \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY tablerag ./tablerag
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "tablerag.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
