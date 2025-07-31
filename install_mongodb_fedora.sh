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
# На Fedora сервис может называться по-разному
if sudo systemctl list-unit-files | grep -q mongod; then
    sudo systemctl start mongod
    sudo systemctl enable mongod
elif sudo systemctl list-unit-files | grep -q mongodb; then
    sudo systemctl start mongodb
    sudo systemctl enable mongodb
else
    echo "❌ Сервис MongoDB не найден"
    echo "💡 Проверьте установку: sudo dnf list installed | grep mongodb"
    exit 1
fi

echo "⏳ Ждем запуска MongoDB..."
sleep 5

echo "🔍 Проверяем статус MongoDB..."
if sudo systemctl is-active --quiet mongod 2>/dev/null || sudo systemctl is-active --quiet mongodb 2>/dev/null; then
    echo "✅ MongoDB запущена"
else
    echo "❌ MongoDB не запущена"
    echo "💡 Проверьте статус:"
    echo "   sudo systemctl status mongod"
    echo "   sudo systemctl status mongodb"
    echo "   sudo dnf list installed | grep mongodb"
    exit 1
fi

echo ""
echo "🎉 Установка MongoDB на Fedora завершена!" 