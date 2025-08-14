#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для управления пользователями гайдов
Позволяет добавлять пользователей по одному или списком для цветовых и Kibbe гайдов
"""

import os
import sys
import json
from datetime import datetime, timedelta
from user_auth import user_auth

def print_banner():
    """Выводит красивый баннер"""
    print("=" * 60)
    print("🎨 УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ГАЙДОВ")
    print("=" * 60)
    print()

def print_menu():
    """Выводит главное меню"""
    print("📋 ВЫБЕРИТЕ ДЕЙСТВИЕ:")
    print("1. ➕ Добавить одного пользователя")
    print("2. 📝 Добавить пользователей из файла")
    print("3. 👥 Добавить пользователей списком")
    print("4. 🔍 Просмотреть всех пользователей гайдов")
    print("5. ❌ Удалить пользователя")
    print("6. 📊 Статистика по гайдам")
    print("7. 🔍 Найти пользователя по email")
    print("8. ✅ Проверить возможность отправки гайда")
    print("9. 🔧 Исправить данные пользователя")
    print("10. 🔧🔧 Массовое исправление подписок")
    print("0. 🚪 Выход")
    print()

def add_single_user():
    """Добавляет одного пользователя"""
    print("\n➕ ДОБАВЛЕНИЕ ОДНОГО ПОЛЬЗОВАТЕЛЯ")
    print("-" * 40)
    
    # Получаем данные пользователя
    email = input("📧 Email пользователя: ").strip().lower()
    if not email:
        print("❌ Email не может быть пустым")
        return
    
    # Проверяем, существует ли пользователь
    print(f"🔍 Проверяем существующего пользователя {email}...")
    existing_user = user_auth.pre_subscriptions_collection.find_one({"email": email})
    
    if existing_user:
        print(f"⚠️ Пользователь {email} уже существует в базе данных:")
        print(f"   Тип: {existing_user.get('product_type', 'неизвестно')}")
        print(f"   Статус: {existing_user.get('status', 'неизвестно')}")
        print(f"   Источник: {existing_user.get('source', 'неизвестно')}")
        print(f"   Создан: {existing_user.get('created_at', 'неизвестно')}")
        
        update_choice = input("\n🔄 Обновить существующего пользователя? (y/n): ").strip().lower()
        if update_choice != 'y':
            print("❌ Операция отменена")
            return
        
        # Удаляем существующего пользователя
        user_auth.remove_pre_subscription(email)
        print(f"🗑️ Существующий пользователь {email} удален")
    
    print("\n🎨 ВЫБЕРИТЕ ТИП ГАЙДА:")
    print("1. 🎨 Цветовой гайд")
    print("2. 👗 Гайд по Кибби")
    
    guide_type = input("Выберите тип (1 или 2): ").strip()
    
    if guide_type == "1":
        product_type = "color_guide"
        guide_name = "цветовой гайд"
    elif guide_type == "2":
        product_type = "kibbe_guide"
        guide_name = "гайд по Кибби"
    else:
        print("❌ Неверный выбор")
        return
    
    # Получаем сумму (может быть 0 для бесплатных гайдов)
    try:
        amount = float(input("💰 Сумма (0 для бесплатного): ") or "0")
    except ValueError:
        print("❌ Неверная сумма")
        return
    
    # Получаем источник
    source = input("📝 Источник (manual, google_sheets, etc.): ").strip() or "manual"
    
    # Получаем заметки
    notes = input("📝 Заметки (опционально): ").strip() or f"Добавлен через скрипт {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    # Добавляем пользователя
    try:
        result = user_auth.add_pre_subscription(
            email=email,
            subscription_end=None,  # У гайдов нет subscription_end
            source=source,
            notes=notes,
            product_type=product_type
        )
        
        if result.get("success"):
            print(f"✅ Пользователь {email} успешно добавлен для {guide_name}")
            
            # Если сумма > 0, добавляем информацию о платеже
            if amount > 0:
                payment_result = user_auth.add_guide_purchase(
                    email=email,
                    product_type=product_type,
                    amount=amount,
                    transaction_id=f"manual_{int(datetime.now().timestamp())}",
                    source=source,
                    notes=notes
                )
                if payment_result.get("success"):
                    print(f"💰 Информация о платеже добавлена: {amount} RUB")
                else:
                    print(f"⚠️ Ошибка при добавлении информации о платеже: {payment_result.get('error')}")
        else:
            print(f"❌ Ошибка при добавлении пользователя: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")

def add_users_from_file():
    """Добавляет пользователей из файла"""
    print("\n📝 ДОБАВЛЕНИЕ ПОЛЬЗОВАТЕЛЕЙ ИЗ ФАЙЛА")
    print("-" * 40)
    
    filename = input("📁 Путь к файлу (JSON или TXT): ").strip()
    if not os.path.exists(filename):
        print(f"❌ Файл {filename} не найден")
        return
    
    try:
        if filename.endswith('.json'):
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            # Для TXT файла - каждая строка это email
            with open(filename, 'r', encoding='utf-8') as f:
                emails = [line.strip() for line in f if line.strip()]
                data = [{"email": email, "product_type": "color_guide"} for email in emails]
        
        if not isinstance(data, list):
            print("❌ Файл должен содержать список пользователей")
            return
        
        print(f"📊 Найдено {len(data)} пользователей")
        
        # Подтверждение
        confirm = input("Продолжить? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ Операция отменена")
            return
        
        # Добавляем пользователей
        success_count = 0
        for i, user_data in enumerate(data, 1):
            try:
                email = user_data.get('email', '').strip().lower()
                product_type = user_data.get('product_type', 'color_guide')
                amount = user_data.get('amount', 0)
                source = user_data.get('source', 'file_import')
                notes = user_data.get('notes', f'Импортирован из файла {datetime.now().strftime("%Y-%m-%d %H:%M")}')
                
                if not email:
                    print(f"⚠️ Строка {i}: пропущена (нет email)")
                    continue
                
                # Добавляем пользователя
                result = user_auth.add_pre_subscription(
                    email=email,
                    subscription_end=None,
                    source=source,
                    notes=notes,
                    product_type=product_type
                )
                
                if result.get("success"):
                    success_count += 1
                    print(f"✅ {i}/{len(data)}: {email} - {product_type}")
                    
                    # Если есть сумма, добавляем информацию о платеже
                    if amount > 0:
                        user_auth.add_guide_purchase(
                            email=email,
                            product_type=product_type,
                            amount=amount,
                            transaction_id=f"file_import_{int(datetime.now().timestamp())}_{i}",
                            source=source,
                            notes=notes
                        )
                else:
                    print(f"❌ {i}/{len(data)}: {email} - ошибка: {result.get('error')}")
                    
            except Exception as e:
                print(f"❌ {i}/{len(data)}: ошибка: {str(e)}")
        
        print(f"\n🎉 Импорт завершен! Успешно добавлено: {success_count}/{len(data)}")
        
    except Exception as e:
        print(f"❌ Ошибка при чтении файла: {str(e)}")

def add_users_list():
    """Добавляет пользователей списком"""
    print("\n👥 ДОБАВЛЕНИЕ ПОЛЬЗОВАТЕЛЕЙ СПИСКОМ")
    print("-" * 40)
    
    print("📝 Введите email'ы (по одному на строку, пустая строка для завершения):")
    emails = []
    
    while True:
        email = input(f"📧 Email {len(emails) + 1}: ").strip().lower()
        if not email:
            break
        emails.append(email)
    
    if not emails:
        print("❌ Не введено ни одного email")
        return
    
    print(f"\n📊 Введено {len(emails)} email'ов")
    
    # Выбираем тип гайда
    print("\n🎨 ВЫБЕРИТЕ ТИП ГАЙДА:")
    print("1. 🎨 Цветовой гайд")
    print("2. 👗 Гайд по Кибби")
    
    guide_type = input("Выберите тип (1 или 2): ").strip()
    
    if guide_type == "1":
        product_type = "color_guide"
        guide_name = "цветовой гайд"
    elif guide_type == "2":
        product_type = "kibbe_guide"
        guide_name = "гайд по Кибби"
    else:
        print("❌ Неверный выбор")
        return
    
    # Получаем сумму
    try:
        amount = float(input("💰 Сумма для каждого (0 для бесплатных): ") or "0")
    except ValueError:
        print("❌ Неверная сумма")
        return
    
    # Подтверждение
    confirm = input(f"Добавить {len(emails)} пользователей для {guide_name}? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Операция отменена")
        return
    
    # Добавляем пользователей
    success_count = 0
    for i, email in enumerate(emails, 1):
        try:
            result = user_auth.add_pre_subscription(
                email=email,
                subscription_end=None,
                source="manual_list",
                notes=f"Добавлен списком {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                product_type=product_type
            )
            
            if result.get("success"):
                success_count += 1
                print(f"✅ {i}/{len(emails)}: {email}")
                
                # Если есть сумма, добавляем информацию о платеже
                if amount > 0:
                    user_auth.add_guide_purchase(
                        email=email,
                        product_type=product_type,
                        amount=amount,
                        transaction_id=f"manual_list_{int(datetime.now().timestamp())}_{i}",
                        source="manual_list",
                        notes=f"Добавлен списком {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
            else:
                print(f"❌ {i}/{len(emails)}: {email} - ошибка: {result.get('error')}")
                
        except Exception as e:
            print(f"❌ {i}/{len(emails)}: {email} - ошибка: {str(e)}")
    
    print(f"\n🎉 Добавление завершено! Успешно: {success_count}/{len(emails)}")

def view_all_users():
    """Показывает всех пользователей гайдов"""
    print("\n🔍 ВСЕ ПОЛЬЗОВАТЕЛИ ГАЙДОВ")
    print("-" * 40)
    
    try:
        stats = user_auth.get_guide_purchase_stats()
        if not stats.get("success"):
            print(f"❌ Ошибка при получении статистики: {stats.get('error')}")
            return
        
        data = stats.get("data", {})
        
        print("🎨 ЦВЕТОВЫЕ ГАЙДЫ:")
        color_stats = data.get("color_guide", {})
        print(f"   Всего покупок: {color_stats.get('total_purchases', 0)}")
        print(f"   Отправлено: {color_stats.get('sent_count', 0)}")
        print(f"   Ожидают отправки: {color_stats.get('pending_count', 0)}")
        print(f"   Общая сумма: {color_stats.get('total_amount', 0)} RUB")
        
        print("\n👗 ГАЙДЫ ПО КИББИ:")
        kibbe_stats = data.get("kibbe_guide", {})
        print(f"   Всего покупок: {kibbe_stats.get('total_purchases', 0)}")
        print(f"   Отправлено: {kibbe_stats.get('sent_count', 0)}")
        print(f"   Ожидают отправки: {kibbe_stats.get('pending_count', 0)}")
        print(f"   Общая сумма: {kibbe_stats.get('total_amount', 0)} RUB")
        
        # Показываем детали по пользователям
        print("\n📋 ДЕТАЛИ ПО ПОЛЬЗОВАТЕЛЯМ:")
        print("(Для просмотра деталей используйте MongoDB Compass или другой клиент)")
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")

def delete_user():
    """Удаляет пользователя"""
    print("\n❌ УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ")
    print("-" * 40)
    
    email = input("📧 Email пользователя для удаления: ").strip().lower()
    if not email:
        print("❌ Email не может быть пустым")
        return
    
    # Подтверждение
    confirm = input(f"Удалить пользователя {email}? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Операция отменена")
        return
    
    try:
        result = user_auth.remove_pre_subscription(email)
        if result.get("success"):
            print(f"✅ Пользователь {email} успешно удален")
        else:
            print(f"❌ Ошибка при удалении: {result.get('error')}")
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")

def show_stats():
    """Показывает статистику по гайдам"""
    print("\n📊 СТАТИСТИКА ПО ГАЙДАМ")
    print("-" * 40)
    
    try:
        stats = user_auth.get_guide_purchase_stats()
        if not stats.get("success"):
            print(f"❌ Ошибка при получении статистики: {stats.get('error')}")
            return
        
        data = stats.get("data", {})
        
        print("🎨 ЦВЕТОВЫЕ ГАЙДЫ:")
        color_stats = data.get("color_guide", {})
        print(f"   📈 Всего покупок: {color_stats.get('total_purchases', 0)}")
        print(f"   📤 Отправлено: {color_stats.get('sent_count', 0)}")
        print(f"   ⏳ Ожидают отправки: {color_stats.get('pending_count', 0)}")
        print(f"   💰 Общая сумма: {color_stats.get('total_amount', 0)} RUB")
        
        print("\n👗 ГАЙДЫ ПО КИББИ:")
        kibbe_stats = data.get("kibbe_guide", {})
        print(f"   📈 Всего покупок: {kibbe_stats.get('total_purchases', 0)}")
        print(f"   📤 Отправлено: {kibbe_stats.get('sent_count', 0)}")
        print(f"   ⏳ Ожидают отправки: {kibbe_stats.get('pending_count', 0)}")
        print(f"   💰 Общая сумма: {kibbe_stats.get('total_amount', 0)} RUB")
        
        # Общая статистика
        total_purchases = (color_stats.get('total_purchases', 0) + 
                          kibbe_stats.get('total_purchases', 0))
        total_sent = (color_stats.get('sent_count', 0) + 
                     kibbe_stats.get('sent_count', 0))
        total_pending = (color_stats.get('pending_count', 0) + 
                        kibbe_stats.get('pending_count', 0))
        total_amount = (color_stats.get('total_amount', 0) + 
                       kibbe_stats.get('total_amount', 0))
        
        print(f"\n📊 ОБЩАЯ СТАТИСТИКА:")
        print(f"   📈 Всего покупок: {total_purchases}")
        print(f"   📤 Всего отправлено: {total_sent}")
        print(f"   ⏳ Всего ожидают: {total_pending}")
        print(f"   💰 Общая сумма: {total_amount} RUB")
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")

def find_user_by_email():
    """Находит пользователя по email"""
    print("\n🔍 ПОИСК ПОЛЬЗОВАТЕЛЯ ПО EMAIL")
    print("-" * 40)
    
    email = input("📧 Email пользователя: ").strip().lower()
    if not email:
        print("❌ Email не может быть пустым")
        return
    
    try:
        # Ищем все записи для этого email
        users = list(user_auth.pre_subscriptions_collection.find({"email": email}))
        
        if not users:
            print(f"❌ Пользователь {email} не найден в базе данных")
            return
        
        print(f"✅ Найдено {len(users)} записей для {email}:")
        print()
        
        for i, user in enumerate(users, 1):
            print(f"📋 ЗАПИСЬ {i}:")
            print(f"   🎨 Тип: {user.get('product_type', 'неизвестно')}")
            print(f"   📊 Статус: {user.get('status', 'неизвестно')}")
            print(f"   📝 Источник: {user.get('source', 'неизвестно')}")
            print(f"   📅 Создан: {user.get('created_at', 'неизвестно')}")
            print(f"   📅 Обновлен: {user.get('updated_at', 'неизвестно')}")
            print(f"   📝 Заметки: {user.get('notes', 'нет')}")
            
            # Проверяем подписку
            if user.get('product_type') == 'subscription':
                subscription_end = user.get('subscription_end')
                if subscription_end:
                    if subscription_end > datetime.utcnow():
                        print(f"   ✅ Подписка активна до: {subscription_end}")
                        print(f"   🎁 Бонус: Гайды по цветотипу и типажу БЕСПЛАТНО!")
                    else:
                        print(f"   ❌ Подписка истекла: {subscription_end}")
                else:
                    print(f"   ⚠️ Подписка без срока окончания")
            
            # Проверяем, отправлен ли гайд
            guide_data = user.get('guide_data', {})
            if guide_data:
                print(f"   📤 Гайд отправлен: {'Да' if guide_data.get('sent') else 'Нет'}")
                if guide_data.get('sent'):
                    print(f"   📅 Дата отправки: {guide_data.get('sent_at', 'неизвестно')}")
                    print(f"   📁 Путь к PDF: {guide_data.get('pdf_path', 'неизвестно')}")
                    print(f"   🔢 Попыток отправки: {guide_data.get('attempts', 0)}")
                    print(f"   📅 Последняя попытка: {guide_data.get('last_attempt', 'неизвестно')}")
            else:
                if user.get('product_type') in ['color_guide', 'kibbe_guide']:
                    print(f"   📤 Гайд отправлен: Нет (нет данных)")
            
            # Проверяем информацию о платеже
            if user.get('amount', 0) > 0:
                print(f"   💰 Сумма: {user.get('amount')} {user.get('currency', 'RUB')}")
                print(f"   🆔 ID транзакции: {user.get('transaction_id', 'неизвестно')}")
            elif user.get('product_type') in ['color_guide', 'kibbe_guide'] and user.get('source') == 'subscription_benefit':
                print(f"   💰 Сумма: БЕСПЛАТНО (бонус для подписчика)")
            
            print()
            
    except Exception as e:
        print(f"❌ Ошибка при поиске: {str(e)}")

def fix_user_data():
    """Исправляет данные пользователя"""
    print("\n🔧 ИСПРАВЛЕНИЕ ДАННЫХ ПОЛЬЗОВАТЕЛЯ")
    print("-" * 40)
    
    email = input("📧 Email пользователя: ").strip().lower()
    if not email:
        print("❌ Email не может быть пустым")
        return
    
    try:
        # Ищем пользователя в базе данных
        user = user_auth.pre_subscriptions_collection.find_one({"email": email})
        
        if not user:
            print(f"❌ Пользователь {email} не найден в базе данных")
            return
        
        print(f"🔍 Найдена запись для {email}:")
        print(f"   🎨 Тип: {user.get('product_type', 'неизвестно')}")
        print(f"   📊 Статус: {user.get('status', 'неизвестно')}")
        print(f"   📝 Источник: {user.get('source', 'неизвестно')}")
        print(f"   📅 Создан: {user.get('created_at', 'неизвестно')}")
        
        # Определяем, что нужно исправить
        print(f"\n🎯 ЧТО НУЖНО ИСПРАВИТЬ:")
        
        if not user.get('product_type'):
            print("   ❌ product_type: отсутствует")
        if not user.get('status'):
            print("   ❌ status: отсутствует")
        
        print("\n🎨 ВЫБЕРИТЕ ТИП ПРОДУКТА:")
        print("1. 🎨 Цветовой гайд")
        print("2. 👗 Гайд по Кибби")
        print("3. 🔐 Подписка на ИИ-стилиста")
        
        product_choice = input("Выберите тип (1, 2 или 3): ").strip()
        
        if product_choice == "1":
            product_type = "color_guide"
            product_name = "цветовой гайд"
        elif product_choice == "2":
            product_type = "kibbe_guide"
            product_name = "гайд по Кибби"
        elif product_choice == "3":
            product_type = "subscription"
            product_name = "подписка на ИИ-стилиста"
        else:
            print("❌ Неверный выбор")
            return
        
        # Определяем статус
        if product_type == "subscription":
            status = "completed"
        else:
            status = "completed"
        
        # Получаем сумму
        if product_type == "subscription":
            try:
                amount = float(input("💰 Сумма подписки (RUB): ") or "0")
            except ValueError:
                print("❌ Неверная сумма")
                return
        else:
            try:
                amount = float(input("💰 Сумма гайда (0 для бесплатного): ") or "0")
            except ValueError:
                print("❌ Неверная сумма")
                return
        
        # Получаем дату окончания подписки
        subscription_end = None
        if product_type == "subscription":
            try:
                days = int(input("📅 Срок подписки в днях (0 для бессрочной): ") or "30")
                if days > 0:
                    subscription_end = datetime.utcnow() + timedelta(days=days)
                    print(f"📅 Подписка будет действовать до: {subscription_end}")
                else:
                    print("📅 Подписка будет бессрочной")
            except ValueError:
                print("❌ Неверный срок")
                return
        
        # Подтверждение
        print(f"\n📋 БУДЕТ ИСПРАВЛЕНО:")
        print(f"   🎨 Тип: {product_type} ({product_name})")
        print(f"   📊 Статус: {status}")
        print(f"   💰 Сумма: {amount} RUB")
        if subscription_end:
            print(f"   📅 Окончание подписки: {subscription_end}")
        
        confirm = input("\nПродолжить? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ Операция отменена")
            return
        
        # Обновляем данные пользователя
        update_data = {
            "product_type": product_type,
            "status": status,
            "amount": amount,
            "updated_at": datetime.utcnow()
        }
        
        if subscription_end:
            update_data["subscription_end"] = subscription_end
        
        result = user_auth.pre_subscriptions_collection.update_one(
            {"email": email},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            print(f"✅ Данные пользователя {email} успешно исправлены!")
            print(f"   🎨 Тип: {product_type}")
            print(f"   📊 Статус: {status}")
            print(f"   💰 Сумма: {amount} RUB")
            if subscription_end:
                print(f"   📅 Подписка до: {subscription_end}")
        else:
            print(f"❌ Не удалось обновить данные пользователя {email}")
            
    except Exception as e:
        print(f"❌ Ошибка при исправлении данных: {str(e)}")

def fix_all_subscriptions():
    """Массово исправляет все подписки с неправильными данными"""
    print("\n🔧🔧 МАССОВОЕ ИСПРАВЛЕНИЕ ПОДПИСОК")
    print("-" * 40)
    
    print("🔍 Ищем всех пользователей с проблемными данными...")
    
    try:
        # Ищем всех пользователей, у которых отсутствует product_type или status
        problematic_users = list(user_auth.pre_subscriptions_collection.find({
            "$or": [
                {"product_type": {"$exists": False}},
                {"product_type": None},
                {"status": {"$exists": False}},
                {"status": None}
            ]
        }))
        
        if not problematic_users:
            print("✅ Все пользователи имеют правильные данные!")
            return
        
        print(f"⚠️ Найдено {len(problematic_users)} пользователей с проблемными данными:")
        print()
        
        for i, user in enumerate(problematic_users, 1):
            email = user.get('email', 'неизвестно')
            product_type = user.get('product_type', 'отсутствует')
            status = user.get('status', 'отсутствует')
            source = user.get('source', 'неизвестно')
            created_at = user.get('created_at', 'неизвестно')
            
            print(f"📋 ПОЛЬЗОВАТЕЛЬ {i}:")
            print(f"   📧 Email: {email}")
            print(f"   🎨 Тип: {product_type}")
            print(f"   📊 Статус: {status}")
            print(f"   📝 Источник: {source}")
            print(f"   📅 Создан: {created_at}")
            print()
        
        # Определяем настройки для массового исправления
        print("🎯 НАСТРОЙКИ МАССОВОГО ИСПРАВЛЕНИЯ:")
        print("1. 🔐 Все проблемные пользователи → Подписка на ИИ-стилиста")
        print("2. 🎨 Все проблемные пользователи → Цветовой гайд")
        print("3. 👗 Все проблемные пользователи → Гайд по Кибби")
        print("4. 🔍 Индивидуальный выбор для каждого")
        
        choice = input("Выберите режим (1-4): ").strip()
        
        if choice == "1":
            # Все → подписка
            product_type = "subscription"
            product_name = "подписка на ИИ-стилиста"
            status = "completed"
            
            try:
                amount = float(input("💰 Сумма подписки для всех (RUB): ") or "1000")
                days = int(input("📅 Срок подписки в днях для всех (0 для бессрочной): ") or "365")
            except ValueError:
                print("❌ Неверные значения")
                return
                
        elif choice == "2":
            # Все → цветовой гайд
            product_type = "color_guide"
            product_name = "цветовой гайд"
            status = "completed"
            amount = 0  # Бесплатно
            
        elif choice == "3":
            # Все → гайд по Кибби
            product_type = "kibbe_guide"
            product_name = "гайд по Кибби"
            status = "completed"
            amount = 0  # Бесплатно
            
        elif choice == "4":
            print("❌ Индивидуальный режим пока не реализован")
            return
            
        else:
            print("❌ Неверный выбор")
            return
        
        # Подтверждение
        print(f"\n📋 БУДЕТ ИСПРАВЛЕНО:")
        print(f"   🎨 Тип: {product_type} ({product_name})")
        print(f"   📊 Статус: {status}")
        print(f"   💰 Сумма: {amount} RUB")
        if product_type == "subscription" and days > 0:
            subscription_end = datetime.utcnow() + timedelta(days=days)
            print(f"   📅 Окончание подписки: {subscription_end}")
        print(f"   👥 Количество пользователей: {len(problematic_users)}")
        
        confirm = input("\nПродолжить массовое исправление? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ Операция отменена")
            return
        
        # Массовое исправление
        print(f"\n🔧 Начинаем массовое исправление...")
        success_count = 0
        
        for i, user in enumerate(problematic_users, 1):
            try:
                email = user.get('email')
                if not email:
                    print(f"⚠️ {i}/{len(problematic_users)}: пропущен (нет email)")
                    continue
                
                # Подготавливаем данные для обновления
                update_data = {
                    "product_type": product_type,
                    "status": status,
                    "amount": amount,
                    "updated_at": datetime.utcnow()
                }
                
                # Если это подписка, добавляем дату окончания
                if product_type == "subscription" and days > 0:
                    subscription_end = datetime.utcnow() + timedelta(days=days)
                    update_data["subscription_end"] = subscription_end
                
                # Обновляем пользователя
                result = user_auth.pre_subscriptions_collection.update_one(
                    {"email": email},
                    {"$set": update_data}
                )
                
                if result.modified_count > 0:
                    success_count += 1
                    print(f"✅ {i}/{len(problematic_users)}: {email} исправлен")
                else:
                    print(f"❌ {i}/{len(problematic_users)}: {email} - ошибка обновления")
                    
            except Exception as e:
                print(f"❌ {i}/{len(problematic_users)}: {email} - ошибка: {str(e)}")
        
        print(f"\n🎉 Массовое исправление завершено!")
        print(f"✅ Успешно исправлено: {success_count}/{len(problematic_users)}")
        
        if success_count > 0:
            print(f"\n🔍 Теперь можете проверить исправленных пользователей:")
            print(f"   - Пункт 7: Найти пользователя по email")
            print(f"   - Пункт 8: Проверить возможность отправки гайда")
        
    except Exception as e:
        print(f"❌ Ошибка при массовом исправлении: {str(e)}")

def check_guide_access():
    """Проверяет возможность отправки гайда для пользователя"""
    print("\n✅ ПРОВЕРКА ВОЗМОЖНОСТИ ОТПРАВКИ ГАЙДА")
    print("-" * 40)
    
    email = input("📧 Email пользователя: ").strip().lower()
    if not email:
        print("❌ Email не может быть пустым")
        return
    
    print("\n🎨 ВЫБЕРИТЕ ТИП ГАЙДА ДЛЯ ПРОВЕРКИ:")
    print("1. 🎨 Цветовой гайд")
    print("2. 👗 Гайд по Кибби")
    
    guide_type = input("Выберите тип (1 или 2): ").strip()
    
    if guide_type == "1":
        product_type = "color_guide"
        guide_name = "цветовой гайд"
    elif guide_type == "2":
        product_type = "kibbe_guide"
        guide_name = "гайд по Кибби"
    else:
        print("❌ Неверный выбор")
        return
    
    try:
        print(f"\n🔍 Проверяем возможность отправки {guide_name} для {email}...")
        
        # Проверяем возможность отправки гайда
        can_send = user_auth.can_send_guide(email, product_type)
        
        if can_send:
            print(f"✅ Пользователь {email} МОЖЕТ получить {guide_name}")
            
            # Проверяем, почему можно отправить
            # 1. Прямая покупка гайда
            guide_purchase = user_auth.pre_subscriptions_collection.find_one({
                "email": email,
                "product_type": product_type,
                "subscription_end": None,
                "status": "completed",
                "guide_data.sent": False
            })
            
            if guide_purchase:
                print(f"   🎯 Причина: Прямая покупка {guide_name}")
                if guide_purchase.get('amount', 0) > 0:
                    print(f"   💰 Сумма: {guide_purchase.get('amount')} RUB")
                else:
                    print(f"   💰 Сумма: БЕСПЛАТНО")
            
            # 2. Действующая подписка
            subscription = user_auth.pre_subscriptions_collection.find_one({
                "email": email,
                "product_type": "subscription",
                "status": "completed",
                "subscription_end": {"$gt": datetime.utcnow()}
            })
            
            if subscription:
                print(f"   🎯 Причина: Действующая подписка на ИИ-стилиста")
                print(f"   📅 Подписка действует до: {subscription.get('subscription_end')}")
                print(f"   🎁 Бонус: {guide_name} предоставляется БЕСПЛАТНО!")
            
        else:
            print(f"❌ Пользователь {email} НЕ МОЖЕТ получить {guide_name}")
            
            # Проверяем, почему нельзя отправить
            # 1. Проверяем, был ли уже отправлен гайд
            guide_sent = user_auth.pre_subscriptions_collection.find_one({
                "email": email,
                "product_type": product_type,
                "guide_data.sent": True
            })
            
            if guide_sent:
                print(f"   🚫 Причина: {guide_name} уже был отправлен")
                print(f"   📅 Дата отправки: {guide_sent.get('guide_data', {}).get('sent_at', 'неизвестно')}")
            
            # 2. Проверяем подписку
            subscription = user_auth.pre_subscriptions_collection.find_one({
                "email": email,
                "product_type": "subscription",
                "status": "completed"
            })
            
            if subscription:
                subscription_end = subscription.get('subscription_end')
                if subscription_end and subscription_end <= datetime.utcnow():
                    print(f"   🚫 Причина: Подписка на ИИ-стилиста истекла")
                    print(f"   📅 Подписка действовала до: {subscription_end}")
                else:
                    print(f"   🚫 Причина: Неизвестно (подписка активна)")
            else:
                print(f"   🚫 Причина: Нет покупки гайда и нет подписки на ИИ-стилиста")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {str(e)}")

def main():
    """Главная функция"""
    print_banner()
    
    # Подключаемся к MongoDB
    print("🔌 Подключение к MongoDB...")
    if not user_auth.connect():
        print("❌ Не удалось подключиться к MongoDB")
        print("Проверьте настройки подключения в mongo_config.py")
        return
    
    print("✅ MongoDB подключена успешно!")
    print()
    
    while True:
        print_menu()
        choice = input("Выберите действие (0-6): ").strip()
        
        if choice == "0":
            print("👋 До свидания!")
            break
        elif choice == "1":
            add_single_user()
        elif choice == "2":
            add_users_from_file()
        elif choice == "3":
            add_users_list()
        elif choice == "4":
            view_all_users()
        elif choice == "5":
            delete_user()
        elif choice == "6":
            show_stats()
        elif choice == "7":
            find_user_by_email()
        elif choice == "8":
            check_guide_access()
        elif choice == "9":
            fix_user_data()
        elif choice == "10":
            fix_all_subscriptions()
        else:
            print("❌ Неверный выбор. Попробуйте снова.")
        
        input("\nНажмите Enter для продолжения...")
        print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    main() 