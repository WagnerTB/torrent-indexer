FROM python:3.12-alpine

WORKDIR /app

COPY admin_agent.py /app/

# Roda como UID/GID do dono dos arquivos no host (PUID/PGID no compose).
USER 1000:1000

EXPOSE 8093

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8093/health', timeout=3)"

CMD ["python3", "/app/admin_agent.py"]
