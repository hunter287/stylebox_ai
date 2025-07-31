#!/usr/bin/env python3
"""
Скрипт для импорта данных MongoDB на продакшен сервер
"""

import json
import os
import sys
from datetime import datetime
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

def import_collection(db, collection_name, json_file, drop_existing=True):
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
        
        # Очищаем коллекцию перед импортом (если требуется)
        if drop_existing:
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

def show_import_menu():
    """Показывает меню импорта"""
    print("\n=== Меню импорта ===")
    print("1. Импортировать все коллекции")
    print("2. Импортировать конкретную коллекцию")
    print("3. Показать доступные файлы")
    print("4. Проверить подключение к MongoDB")
    print("5. Выход")

def get_available_files():
    """Получает список доступных JSON файлов"""
    files = []
    for file in os.listdir('.'):
        if file.endswith('.json') and file != 'export_info.json':
            files.append(file)
    return sorted(files)

def import_all_collections():
    """Импортирует все коллекции"""
    db = connect_to_mongo()
    if db is None:
        return False
    
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
    
    for collection_name, filename in import_files:
        if os.path.exists(filename):
            print(f"\n🔄 Импортируем {collection_name}...")
            if import_collection(db, collection_name, filename):
                success_count += 1
            else:
                error_count += 1
        else:
            logger.warning(f"⚠️ Файл {filename} не найден")
    
    print(f"\n=== Результат импорта ===")
    print(f"✅ Успешно импортировано: {success_count}")
    print(f"❌ Ошибок: {error_count}")
    
    return error_count == 0

def import_specific_collection():
    """Импортирует конкретную коллекцию"""
    db = connect_to_mongo()
    if db is None:
        return False
    
    # Показываем доступные файлы
    files = get_available_files()
    if not files:
        print("❌ JSON файлы не найдены в текущей директории")
        return False
    
    print("\nДоступные файлы:")
    for i, file in enumerate(files, 1):
        print(f"{i}. {file}")
    
    try:
        choice = int(input("\nВыберите номер файла: ")) - 1
        if 0 <= choice < len(files):
            filename = files[choice]
            collection_name = filename.replace('.json', '')
            
            print(f"\n🔄 Импортируем {collection_name}...")
            return import_collection(db, collection_name, filename)
        else:
            print("❌ Неверный выбор")
            return False
    except ValueError:
        print("❌ Неверный ввод")
        return False

def show_available_files():
    """Показывает доступные файлы"""
    files = get_available_files()
    if not files:
        print("❌ JSON файлы не найдены в текущей директории")
        return
    
    print("\n=== Доступные файлы ===")
    for i, file in enumerate(files, 1):
        size = os.path.getsize(file)
        size_mb = size / (1024 * 1024)
        print(f"{i}. {file} ({size_mb:.2f} MB)")
    
    # Показываем общий размер
    total_size = sum(os.path.getsize(f) for f in files)
    total_size_mb = total_size / (1024 * 1024)
    print(f"\nОбщий размер: {total_size_mb:.2f} MB")

def check_mongo_connection():
    """Проверяет подключение к MongoDB"""
    db = connect_to_mongo()
    if db is None:
        return False
    
    try:
        # Проверяем подключение
        db.command('ping')
        print("✅ Подключение к MongoDB успешно")
        
        # Показываем информацию о базе данных
        collections = db.list_collection_names()
        print(f"📊 Коллекции в базе данных: {len(collections)}")
        for collection in sorted(collections):
            count = db[collection].count_documents({})
            print(f"   - {collection}: {count} документов")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False

def main():
    """Главная функция"""
    print("📥 Импорт данных MongoDB на продакшен")
    print("=" * 40)
    
    while True:
        show_import_menu()
        
        try:
            choice = input("\nВведите номер (1-5): ").strip()
            
            if choice == '1':
                print("\n🔄 Импорт всех коллекций...")
                import_all_collections()
                
            elif choice == '2':
                import_specific_collection()
                
            elif choice == '3':
                show_available_files()
                
            elif choice == '4':
                check_mongo_connection()
                
            elif choice == '5':
                print("👋 До свидания!")
                break
                
            else:
                print("❌ Неверный выбор. Попробуйте снова.")
                
        except KeyboardInterrupt:
            print("\n\n👋 Прервано пользователем")
            break
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")

if __name__ == '__main__':
    main() 