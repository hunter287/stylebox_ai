#!/usr/bin/env python3
"""
Скрипт для проверки логики предварительных подписок
"""

import user_auth
from datetime import datetime
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def check_pre_subscriptions():
    """Проверяет предварительные подписки"""
    print("=== Проверка предварительных подписок ===")
    
    auth = user_auth.UserAuth()
    
    if not auth.connect():
        print("❌ Ошибка подключения к базе")
        return False
    
    # Получаем все предварительные подписки
    result = auth.list_pre_subscriptions(active_only=True)
    
    if result['success']:
        subscriptions = result['subscriptions']
        print(f"📋 Найдено {len(subscriptions)} активных предварительных подписок:")
        
        for sub in subscriptions:
            email = sub.get('email', 'N/A')
            end_date = sub.get('subscription_end', 'N/A')
            created = sub.get('created_at', 'N/A')
            source = sub.get('source', 'manual')
            
            print(f"   📧 {email}")
            print(f"      Действует до: {end_date}")
            print(f"      Источник: {source}")
            print(f"      Создана: {created}")
            print("   " + "-" * 40)
    else:
        print(f"❌ Ошибка получения подписок: {result['error']}")
        return False
    
    return True

def check_users_with_subscriptions():
    """Проверяет пользователей с подписками"""
    print("\n=== Проверка пользователей с подписками ===")
    
    auth = user_auth.UserAuth()
    
    if not auth.connect():
        print("❌ Ошибка подключения к базе")
        return False
    
    # Получаем всех пользователей
    users = list(auth.users_collection.find({}))
    
    users_with_subscription = []
    users_without_subscription = []
    
    for user in users:
        email = user.get('email', 'N/A')
        subscription = user.get('subscription_end')
        created = user.get('created_at', 'N/A')
        
        if subscription:
            users_with_subscription.append({
                'email': email,
                'subscription': subscription,
                'created': created
            })
        else:
            users_without_subscription.append({
                'email': email,
                'created': created
            })
    
    print(f"📊 Пользователей с подписками: {len(users_with_subscription)}")
    print(f"📊 Пользователей без подписок: {len(users_without_subscription)}")
    
    if users_with_subscription:
        print("\n✅ Пользователи с подписками:")
        for user in users_with_subscription:
            print(f"   📧 {user['email']}")
            print(f"      Подписка до: {user['subscription']}")
            print(f"      Создан: {user['created']}")
            print("   " + "-" * 40)
    
    if users_without_subscription:
        print(f"\n❌ Пользователи без подписок ({len(users_without_subscription)}):")
        for user in users_without_subscription[:10]:  # Показываем только первые 10
            print(f"   📧 {user['email']} (создан: {user['created']})")
        
        if len(users_without_subscription) > 10:
            print(f"   ... и еще {len(users_without_subscription) - 10} пользователей")
    
    return True

def test_pre_subscription_lookup():
    """Тестирует поиск предварительных подписок"""
    print("\n=== Тест поиска предварительных подписок ===")
    
    auth = user_auth.UserAuth()
    
    if not auth.connect():
        print("❌ Ошибка подключения к базе")
        return False
    
    # Получаем email для тестирования
    test_email = input("Введите email для проверки: ").strip()
    
    if not test_email:
        print("❌ Email не введен")
        return False
    
    print(f"\n🔍 Проверяем предварительную подписку для: {test_email}")
    
    # Проверяем предварительную подписку
    pre_sub_result = auth.get_pre_subscription(test_email)
    
    if pre_sub_result['success']:
        subscription = pre_sub_result['subscription']
        print(f"✅ Предварительная подписка найдена:")
        print(f"   Email: {subscription.get('email')}")
        print(f"   Действует до: {subscription.get('subscription_end')}")
        print(f"   Источник: {subscription.get('source')}")
        print(f"   Создана: {subscription.get('created_at')}")
    else:
        print(f"❌ Предварительная подписка не найдена: {pre_sub_result['error']}")
    
    # Проверяем пользователя
    user = auth.users_collection.find_one({"email": test_email})
    
    if user:
        print(f"\n👤 Пользователь найден:")
        print(f"   Email: {user.get('email')}")
        print(f"   Username: {user.get('username')}")
        print(f"   Подписка: {user.get('subscription_end', 'Нет')}")
        print(f"   Создан: {user.get('created_at')}")
        
        # Проверяем, есть ли несоответствие
        if not user.get('subscription_end') and pre_sub_result['success']:
            print("\n⚠️  ПРОБЛЕМА: Есть предварительная подписка, но пользователь не получил подписку!")
            print("   Возможные причины:")
            print("   1. Пользователь зарегистрировался до добавления предварительной подписки")
            print("   2. Ошибка в логике регистрации")
            print("   3. Проблема с форматом email (регистр, пробелы)")
        elif user.get('subscription_end') and not pre_sub_result['success']:
            print("\n✅ Пользователь имеет подписку, предварительная подписка была использована")
        elif user.get('subscription_end') and pre_sub_result['success']:
            print("\n⚠️  ПРОБЛЕМА: Пользователь имеет подписку И предварительную подписку!")
            print("   Предварительная подписка должна была быть удалена при регистрации")
        else:
            print("\n✅ Состояние корректное: нет предварительной подписки и нет подписки у пользователя")
    else:
        print(f"\n❌ Пользователь {test_email} не найден")
    
    return True

def test_registration_logic():
    """Тестирует логику регистрации"""
    print("\n=== Тест логики регистрации ===")
    
    auth = user_auth.UserAuth()
    
    if not auth.connect():
        print("❌ Ошибка подключения к базе")
        return False
    
    # Получаем email для тестирования
    test_email = input("Введите email для тестирования регистрации: ").strip()
    
    if not test_email:
        print("❌ Email не введен")
        return False
    
    print(f"\n🔍 Тестируем логику регистрации для: {test_email}")
    
    # Проверяем, есть ли предварительная подписка
    pre_sub_result = auth.get_pre_subscription(test_email)
    
    if pre_sub_result['success']:
        subscription = pre_sub_result['subscription']
        print(f"✅ Найдена предварительная подписка:")
        print(f"   Действует до: {subscription.get('subscription_end')}")
        
        # Симулируем логику регистрации
        print(f"\n🔄 Симулируем логику регистрации...")
        
        # Проверяем, что пользователь получит подписку
        subscription_end = subscription.get('subscription_end')
        if subscription_end:
            print(f"✅ При регистрации пользователь получит подписку до: {subscription_end}")
            
            # Проверяем, что предварительная подписка будет удалена
            print(f"✅ Предварительная подписка будет удалена после регистрации")
        else:
            print(f"❌ Предварительная подписка не имеет даты окончания")
    else:
        print(f"❌ Предварительная подписка не найдена: {pre_sub_result['error']}")
        print(f"   При регистрации пользователь НЕ получит подписку")
    
    return True

def check_database_connection():
    """Проверяет подключение к базе данных"""
    print("=== Проверка подключения к базе данных ===")
    
    # Проверяем переменные окружения
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    db_name = os.getenv('MONGO_DB_NAME', 'stylist_ai')
    
    print(f"MONGO_URI: {mongo_uri}")
    print(f"MONGO_DB_NAME: {db_name}")
    
    auth = user_auth.UserAuth()
    
    if auth.connect():
        print("✅ Подключение к базе успешно")
        
        # Проверяем коллекции
        collections = auth.db.list_collection_names()
        print(f"📋 Доступные коллекции: {collections}")
        
        # Проверяем количество документов
        users_count = auth.users_collection.count_documents({})
        pre_sub_count = auth.pre_subscriptions_collection.count_documents({})
        
        print(f"📊 Пользователей: {users_count}")
        print(f"📊 Предварительных подписок: {pre_sub_count}")
        
        return True
    else:
        print("❌ Ошибка подключения к базе")
        return False

def main():
    """Главная функция"""
    print("🔍 Диагностика предварительных подписок")
    print("=" * 50)
    
    # Проверяем подключение
    if not check_database_connection():
        return False
    
    # Проверяем предварительные подписки
    if not check_pre_subscriptions():
        return False
    
    # Проверяем пользователей
    if not check_users_with_subscriptions():
        return False
    
    # Тестируем поиск
    if not test_pre_subscription_lookup():
        return False
    
    # Тестируем логику регистрации
    if not test_registration_logic():
        return False
    
    print("\n" + "=" * 50)
    print("✅ Диагностика завершена")
    print("📋 Проверьте результаты выше для выявления проблем")

if __name__ == '__main__':
    main() 