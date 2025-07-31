#!/usr/bin/env python3
"""
Скрипт для импорта данных MongoDB для продакшена
"""

import os
import json
import logging
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

def import_collection_from_json(collection, filename):
    """Импортирует коллекцию из JSON файла"""
    try:
        if not os.path.exists(filename):
            logger.warning(f"⚠️ Файл {filename} не найден, пропускаем")
            return True
        
        # Читаем данные из файла
        with open(filename, 'r', encoding='utf-8') as f:
            documents = json.load(f)
        
        if not documents:
            logger.info(f"📝 Файл {filename} пустой, пропускаем")
            return True
        
        # Конвертируем строки обратно в ObjectId
        for doc in documents:
            if '_id' in doc and isinstance(doc['_id'], str):
                try:
                    doc['_id'] = ObjectId(doc['_id'])
                except:
                    # Если не удается конвертировать в ObjectId, оставляем как строку
                    pass
        
        # Очищаем коллекцию перед импортом
        collection.delete_many({})
        logger.info(f"🗑️ Очищена коллекция {collection.name}")
        
        # Импортируем документы
        if documents:
            result = collection.insert_many(documents)
            logger.info(f"✅ Импортировано {len(result.inserted_ids)} документов в {collection.name}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка импорта {filename}: {e}")
        return False

def main():
    """Главная функция импорта"""
    print("🚀 Импорт данных MongoDB для продакшена")
    print("=" * 50)
    
    # Настройки подключения к MongoDB для продакшена
    mongo_uri = os.getenv('MONGO_URI_PROD', 'mongodb://localhost:27018/')
    database_name = os.getenv('MONGO_DB_NAME_PROD', 'stylist_ai_prod')
    
    try:
        # Подключаемся к MongoDB
        logger.info(f"🔌 Подключаемся к MongoDB (PROD): {mongo_uri}")
        client = MongoClient(mongo_uri)
        db = client[database_name]
        
        # Проверяем подключение
        client.admin.command('ping')
        logger.info("✅ Подключение к MongoDB (PROD) успешно!")
        
        # Спрашиваем пользователя о папке с данными
        print("\nДоступные папки экспорта:")
        export_dirs = [d for d in os.listdir('.') if d.startswith('mongo_export')]
        for i, dir_name in enumerate(export_dirs, 1):
            print(f"{i}. {dir_name}")
        
        if not export_dirs:
            print("❌ Папки экспорта не найдены")
            return False
        
        choice = input(f"\nВыберите папку (1-{len(export_dirs)}): ").strip()
        try:
            export_dir = export_dirs[int(choice) - 1]
        except (ValueError, IndexError):
            print("❌ Неверный выбор")
            return False
        
        if not os.path.exists(export_dir):
            print(f"❌ Папка {export_dir} не существует")
            return False
        
        print(f"\n📁 Импортируем данные из папки: {export_dir}")
        
        # Список коллекций для импорта
        collections_to_import = [
            'users',
            'sessions', 
            'password_reset_tokens',
            'pre_subscriptions',
            'products',
            'products_enhanced',
            'chat_sessions'
        ]
        
        success_count = 0
        error_count = 0
        
        # Импортируем каждую коллекцию
        for collection_name in collections_to_import:
            try:
                collection = db[collection_name]
                filename = os.path.join(export_dir, f"{collection_name}.json")
                
                if import_collection_from_json(collection, filename):
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"❌ Ошибка импорта коллекции {collection_name}: {e}")
                error_count += 1
        
        # Закрываем подключение
        client.close()
        
        print(f"\n=== Результат импорта ===")
        print(f"✅ Успешно импортировано: {success_count} коллекций")
        print(f"❌ Ошибок: {error_count}")
        
        if success_count > 0:
            print(f"\n📊 Статистика базы данных:")
            client = MongoClient(mongo_uri)
            db = client[database_name]
            for collection_name in collections_to_import:
                try:
                    count = db[collection_name].count_documents({})
                    print(f"   {collection_name}: {count} документов")
                except:
                    pass
            client.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False

if __name__ == '__main__':
    main() 