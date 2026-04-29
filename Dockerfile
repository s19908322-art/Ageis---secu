FROM python:3.11-slim

# ffmpeg pour la lecture audio + ca-certificates pour HTTPS
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# IMPORTANT : on force la dernière version de yt-dlp à chaque build
# (YouTube change son API très souvent, c'est obligatoire en 2026)
RUN pip install --no-cache-dir -U "yt-dlp>=2025.10.26"

COPY bot.py .

# Volume pour les données persistantes (Railway → mount sur /data)
VOLUME ["/data"]

CMD ["python", "-u", "bot.py"]
