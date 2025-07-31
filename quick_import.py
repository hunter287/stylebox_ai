#!/usr/bin/env python3
"""
Быстрый импорт всех данных MongoDB
"""

import json
import os
from pymongo import MongoClient
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def connect_to_mongo():
    """Подключается к MongoDB"""
    try:
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        db_name = os.getenv('MONGO_DB_NAME', 'stylist_ai')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        # Проверяем подключение
        db.command('ping')
        
        logger.info(f"✅ Подключение к MongoDB успешно: {db_name}")
        return db
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к MongoDB: {e}")
        return None

def import_collection(db, collection_name, json_file):
    """Импортирует коллекцию из JSON файла"""
    try:
        if not os.path.exists(json_file):
            logger.error(f"❌ Файл {json_file} не найден")
            return False
        
        collection = db[collection_name]
        
        # Читаем JSON файл
        logger.info(f"📖 Читаем файл {json_file}...")
        with open(json_file, 'r', encoding='utf-8') as f:
            documents = json.load(f)
        
        if not documents:
            logger.warning(f"⚠️ Файл {json_file} пустой")
            return True
        
        # Очищаем коллекцию перед импортом
        logger.info(f"🗑️ Очищаем коллекцию {collection_name}...")
        collection.delete_many({})
        
        # Импортируем документы
        logger.info(f"📥 Импортируем {len(documents)} документов в {collection_name}...")
        result = collection.insert_many(documents)
        
        logger.info(f"✅ Импортировано {len(result.inserted_ids)} документов в {collection_name}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка импорта коллекции {collection_name}: {e}")
        return False

def main():
    """Главная функция"""
    print("🚀 Быстрый импорт данных MongoDB")
    print("=" * 40)
    
    db = connect_to_mongo()
    if db is None:
        print("❌ Не удалось подключиться к MongoDB")
        return
    
    # Список файлов для импорта
    import_files = [
        ('users', 'users.json'),
        ('sessions', 'sessions.json'),
        ('password_reset_tokens', 'password_reset_tokens.json'),
        ('pre_subscriptions', 'pre_subscriptions.json'),
        ('products', 'products.json'),
        ('products_enhanced', 'products_enhanced.json'),
        ('chat_sessions', 'chat_sessions.json')
    ]
    
    success_count = 0
    error_count = 0
    
    print("\n🔄 Начинаем импорт...")
    
    for collection_name, filename in import_files:
        if os.path.exists(filename):
            if import_collection(db, collection_name, filename):
                success_count += 1
            else:
                error_count += 1
        else:
            logger.warning(f"⚠️ Файл {filename} не найден")
    
    print(f"\n=== Результат импорта ===")
    print(f"✅ Успешно импортировано: {success_count}")
    print(f"❌ Ошибок: {error_count}")
    
    if error_count == 0:
        print("🎉 Импорт завершен успешно!")
    else:
        print("⚠️ Импорт завершен с ошибками")

if __name__ == '__main__':
    main() 