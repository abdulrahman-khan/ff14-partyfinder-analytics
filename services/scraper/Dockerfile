FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    requests \
    beautifulsoup4 \
    google-cloud-storage \
    google-cloud-secret-manager

COPY main.py .

CMD ["python", "main.py"]