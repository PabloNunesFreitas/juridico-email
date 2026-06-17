#!/bin/bash
# Script de instalação do servidor Hetzner
# Roda UMA VEZ como root após criar o servidor
# Uso: bash setup-server.sh

set -e

echo "======================================"
echo "  Instalando servidor juridico-email  "
echo "======================================"

# Atualiza o sistema
apt-get update -y && apt-get upgrade -y

# Instala dependências
apt-get install -y curl git ufw

# Instala Docker
curl -fsSL https://get.docker.com | bash

# Instala Docker Compose
apt-get install -y docker-compose-plugin

# Configura firewall
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8000/tcp
ufw --force enable

# Cria usuário deploy (mais seguro que root)
if ! id "deploy" &>/dev/null; then
  useradd -m -s /bin/bash deploy
  usermod -aG docker deploy
  mkdir -p /home/deploy/.ssh
  cp /root/.ssh/authorized_keys /home/deploy/.ssh/ 2>/dev/null || true
  chown -R deploy:deploy /home/deploy/.ssh
fi

# Cria pasta do projeto
mkdir -p /opt/juridico-email
chown deploy:deploy /opt/juridico-email

echo ""
echo "======================================"
echo "  Instalação concluída!"
echo "  Próximo passo: copiar os arquivos"
echo "======================================"
