#!/bin/bash

echo "🔍 Диагностика MongoDB на Fedora..."
echo "=================================================="

echo "📦 Проверяем установленные пакеты MongoDB..."
sudo dnf list installed | grep -i mongo

echo ""
echo "🔧 Проверяем доступные сервисы..."
sudo systemctl list-unit-files | grep -i mongo

echo ""
echo "📁 Проверяем файлы конфигурации..."
ls -la /etc/mongod* 2>/dev/null || echo "Файлы конфигурации не найдены"

echo ""
echo "📁 Проверяем исполняемые файлы..."
which mongod 2>/dev/null || echo "mongod не найден"
which mongo 2>/dev/null || echo "mongo не найден"

echo ""
echo "💡 Рекомендации:"
echo "1. Если MongoDB не установлена: sudo dnf install mongodb-org"
echo "2. Если установлена, но не запущена: sudo systemctl start mongod"
echo "3. Проверьте статус: sudo systemctl status mongod" 