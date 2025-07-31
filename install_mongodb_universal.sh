#!/bin/bash

echo "🔧 Универсальная установка MongoDB..."
echo "=================================================="

# Определяем операционную систему
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    if command -v apt-get &> /dev/null; then
        echo "📦 Ubuntu/Debian система - устанавливаем через apt..."
        wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -
        echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list
        sudo apt-get update
        sudo apt-get install -y mongodb-org
    elif command -v yum &> /dev/null; then
        echo "📦 CentOS/RHEL система - устанавливаем через yum..."
        sudo yum install -y mongodb-org
    elif command -v dnf &> /dev/null; then
        echo "📦 Fedora система - устанавливаем через dnf..."
        sudo dnf install -y mongodb-org
    else
        echo "❌ Неизвестная Linux система"
        echo "💡 Установите MongoDB вручную: https://docs.mongodb.com/manual/installation/"
        exit 1
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    echo "📦 macOS система - устанавливаем через Homebrew..."
    if command -v brew &> /dev/null; then
        brew tap mongodb/brew
        brew install mongodb-community
    else
        echo "❌ Homebrew не установлен"
        echo "💡 Установите Homebrew: https://brew.sh/"
        exit 1
    fi
else
    echo "❌ Неподдерживаемая система: $OSTYPE"
    echo "💡 Установите MongoDB вручную: https://docs.mongodb.com/manual/installation/"
    exit 1
fi

# Запускаем MongoDB
echo "🚀 Запускаем MongoDB..."

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    sudo systemctl start mongod
    sudo systemctl enable mongod
elif [[ "$OSTYPE" == "darwin"* ]]; then
    brew services start mongodb-community
fi

# Ждем запуска
echo "⏳ Ждем запуска MongoDB..."
sleep 5

# Проверяем статус
echo "🔍 Проверяем статус MongoDB..."
if command -v mongod &> /dev/null; then
    echo "✅ MongoDB установлена"
    
    # Проверяем подключение
    if mongo --eval "db.adminCommand('ping')" &> /dev/null; then
        echo "✅ MongoDB запущена и отвечает"
    else
        echo "⚠️  MongoDB установлена, но не отвечает"
        echo "💡 Проверьте статус:"
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            echo "   sudo systemctl status mongod"
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            echo "   brew services list | grep mongodb"
        fi
    fi
else
    echo "❌ MongoDB не установлена"
fi

echo ""
echo "🎉 Установка MongoDB завершена!" 