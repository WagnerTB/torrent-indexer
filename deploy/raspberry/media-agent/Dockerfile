FROM python:3.12-alpine

RUN apk add --no-cache ffmpeg

WORKDIR /app

COPY media_agent.py system_status.py /app/

CMD ["python3", "/app/media_agent.py"]
