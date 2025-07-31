#!/usr/bin/env python3
"""
Скрипт для экспорта данных MongoDB для продакшена
"""

import os
import json
import logging
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

def export_collection_to_json(collection, filename):
    """Экспортирует коллекцию в JSON файл"""
    try:
        # Получаем все документы из коллекции
        documents = list(collection.find({}))
        
        # Конвертируем ObjectId в строки для JSON
        for doc in documents:
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
        
        # Сохраняем в файл
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Экспортировано {len(documents)} документов в {filename}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка экспорта {filename}: {e}")
        return False

def main():
    """Главная функция экспорта"""
    print("🚀 Экспорт данных MongoDB для продакшена")
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
        
        # Создаем папку для экспорта
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_dir = f"mongo_export_prod_{timestamp}"
        os.makedirs(export_dir, exist_ok=True)
        
        # Список коллекций для экспорта
        collections_to_export = [
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
        
        # Экспортируем каждую коллекцию
        for collection_name in collections_to_export:
            try:
                collection = db[collection_name]
                filename = os.path.join(export_dir, f"{collection_name}.json")
                
                if export_collection_to_json(collection, filename):
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"❌ Ошибка экспорта коллекции {collection_name}: {e}")
                error_count += 1
        
        # Сохраняем информацию об экспорте
        export_info = {
            "timestamp": datetime.now().isoformat(),
            "database": database_name,
            "collections_exported": success_count,
            "collections_failed": error_count,
            "total_collections": len(collections_to_export)
        }
        
        with open(os.path.join(export_dir, "export_info.json"), 'w', encoding='utf-8') as f:
            json.dump(export_info, f, ensure_ascii=False, indent=2)
        
        # Закрываем подключение
        client.close()
        
        print(f"\n=== Результат экспорта ===")
        print(f"✅ Успешно экспортировано: {success_count} коллекций")
        print(f"❌ Ошибок: {error_count}")
        print(f"📁 Папка экспорта: {export_dir}")
        
        if success_count > 0:
            print(f"\n📋 Экспортированные файлы:")
            for file in os.listdir(export_dir):
                if file.endswith('.json'):
                    file_path = os.path.join(export_dir, file)
                    size = os.path.getsize(file_path)
                    print(f"   {file} ({size} bytes)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False

if __name__ == '__main__':
    main() 