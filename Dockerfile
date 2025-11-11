FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    espeak-ng \
    libespeak1 \
    espeak-data \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["bash", "run.sh"]
