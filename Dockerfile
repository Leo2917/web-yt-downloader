# Usamos Python 3.11
FROM python:3.11-slim

# Instalamos FFmpeg (esto es lo que permite convertir a MP3)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalamos las librerías de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos tu código
COPY . .

# Comando para arrancar la web
EXPOSE 8000
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:8000"]
