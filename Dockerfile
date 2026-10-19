FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema mínimas para PyMuPDF (no requiere librerías extra
# en python:slim, pero mantenemos build-essential fuera para una imagen
# ligera; se añade aquí solo si en el futuro se activa OCR con tesseract-ocr).
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data/demo ./data/demo

RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
