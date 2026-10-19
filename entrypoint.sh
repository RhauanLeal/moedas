#!/bin/sh
set -e

echo ">> Aplicando migrações..."
python manage.py migrate --noinput

echo ">> Conferindo catálogo de moedas..."
python manage.py carregar_catalogo

echo ">> Ligando as fotos às moedas..."
python manage.py carregar_fotos

# Cria o usuário de login na primeira subida (se ainda não existir).
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py createsuperuser --noinput \
    --username "$DJANGO_SUPERUSER_USERNAME" \
    --email "${DJANGO_SUPERUSER_EMAIL:-admin@localhost}" 2>/dev/null \
    && echo ">> Usuário $DJANGO_SUPERUSER_USERNAME criado." \
    || echo ">> Usuário $DJANGO_SUPERUSER_USERNAME já existe."
fi

exec "$@"
