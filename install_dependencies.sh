#!/bin/bash

echo "🔧 Установка зависимостей для обхода блокировки Selenium..."
echo "=================================================="

# Проверяем, активирована ли виртуальная среда
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Виртуальная среда не активирована"
    echo "💡 Рекомендуется активировать виртуальную среду:"
    echo "   source venv/bin/activate"
    echo ""
fi

# Устанавливаем Python зависимости
echo "📦 Установка Python пакетов..."

# Основные пакеты для обхода блокировки
pip install undetected-chromedriver
pip install fake-useragent
pip install selenium-stealth

# Дополнительные полезные пакеты
pip install requests
pip install beautifulsoup4
pip install lxml

echo "✅ Python пакеты установлены"

# Проверяем наличие Chrome
echo ""
echo "🔍 Проверка Chrome браузера..."

if command -v google-chrome &> /dev/null; then
    echo "✅ Google Chrome найден"
elif command -v chromium-browser &> /dev/null; then
    echo "✅ Chromium найден"
elif command -v chrome &> /dev/null; then
    echo "✅ Chrome найден"
else
    echo "❌ Chrome не найден"
    echo "💡 Установите Chrome:"
    echo "   macOS: brew install --cask google-chrome"
    echo "   Ubuntu: sudo apt install google-chrome-stable"
    echo "   или скачайте с https://www.google.com/chrome/"
fi

# Проверяем наличие chromedriver
echo ""
echo "🔍 Проверка chromedriver..."

if command -v chromedriver &> /dev/null; then
    echo "✅ chromedriver найден в PATH"
    chromedriver --version
else
    echo "⚠️  chromedriver не найден в PATH"
    echo "💡 Установка chromedriver:"
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "   macOS: brew install chromedriver"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "   Linux: sudo apt install chromium-chromedriver"
    else
        echo "   Скачайте с https://chromedriver.chromium.org/"
    fi
fi

echo ""
echo "🎉 Установка завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Убедитесь, что Chrome установлен"
echo "2. Установите chromedriver (если не установлен)"
echo "3. Протестируйте парсер:"
echo "   python test_advanced_parser.py single"
echo ""
echo "🔧 Доступные парсеры:"
echo "- selenium_parser.py - базовый парсер"
echo "- improved_selenium_parser.py - улучшенный парсер"
echo "- advanced_selenium_parser.py - продвинутый парсер (рекомендуется)" 