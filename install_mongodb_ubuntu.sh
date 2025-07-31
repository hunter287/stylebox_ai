#!/bin/bash

echo "🔧 Установка MongoDB на Ubuntu..."
echo "=================================================="

# Проверяем, что это Ubuntu
if ! command -v apt-get &> /dev/null; then
    echo "❌ Это не Ubuntu/Debian система"
    exit 1
fi

echo "📦 Обновляем пакеты..."
sudo apt-get update

echo "📦 Устанавливаем зависимости..."
sudo apt-get install -y wget gnupg

echo "📦 Добавляем ключ MongoDB..."
wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -

echo "📦 Добавляем репозиторий MongoDB..."
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list

echo "📦 Обновляем пакеты..."
sudo apt-get update

echo "📦 Устанавливаем MongoDB..."
sudo apt-get install -y mongodb-org

echo "🚀 Запускаем MongoDB..."
sudo systemctl start mongod
sudo systemctl enable mongod

echo "⏳ Ждем запуска MongoDB..."
sleep 5

echo "🔍 Проверяем статус MongoDB..."
if sudo systemctl is-active --quiet mongod; then
    echo "✅ MongoDB запущена"
else
    echo "❌ MongoDB не запущена"
    echo "💡 Проверьте статус: sudo systemctl status mongod"
    exit 1
fi

echo ""
echo "🎉 Установка MongoDB на Ubuntu завершена!" 