#!/usr/bin/env python3
"""
Скрипт для управления пользователями в MongoDB (исправленная версия)
"""

import os
import logging
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import user_auth

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

def connect_to_mongo():
    """Подключается к MongoDB"""
    try:
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        database_name = os.getenv('MONGO_DB_NAME', 'stylist_ai')
        
        client = MongoClient(mongo_uri)
        db = client[database_name]
        
        # Проверяем подключение
        client.admin.command('ping')
        logger.info("✅ Подключение к MongoDB успешно!")
        
        return db
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к MongoDB: {e}")
        return None

def list_users():
    """Показывает список всех пользователей"""
    print("=== Список пользователей ===")
    
    db = connect_to_mongo()
    if db is None:
        return False
    
    users = db.users.find({})
    user_count = 0
    
    print(f"{'ID':<24} {'Email':<30} {'Username':<20} {'Подписка':<15} {'Создан':<20}")
    print("-" * 110)
    
    for user in users:
        user_id = str(user['_id'])
        email = user.get('email') or 'N/A'
        username = user.get('username') or 'N/A'
        subscription = user.get('subscription_end') or 'Нет'
        created = user.get('created_at') or 'N/A'
        
        if isinstance(created, datetime):
            created = created.strftime('%Y-%m-%d %H:%M')
        elif created is None:
            created = 'N/A'
        
        print(f"{user_id:<24} {email:<30} {username:<20} {subscription:<15} {created:<20}")
        user_count += 1
    
    print(f"\nВсего пользователей: {user_count}")
    return True

def delete_user_by_email(email):
    """Удаляет пользователя по email"""
    print(f"🗑️ Удаление пользователя: {email}")
    
    db = connect_to_mongo()
    if db is None:
        return False
    
    # Находим пользователя
    user = db.users.find_one({"email": email})
    if not user:
        print(f"❌ Пользователь с email {email} не найден")
        return False
    
    # Показываем информацию о пользователе
    print(f"📧 Email: {user.get('email') or 'N/A'}")
    print(f"👤 Username: {user.get('username') or 'N/A'}")
    print(f"📅 Создан: {user.get('created_at') or 'N/A'}")
    print(f"💳 Подписка: {user.get('subscription_end') or 'Нет'}")
    
    # Подтверждение удаления
    confirm = input("\n❓ Вы уверены, что хотите удалить этого пользователя? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Удаление отменено")
        return False
    
    # Удаляем пользователя
    result = db.users.delete_one({"email": email})
    
    if result.deleted_count > 0:
        print(f"✅ Пользователь {email} успешно удален")
        
        # Также удаляем связанные сессии
        sessions_deleted = db.sessions.delete_many({"email": email})
        print(f"🗑️ Удалено {sessions_deleted.deleted_count} связанных сессий")
        
        return True
    else:
        print(f"❌ Ошибка удаления пользователя {email}")
        return False

def delete_user_by_id(user_id):
    """Удаляет пользователя по ID"""
    print(f"🗑️ Удаление пользователя по ID: {user_id}")
    
    db = connect_to_mongo()
    if db is None:
        return False
    
    try:
        object_id = ObjectId(user_id)
    except:
        print(f"❌ Неверный формат ID: {user_id}")
        return False
    
    # Находим пользователя
    user = db.users.find_one({"_id": object_id})
    if not user:
        print(f"❌ Пользователь с ID {user_id} не найден")
        return False
    
    # Показываем информацию о пользователе
    print(f"📧 Email: {user.get('email') or 'N/A'}")
    print(f"👤 Username: {user.get('username') or 'N/A'}")
    print(f"📅 Создан: {user.get('created_at') or 'N/A'}")
    print(f"💳 Подписка: {user.get('subscription_end') or 'Нет'}")
    
    # Подтверждение удаления
    confirm = input("\n❓ Вы уверены, что хотите удалить этого пользователя? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Удаление отменено")
        return False
    
    # Удаляем пользователя
    result = db.users.delete_one({"_id": object_id})
    
    if result.deleted_count > 0:
        print(f"✅ Пользователь с ID {user_id} успешно удален")
        
        # Также удаляем связанные сессии
        sessions_deleted = db.sessions.delete_many({"user_id": object_id})
        print(f"🗑️ Удалено {sessions_deleted.deleted_count} связанных сессий")
        
        return True
    else:
        print(f"❌ Ошибка удаления пользователя с ID {user_id}")
        return False

def delete_inactive_users():
    """Удаляет неактивных пользователей (без подписки)"""
    print("🗑️ Удаление неактивных пользователей")
    
    db = connect_to_mongo()
    if db is None:
        return False
    
    # Находим пользователей без подписки
    inactive_users = db.users.find({"subscription_end": {"$exists": False}})
    inactive_count = 0
    
    print("\nНеактивные пользователи:")
    print("-" * 50)
    
    for user in inactive_users:
        email = user.get('email') or 'N/A'
        username = user.get('username') or 'N/A'
        print(f"📧 {email} - {username}")
        inactive_count += 1
    
    if inactive_count == 0:
        print("✅ Неактивных пользователей не найдено")
        return True
    
    print(f"\nНайдено {inactive_count} неактивных пользователей")
    
    # Подтверждение удаления
    confirm = input("\n❓ Удалить всех неактивных пользователей? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Удаление отменено")
        return False
    
    # Удаляем неактивных пользователей
    result = db.users.delete_many({"subscription_end": {"$exists": False}})
    
    if result.deleted_count > 0:
        print(f"✅ Удалено {result.deleted_count} неактивных пользователей")
        return True
    else:
        print("❌ Ошибка удаления неактивных пользователей")
        return False

def search_users(query):
    """Поиск пользователей по email или username"""
    print(f"🔍 Поиск пользователей: {query}")
    
    db = connect_to_mongo()
    if db is None:
        return False
    
    # Поиск по email или username
    users = db.users.find({
        "$or": [
            {"email": {"$regex": query, "$options": "i"}},
            {"username": {"$regex": query, "$options": "i"}}
        ]
    })
    
    found_count = 0
    print(f"\nРезультаты поиска:")
    print("-" * 50)
    
    for user in users:
        user_id = str(user['_id'])
        email = user.get('email') or 'N/A'
        username = user.get('username') or 'N/A'
        subscription = user.get('subscription_end') or 'Нет'
        
        print(f"ID: {user_id}")
        print(f"Email: {email}")
        print(f"Username: {username}")
        print(f"Подписка: {subscription}")
        print("-" * 50)
        found_count += 1
    
    print(f"Найдено пользователей: {found_count}")
    return True

def main():
    """Главная функция"""
    print("👥 Управление пользователями")
    print("=" * 50)
    
    while True:
        print("\nВыберите действие:")
        print("1. Показать всех пользователей")
        print("2. Удалить пользователя по email")
        print("3. Удалить пользователя по ID")
        print("4. Удалить неактивных пользователей")
        print("5. Поиск пользователей")
        print("6. Выход")
        
        choice = input("\nВведите номер (1-6): ").strip()
        
        if choice == '1':
            list_users()
        elif choice == '2':
            email = input("Введите email пользователя: ").strip()
            if email:
                delete_user_by_email(email)
        elif choice == '3':
            user_id = input("Введите ID пользователя: ").strip()
            if user_id:
                delete_user_by_id(user_id)
        elif choice == '4':
            delete_inactive_users()
        elif choice == '5':
            query = input("Введите поисковый запрос: ").strip()
            if query:
                search_users(query)
        elif choice == '6':
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")

if __name__ == '__main__':
    main() 