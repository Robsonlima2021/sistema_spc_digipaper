#!/bin/bash
# Script de Instalação Automatizada - Sistema Inadimplência
# Para Servidores Ubuntu/Debian Linux

set -e

echo "============================================================"
echo "Instalador do Sistema de Consulta SQL de Inadimplência"
echo "============================================================"

# Verifica se está rodando como root
if [ "$EUID" -ne 0 ]; then
  echo "Por favor, rode este script como root (sudo bash install.sh)"
  exit 1
fi

APP_DIR=$(pwd)
APP_USER=$(logname || echo $USER)

if [ "$APP_USER" = "root" ] && [ -n "$SUDO_USER" ]; then
    APP_USER=$SUDO_USER
fi

echo "Diretório da Aplicação: $APP_DIR"
echo "Usuário do Serviço: $APP_USER"

echo ""
echo "[1/5] Atualizando o sistema e instalando dependências básicas (Python3 e venv)..."
apt-get update -y
apt-get install -y python3 python3-pip python3-venv

echo ""
echo "[2/5] Criando o Ambiente Virtual Python (venv)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo ""
echo "[3/5] Instalando dependências do Python (Flask e Gunicorn)..."
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo ""
echo "[4/5] Processando os dados (Criando o banco SQLite)..."
if [ -f "build_db.py" ] && [ -f "Relatorio_Contas_Aberto.txt" ]; then
    venv/bin/python build_db.py
else
    echo "Aviso: Arquivos base (build_db.py ou Relatorio_Contas_Aberto.txt) não encontrados no diretório atual."
fi

echo ""
echo "[5/5] Configurando o serviço de inicialização automática (systemd)..."

SERVICE_FILE="/etc/systemd/system/inadimplencia.service"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Gunicorn instance to serve Sistema de Inadimplencia
After=network.target

[Service]
User=$APP_USER
Group=www-data
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Recarrega o systemd, habilita e inicia o serviço
systemctl daemon-reload
systemctl enable inadimplencia
systemctl restart inadimplencia

echo "============================================================"
echo "Instalação concluída com sucesso!"
echo "O sistema está rodando em segundo plano na porta 5000."
echo "Para acessar, abra no navegador: http://<IP_DO_SERVIDOR>:5000"
echo "============================================================"
echo "Comandos úteis:"
echo "- Status do serviço: sudo systemctl status inadimplencia"
echo "- Parar serviço:     sudo systemctl stop inadimplencia"
echo "- Reiniciar serviço: sudo systemctl restart inadimplencia"
echo "============================================================"
