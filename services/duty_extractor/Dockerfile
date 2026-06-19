FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    google-cloud-storage \
    google-cloud-bigquery

COPY extract_duties.py .

CMD ["python", "extract_duties.py"]