#!/usr/bin/env python3
"""
Скрипт для экспорта данных из MongoDB
"""

import os
import json
from datetime import datetime
from pymongo import MongoClient
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def connect_to_mongo():
    """Подключается к MongoDB"""
    try:
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        db_name = os.getenv('MONGO_DB_NAME', 'stylist_ai')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        logger.info(f"✅ Подключение к MongoDB успешно: {db_name}")
        return db
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к MongoDB: {e}")
        return None

def export_collection(db, collection_name, output_file):
    """Экспортирует коллекцию в JSON файл"""
    try:
        collection = db[collection_name]
        documents = list(collection.find())
        
        # Преобразуем ObjectId в строки для JSON сериализации
        for doc in documents:
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(documents, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"✅ Экспортировано {len(documents)} документов в {output_file}")
        return len(documents)
        
    except Exception as e:
        logger.error(f"❌ Ошибка экспорта коллекции {collection_name}: {e}")
        return 0

def export_all_data():
    """Экспортирует все важные коллекции"""
    db = connect_to_mongo()
    if db is None:
        return False
    
    # Создаем папку для экспорта
    export_dir = f"mongo_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
    
    total_exported = 0
    
    for collection_name in collections_to_export:
        if collection_name in db.list_collection_names():
            output_file = os.path.join(export_dir, f"{collection_name}.json")
            count = export_collection(db, collection_name, output_file)
            total_exported += count
        else:
            logger.warning(f"⚠️ Коллекция {collection_name} не найдена")
    
    # Создаем файл с метаинформацией
    meta_info = {
        "export_date": datetime.now().isoformat(),
        "database_name": db.name,
        "collections_exported": collections_to_export,
        "total_documents": total_exported
    }
    
    meta_file = os.path.join(export_dir, "export_info.json")
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta_info, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ Экспорт завершен. Всего экспортировано {total_exported} документов")
    logger.info(f"📁 Файлы сохранены в папке: {export_dir}")
    
    return True

def export_specific_collection(collection_name):
    """Экспортирует конкретную коллекцию"""
    db = connect_to_mongo()
    if db is None:
        return False
    
    if collection_name not in db.list_collection_names():
        logger.error(f"❌ Коллекция {collection_name} не найдена")
        return False
    
    output_file = f"{collection_name}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    count = export_collection(db, collection_name, output_file)
    
    return count > 0

def show_collection_stats():
    """Показывает статистику по коллекциям"""
    db = connect_to_mongo()
    if db is None:
        return False
    
    print("\n=== Статистика коллекций ===")
    print(f"{'Коллекция':<25} {'Документов':<12} {'Размер (MB)':<12}")
    print("-" * 50)
    
    for collection_name in sorted(db.list_collection_names()):
        collection = db[collection_name]
        count = collection.count_documents({})
        
        # Получаем размер коллекции
        stats = db.command("collstats", collection_name)
        size_mb = round(stats.get('size', 0) / (1024 * 1024), 2)
        
        print(f"{collection_name:<25} {count:<12} {size_mb:<12}")
    
    return True

def main():
    """Главная функция"""
    print("📤 Утилита экспорта данных MongoDB")
    print("=" * 40)
    
    while True:
        print("\nВыберите действие:")
        print("1. Экспортировать все коллекции")
        print("2. Экспортировать конкретную коллекцию")
        print("3. Показать статистику коллекций")
        print("4. Выход")
        
        choice = input("\nВведите номер (1-4): ").strip()
        
        if choice == '1':
            print("\n🔄 Экспорт всех коллекций...")
            export_all_data()
            
        elif choice == '2':
            collection_name = input("Введите название коллекции: ").strip()
            if collection_name:
                print(f"\n🔄 Экспорт коллекции {collection_name}...")
                export_specific_collection(collection_name)
            else:
                print("❌ Название коллекции не может быть пустым")
                
        elif choice == '3':
            show_collection_stats()
            
        elif choice == '4':
            print("👋 До свидания!")
            break
            
        else:
            print("❌ Неверный выбор. Попробуйте снова.")

if __name__ == '__main__':
    main() 