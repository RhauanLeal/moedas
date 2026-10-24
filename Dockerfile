FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput -v0 \
 && chmod +x entrypoint.sh \
 && useradd --create-home --uid 1000 app \
 && chown -R app:app /app
USER app

EXPOSE 8000

# Saúde do container (aparece no Beszel / docker ps). A imagem slim não tem curl.
# start-period folgado: o entrypoint aplica migrações e carrega o catálogo antes do gunicorn.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/saude/', timeout=4).status == 200 else 1)"
ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
