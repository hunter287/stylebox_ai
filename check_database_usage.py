#!/usr/bin/env python3
"""
Скрипт для проверки, какая база данных используется приложением
"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

# Загружаем переменные окружения
load_dotenv()

def check_staging_database():
    """Проверяет staging базу данных"""
    print("=== Staging база (mongodb://localhost:27017/stylist_ai) ===")
    try:
        client = MongoClient('mongodb://localhost:27017/')
        db = client.stylist_ai
        
        # Проверяем подключение
        client.admin.command('ping')
        
        # Получаем статистику
        users_count = db.users.count_documents({})
        products_count = db.products.count_documents({})
        sessions_count = db.sessions.count_documents({})
        pre_subscriptions_count = db.pre_subscriptions.count_documents({})
        
        print(f"✅ Подключение успешно")
        print(f"📊 Пользователей: {users_count}")
        print(f"📦 Товаров: {products_count}")
        print(f"🔑 Сессий: {sessions_count}")
        print(f"💳 Предварительных подписок: {pre_subscriptions_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False

def check_production_database():
    """Проверяет production базу данных"""
    print("\n=== Production база (mongodb://localhost:27018/stylist_ai_prod) ===")
    try:
        client = MongoClient('mongodb://localhost:27018/')
        db = client.stylist_ai_prod
        
        # Проверяем подключение
        client.admin.command('ping')
        
        # Получаем статистику
        users_count = db.users.count_documents({})
        products_count = db.products.count_documents({})
        sessions_count = db.sessions.count_documents({})
        pre_subscriptions_count = db.pre_subscriptions.count_documents({})
        
        print(f"✅ Подключение успешно")
        print(f"📊 Пользователей: {users_count}")
        print(f"📦 Товаров: {products_count}")
        print(f"🔑 Сессий: {sessions_count}")
        print(f"💳 Предварительных подписок: {pre_subscriptions_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False

def check_application_database():
    """Проверяет базу данных, которую использует приложение"""
    print("\n=== База данных приложения ===")
    
    # Получаем настройки приложения
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    db_name = os.getenv('MONGO_DB_NAME', 'stylist_ai')
    
    print(f"MONGO_URI: {mongo_uri}")
    print(f"MONGO_DB_NAME: {db_name}")
    
    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        # Проверяем подключение
        client.admin.command('ping')
        
        # Получаем статистику
        users_count = db.users.count_documents({})
        products_count = db.products.count_documents({})
        sessions_count = db.sessions.count_documents({})
        pre_subscriptions_count = db.pre_subscriptions.count_documents({})
        
        print(f"✅ Подключение успешно")
        print(f"📊 Пользователей: {users_count}")
        print(f"📦 Товаров: {products_count}")
        print(f"🔑 Сессий: {sessions_count}")
        print(f"💳 Предварительных подписок: {pre_subscriptions_count}")
        
        # Определяем тип базы
        port = client.address[1] if client.address else None
        print(f"🌐 Порт подключения: {port}")
        
        if db_name == 'stylist_ai_prod' and port == 27018:
            print("✅ Используется ПРОДАКШЕН база")
            return 'production'
        elif db_name == 'stylist_ai' and port == 27017:
            print("❌ Используется STAGING база")
            return 'staging'
        else:
            print(f"❓ Используется неизвестная база: {db_name} на порту {port}")
            return 'unknown'
        
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return None

def test_write_location():
    """Тестирует, куда записываются данные"""
    print("\n=== Тест записи данных ===")
    
    # Получаем настройки приложения
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    db_name = os.getenv('MONGO_DB_NAME', 'stylist_ai')
    
    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        # Создаем тестовый документ
        test_doc = {
            "test_type": "database_check",
            "timestamp": datetime.now(),
            "message": "Тест записи в базу данных"
        }
        
        # Записываем в базу приложения
        result = db.test_collection.insert_one(test_doc)
        print(f"✅ Записан тестовый документ в {db_name}")
        print(f"📄 ID: {result.inserted_id}")
        
        # Проверяем в обеих базах
        print("\n--- Проверка в staging ---")
        staging_client = MongoClient('mongodb://localhost:27017/')
        staging_doc = staging_client.stylist_ai.test_collection.find_one({"test_type": "database_check"})
        print(f"В staging: {'Да' if staging_doc else 'Нет'}")
        
        print("\n--- Проверка в production ---")
        prod_client = MongoClient('mongodb://localhost:27018/')
        prod_doc = prod_client.stylist_ai_prod.test_collection.find_one({"test_type": "database_check"})
        print(f"В production: {'Да' if prod_doc else 'Нет'}")
        
        # Очищаем тестовые данные
        db.test_collection.delete_one({"_id": result.inserted_id})
        print("\n🧹 Тестовые данные удалены")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка теста записи: {e}")
        return False

def main():
    """Главная функция"""
    print("🔍 Проверка использования базы данных")
    print("=" * 50)
    
    # Проверяем все базы
    staging_ok = check_staging_database()
    production_ok = check_production_database()
    app_db_type = check_application_database()
    
    # Тестируем запись
    write_test_ok = test_write_location()
    
    # Выводим итоговый результат
    print("\n" + "=" * 50)
    print("📋 ИТОГОВЫЙ РЕЗУЛЬТАТ:")
    
    if app_db_type == 'production':
        print("✅ Приложение использует ПРОДАКШЕН базу данных")
    elif app_db_type == 'staging':
        print("❌ Приложение использует STAGING базу данных")
        print("⚠️  Нужно настроить приложение для использования продакшен базы")
    else:
        print("❓ Не удалось определить тип базы данных")
    
    if not staging_ok:
        print("⚠️  Staging база недоступна")
    
    if not production_ok:
        print("⚠️  Production база недоступна")
    
    if not write_test_ok:
        print("⚠️  Тест записи не прошел")

if __name__ == '__main__':
    main() 