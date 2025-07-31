#!/usr/bin/env python3
"""
Скрипт для просмотра данных MongoDB
"""

import os
import json
from pymongo import MongoClient
import logging
from datetime import datetime

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
        
        # Проверяем подключение
        db.command('ping')
        
        logger.info(f"✅ Подключение к MongoDB успешно: {db_name}")
        return db
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к MongoDB: {e}")
        return None

def show_collection_stats(db):
    """Показывает статистику по коллекциям"""
    print("\n=== Статистика коллекций ===")
    print(f"{'Коллекция':<25} {'Документов':<12} {'Размер (MB)':<12}")
    print("-" * 50)
    
    for collection_name in sorted(db.list_collection_names()):
        collection = db[collection_name]
        count = collection.count_documents({})
        
        # Получаем размер коллекции
        try:
            stats = db.command("collstats", collection_name)
            size_mb = round(stats.get('size', 0) / (1024 * 1024), 2)
        except:
            size_mb = 0
        
        print(f"{collection_name:<25} {count:<12} {size_mb:<12}")
    
    return True

def view_collection_data(db, collection_name, limit=5):
    """Показывает данные из коллекции"""
    try:
        collection = db[collection_name]
        documents = list(collection.find().limit(limit))
        
        if not documents:
            print(f"📝 Коллекция {collection_name} пустая")
            return
        
        print(f"\n=== Данные из коллекции '{collection_name}' ===")
        print(f"Показано {len(documents)} из {collection.count_documents({})} документов")
        print("-" * 60)
        
        for i, doc in enumerate(documents, 1):
            print(f"\n📄 Документ {i}:")
            # Преобразуем ObjectId в строку для вывода
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            
            # Красиво выводим JSON
            print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
        
    except Exception as e:
        logger.error(f"❌ Ошибка просмотра коллекции {collection_name}: {e}")

def search_in_collection(db, collection_name, field, value):
    """Ищет документы в коллекции"""
    try:
        collection = db[collection_name]
        
        # Создаем фильтр поиска
        if field == '_id':
            from bson import ObjectId
            try:
                filter_query = {field: ObjectId(value)}
            except:
                print("❌ Неверный формат ObjectId")
                return
        else:
            filter_query = {field: value}
        
        documents = list(collection.find(filter_query).limit(10))
        
        if not documents:
            print(f"🔍 Документы с {field}={value} не найдены")
            return
        
        print(f"\n=== Результаты поиска в '{collection_name}' ===")
        print(f"Найдено {len(documents)} документов")
        print("-" * 60)
        
        for i, doc in enumerate(documents, 1):
            print(f"\n📄 Документ {i}:")
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
        
    except Exception as e:
        logger.error(f"❌ Ошибка поиска в коллекции {collection_name}: {e}")

def show_menu():
    """Показывает меню"""
    print("\n=== Просмотр данных MongoDB ===")
    print("1. Показать статистику коллекций")
    print("2. Просмотреть данные коллекции")
    print("3. Поиск в коллекции")
    print("4. Показать пользователей")
    print("5. Показать предварительные подписки")
    print("6. Показать товары")
    print("7. Выход")

def main():
    """Главная функция"""
    print("🔍 Просмотр данных MongoDB")
    print("=" * 30)
    
    db = connect_to_mongo()
    if db is None:
        print("❌ Не удалось подключиться к MongoDB")
        return
    
    while True:
        show_menu()
        
        try:
            choice = input("\nВведите номер (1-7): ").strip()
            
            if choice == '1':
                show_collection_stats(db)
                
            elif choice == '2':
                collections = db.list_collection_names()
                print("\nДоступные коллекции:")
                for i, coll in enumerate(collections, 1):
                    print(f"{i}. {coll}")
                
                try:
                    coll_choice = int(input("\nВыберите номер коллекции: ")) - 1
                    if 0 <= coll_choice < len(collections):
                        collection_name = collections[coll_choice]
                        limit = int(input("Сколько документов показать (по умолчанию 5): ") or "5")
                        view_collection_data(db, collection_name, limit)
                    else:
                        print("❌ Неверный выбор")
                except ValueError:
                    print("❌ Неверный ввод")
                    
            elif choice == '3':
                collections = db.list_collection_names()
                print("\nДоступные коллекции:")
                for i, coll in enumerate(collections, 1):
                    print(f"{i}. {coll}")
                
                try:
                    coll_choice = int(input("\nВыберите номер коллекции: ")) - 1
                    if 0 <= coll_choice < len(collections):
                        collection_name = collections[coll_choice]
                        field = input("Введите поле для поиска: ").strip()
                        value = input("Введите значение для поиска: ").strip()
                        search_in_collection(db, collection_name, field, value)
                    else:
                        print("❌ Неверный выбор")
                except ValueError:
                    print("❌ Неверный ввод")
                    
            elif choice == '4':
                print("\n=== Пользователи ===")
                view_collection_data(db, 'users', 10)
                
            elif choice == '5':
                print("\n=== Предварительные подписки ===")
                view_collection_data(db, 'pre_subscriptions', 10)
                
            elif choice == '6':
                print("\n=== Товары ===")
                view_collection_data(db, 'products', 5)
                
            elif choice == '7':
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