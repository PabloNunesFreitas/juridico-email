#!/bin/bash
# Script de deploy — roda no servidor a cada atualização
# Uso: bash deploy.sh

set -e

cd /opt/juridico-email

echo "Baixando última versão do GitHub..."
git pull origin main

echo "Rebuilding e subindo containers..."
docker compose -f docker-compose.prod.yml --env-file .env.prod pull 2>/dev/null || true
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

echo "Limpando imagens antigas..."
docker image prune -f

echo ""
echo "Deploy concluído! Backend rodando em :8000"
