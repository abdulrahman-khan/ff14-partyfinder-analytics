FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gcs_to_bronze.py .

CMD ["python", "gcs_to_bronze.py"]