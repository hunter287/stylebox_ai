#!/usr/bin/env python3
"""
Скрипт для настройки продакшен базы данных
"""

import os
import subprocess
import sys
from datetime import datetime

def check_docker_containers():
    """Проверяет статус Docker контейнеров"""
    print("=== Проверка Docker контейнеров ===")
    
    try:
        # Проверяем контейнеры MongoDB
        result = subprocess.run(['docker', 'ps', '|', 'grep', 'mongo'], 
                              shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ MongoDB контейнеры запущены:")
            print(result.stdout)
        else:
            print("❌ MongoDB контейнеры не найдены")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки контейнеров: {e}")
        return False

def setup_production_container():
    """Настраивает контейнер для продакшен MongoDB"""
    print("\n=== Настройка продакшен MongoDB контейнера ===")
    
    try:
        # Проверяем, существует ли контейнер
        result = subprocess.run(['docker', 'ps', '-a', '|', 'grep', 'mongodb_prod'], 
                              shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Контейнер mongodb_prod уже существует")
            
            # Проверяем, запущен ли он
            result = subprocess.run(['docker', 'ps', '|', 'grep', 'mongodb_prod'], 
                                  shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Контейнер mongodb_prod запущен")
                return True
            else:
                print("🔄 Запускаем контейнер mongodb_prod...")
                subprocess.run(['docker', 'start', 'mongodb_prod'], check=True)
                print("✅ Контейнер mongodb_prod запущен")
                return True
        else:
            print("🔄 Создаем контейнер mongodb_prod...")
            
            # Создаем директорию для данных
            subprocess.run(['sudo', 'mkdir', '-p', '/var/lib/mongodb_prod_data'], check=True)
            subprocess.run(['sudo', 'chown', '999:999', '/var/lib/mongodb_prod_data'], check=True)
            
            # Создаем контейнер
            cmd = [
                'docker', 'run', '-d',
                '--name', 'mongodb_prod',
                '-v', '/var/lib/mongodb_prod_data:/data/db',
                '-p', '27018:27017',
                '--restart', 'unless-stopped',
                'mongo:6.0'
            ]
            
            subprocess.run(cmd, check=True)
            print("✅ Контейнер mongodb_prod создан и запущен")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка настройки контейнера: {e}")
        return False

def setup_environment_variables():
    """Настраивает переменные окружения для продакшена"""
    print("\n=== Настройка переменных окружения ===")
    
    try:
        # Проверяем существование .env файла
        if not os.path.exists('.env'):
            print("📝 Создаем файл .env...")
            with open('.env', 'w') as f:
                f.write("# MongoDB Configuration\n")
                f.write("MONGO_URI=mongodb://localhost:27018/\n")
                f.write("MONGO_DB_NAME=stylist_ai_prod\n")
        else:
            print("📝 Обновляем файл .env...")
            # Читаем существующий файл
            with open('.env', 'r') as f:
                lines = f.readlines()
            
            # Обновляем или добавляем переменные
            mongo_uri_found = False
            mongo_db_found = False
            
            for i, line in enumerate(lines):
                if line.startswith('MONGO_URI='):
                    lines[i] = 'MONGO_URI=mongodb://localhost:27018/\n'
                    mongo_uri_found = True
                elif line.startswith('MONGO_DB_NAME='):
                    lines[i] = 'MONGO_DB_NAME=stylist_ai_prod\n'
                    mongo_db_found = True
            
            if not mongo_uri_found:
                lines.append('MONGO_URI=mongodb://localhost:27018/\n')
            if not mongo_db_found:
                lines.append('MONGO_DB_NAME=stylist_ai_prod\n')
            
            # Записываем обновленный файл
            with open('.env', 'w') as f:
                f.writelines(lines)
        
        print("✅ Переменные окружения настроены")
        print("   MONGO_URI=mongodb://localhost:27018/")
        print("   MONGO_DB_NAME=stylist_ai_prod")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка настройки переменных окружения: {e}")
        return False

def restart_application():
    """Перезапускает приложение"""
    print("\n=== Перезапуск приложения ===")
    
    try:
        # Останавливаем приложение
        subprocess.run(['sudo', 'systemctl', 'stop', 'stylist_ai'], check=True)
        print("✅ Приложение остановлено")
        
        # Запускаем приложение
        subprocess.run(['sudo', 'systemctl', 'start', 'stylist_ai'], check=True)
        print("✅ Приложение запущено")
        
        # Проверяем статус
        result = subprocess.run(['sudo', 'systemctl', 'status', 'stylist_ai'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Приложение работает корректно")
        else:
            print("⚠️  Приложение запущено, но есть предупреждения")
            print(result.stdout)
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка перезапуска приложения: {e}")
        return False

def verify_setup():
    """Проверяет настройку"""
    print("\n=== Проверка настройки ===")
    
    try:
        # Проверяем переменные окружения
        from dotenv import load_dotenv
        load_dotenv()
        
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        db_name = os.getenv('MONGO_DB_NAME', 'stylist_ai')
        
        print(f"MONGO_URI: {mongo_uri}")
        print(f"MONGO_DB_NAME: {db_name}")
        
        if mongo_uri == 'mongodb://localhost:27018/' and db_name == 'stylist_ai_prod':
            print("✅ Переменные окружения настроены правильно")
        else:
            print("❌ Переменные окружения настроены неправильно")
            return False
        
        # Проверяем подключение к продакшен базе
        from pymongo import MongoClient
        client = MongoClient('mongodb://localhost:27018/')
        db = client.stylist_ai_prod
        
        # Проверяем подключение
        client.admin.command('ping')
        print("✅ Подключение к продакшен базе успешно")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return False

def main():
    """Главная функция"""
    print("🚀 Настройка продакшен базы данных")
    print("=" * 50)
    
    # Проверяем контейнеры
    if not check_docker_containers():
        print("❌ Проблема с Docker контейнерами")
        return False
    
    # Настраиваем продакшен контейнер
    if not setup_production_container():
        print("❌ Не удалось настроить продакшен контейнер")
        return False
    
    # Настраиваем переменные окружения
    if not setup_environment_variables():
        print("❌ Не удалось настроить переменные окружения")
        return False
    
    # Перезапускаем приложение
    if not restart_application():
        print("❌ Не удалось перезапустить приложение")
        return False
    
    # Проверяем настройку
    if not verify_setup():
        print("❌ Настройка не прошла проверку")
        return False
    
    print("\n" + "=" * 50)
    print("✅ НАСТРОЙКА ЗАВЕРШЕНА УСПЕШНО!")
    print("📋 Приложение теперь использует продакшен базу данных")
    print("🌐 Порт: 27018")
    print("🗄️  База: stylist_ai_prod")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1) 