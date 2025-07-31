#!/bin/bash

echo "🔧 Восстановление MongoDB на staging сервере..."
echo "=================================================="

# Проверяем наличие бэкапа
if [ ! -d "mongo_backup" ]; then
    echo "❌ Папка mongo_backup не найдена"
    echo "💡 Сначала создайте бэкап: mongodump --db stylist_ai --out ./mongo_backup"
    exit 1
fi

# Устанавливаем MongoDB если её нет
if ! command -v mongod &> /dev/null; then
    echo "📦 Устанавливаем MongoDB..."
    chmod +x install_mongodb_universal.sh
    ./install_mongodb_universal.sh
fi

# Запускаем MongoDB
echo "🚀 Запускаем MongoDB..."
sudo systemctl start mongod
sudo systemctl enable mongod

# Ждем запуска MongoDB
echo "⏳ Ждем запуска MongoDB..."
sleep 5

# Восстанавливаем данные
echo "📊 Восстанавливаем данные из бэкапа..."
mongorestore --db stylist_ai mongo_backup/stylist_ai/

echo ""
echo "✅ Восстановление завершено!"
echo ""
echo "📋 Проверка:"
echo "1. Статус MongoDB: sudo systemctl status mongod"
echo "2. Подключение: mongo stylist_ai"
echo "3. Проверка данных: db.products.count()"
echo "4. Проверка enhanced: db.products_enhanced.count()" 