#!/bin/bash

echo "🔧 Установка MongoDB на Fedora..."
echo "=================================================="

# Проверяем, что это Fedora
if ! command -v dnf &> /dev/null; then
    echo "❌ Это не Fedora система"
    exit 1
fi

echo "📦 Обновляем пакеты..."
sudo dnf update -y

echo "📦 Устанавливаем MongoDB..."
sudo dnf install -y mongodb-org

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
echo "🎉 Установка MongoDB на Fedora завершена!" 