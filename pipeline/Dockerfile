FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    google-cloud-storage \
    google-cloud-bigquery

COPY gcs_to_bronze.py .

CMD ["python", "gcs_to_bronze.py"]