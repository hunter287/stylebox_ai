#!/usr/bin/env python3
"""
Скрипт для управления предварительными подписками.

Поддерживает два режима:
1) Непосредственное добавление через аргументы командной строки:
   python add_pre_subscriptions.py --email user@example.com --until 2025-12-31 [--source manual] [--notes "..."]

2) Интерактивное меню (если аргументы не указаны).
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from user_auth import user_auth

def add_pre_subscription_from_input():
    """Добавляет предварительную подписку через интерактивный ввод"""
    print("=== Добавление предварительной подписки ===")
    
    # Подключаемся к MongoDB
    if not user_auth.connect():
        print("❌ Ошибка подключения к MongoDB")
        return False
    
    # Получаем данные от пользователя
    email = input("Введите email: ").strip().lower()
    if not email:
        print("❌ Email не может быть пустым")
        return False
    
    # Проверяем формат email
    if '@' not in email:
        print("❌ Неверный формат email")
        return False
    
    # Получаем дату окончания подписки
    while True:
        end_date_str = input("Введите дату окончания подписки (YYYY-MM-DD): ").strip()
        try:
            subscription_end = datetime.strptime(end_date_str, '%Y-%m-%d')
            break
        except ValueError:
            print("❌ Неверный формат даты. Используйте YYYY-MM-DD")
    
    # Получаем источник подписки
    source = input("Введите источник подписки (по умолчанию 'manual'): ").strip() or 'manual'
    
    # Получаем заметки
    notes = input("Введите заметки (необязательно): ").strip() or None
    
    # Добавляем предварительную подписку
    result = user_auth.add_pre_subscription(email, subscription_end, source, notes)
    
    if result['success']:
        print(f"✅ Предварительная подписка добавлена для {email}")
        print(f"   Действует до: {subscription_end.strftime('%Y-%m-%d')}")
        print(f"   ID: {result['subscription_id']}")
        return True
    else:
        print(f"❌ Ошибка: {result['error']}")
        return False

def add_pre_subscription_via_args(email: str, until: str, source: str = 'manual', notes: str | None = None) -> bool:
    """Добавляет предварительную подписку на основе аргументов командной строки.

    :param email: Email пользователя
    :param until: Дата окончания подписки в формате YYYY-MM-DD
    :param source: Источник подписки (по умолчанию manual)
    :param notes: Заметки (опционально)
    :return: True при успехе, иначе False
    """
    print("=== Добавление предварительной подписки (CLI) ===")

    # Подключаемся к MongoDB
    if not user_auth.connect():
        print("❌ Ошибка подключения к MongoDB")
        return False

    email = (email or '').strip().lower()
    if not email or '@' not in email:
        print("❌ Неверный email")
        return False

    try:
        subscription_end = datetime.strptime(until.strip(), '%Y-%m-%d')
    except Exception:
        print("❌ Неверный формат даты. Используйте YYYY-MM-DD")
        return False

    source = (source or 'manual').strip() or 'manual'
    notes = (notes.strip() if isinstance(notes, str) else None) or None

    result = user_auth.add_pre_subscription(email, subscription_end, source, notes)
    if result['success']:
        print(f"✅ Предварительная подписка добавлена для {email}")
        print(f"   Действует до: {subscription_end.strftime('%Y-%m-%d')}")
        print(f"   Источник: {source}")
        if notes:
            print(f"   Заметки: {notes}")
        print(f"   ID: {result['subscription_id']}")
        return True
    else:
        print(f"❌ Ошибка: {result['error']}")
        return False

def add_multiple_pre_subscriptions():
    """Добавляет несколько предварительных подписок из файла"""
    print("=== Добавление предварительных подписок из файла ===")
    
    # Подключаемся к MongoDB
    if not user_auth.connect():
        print("❌ Ошибка подключения к MongoDB")
        return False
    
    filename = input("Введите путь к файлу с данными: ").strip()
    if not os.path.exists(filename):
        print(f"❌ Файл {filename} не найден")
        return False
    
    # Определяем формат файла
    print("\nВыберите формат файла:")
    print("1. Только email'ы (одна строка = один email)")
    print("2. CSV с email, датой, источником, заметками")
    print("3. CSV с email и датой")
    
    format_choice = input("Введите номер формата (1-3): ").strip()
    
    # Получаем дату окончания подписки для всех email'ов
    if format_choice == "1":
        while True:
            end_date_str = input("Введите дату окончания подписки для всех (YYYY-MM-DD): ").strip()
            try:
                subscription_end = datetime.strptime(end_date_str, '%Y-%m-%d')
                break
            except ValueError:
                print("❌ Неверный формат даты. Используйте YYYY-MM-DD")
        
        source = input("Введите источник подписки (по умолчанию 'manual'): ").strip() or 'manual'
        notes = input("Введите заметки для всех (необязательно): ").strip() or None
    
    success_count = 0
    error_count = 0
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):  # Пропускаем пустые строки и комментарии
                    continue
                
                if format_choice == "1":
                    # Формат: только email
                    email = line.strip().lower()
                    if '@' not in email:
                        print(f"❌ Строка {line_num}: неверный email - {email}")
                        error_count += 1
                        continue
                    
                    # Добавляем подписку
                    result = user_auth.add_pre_subscription(email, subscription_end, source, notes)
                    
                elif format_choice == "2":
                    # Формат: email,дата,источник,заметки
                    parts = line.split(',')
                    if len(parts) < 2:
                        print(f"❌ Строка {line_num}: неверный формат")
                        error_count += 1
                        continue
                    
                    email = parts[0].strip().lower()
                    end_date_str = parts[1].strip()
                    source = parts[2].strip() if len(parts) > 2 else 'manual'
                    notes = parts[3].strip() if len(parts) > 3 else None
                    
                    # Проверяем email
                    if '@' not in email:
                        print(f"❌ Строка {line_num}: неверный email - {email}")
                        error_count += 1
                        continue
                    
                    # Парсим дату
                    try:
                        subscription_end = datetime.strptime(end_date_str, '%Y-%m-%d')
                    except ValueError:
                        print(f"❌ Строка {line_num}: неверный формат даты - {end_date_str}")
                        error_count += 1
                        continue
                    
                    # Добавляем подписку
                    result = user_auth.add_pre_subscription(email, subscription_end, source, notes)
                    
                elif format_choice == "3":
                    # Формат: email,дата
                    parts = line.split(',')
                    if len(parts) < 2:
                        print(f"❌ Строка {line_num}: неверный формат")
                        error_count += 1
                        continue
                    
                    email = parts[0].strip().lower()
                    end_date_str = parts[1].strip()
                    source = 'manual'
                    notes = None
                    
                    # Проверяем email
                    if '@' not in email:
                        print(f"❌ Строка {line_num}: неверный email - {email}")
                        error_count += 1
                        continue
                    
                    # Парсим дату
                    try:
                        subscription_end = datetime.strptime(end_date_str, '%Y-%m-%d')
                    except ValueError:
                        print(f"❌ Строка {line_num}: неверный формат даты - {end_date_str}")
                        error_count += 1
                        continue
                    
                    # Добавляем подписку
                    result = user_auth.add_pre_subscription(email, subscription_end, source, notes)
                
                else:
                    print("❌ Неверный выбор формата")
                    return False
                
                if result['success']:
                    print(f"✅ Строка {line_num}: подписка добавлена для {email}")
                    success_count += 1
                else:
                    print(f"❌ Строка {line_num}: {result['error']}")
                    error_count += 1
        
        print(f"\n=== Результат ===")
        print(f"✅ Успешно добавлено: {success_count}")
        print(f"❌ Ошибок: {error_count}")
        
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        return False
    
    return True

def list_pre_subscriptions():
    """Показывает список предварительных подписок"""
    print("=== Список предварительных подписок ===")
    
    # Подключаемся к MongoDB
    if not user_auth.connect():
        print("❌ Ошибка подключения к MongoDB")
        return False
    
    # Получаем список подписок
    result = user_auth.list_pre_subscriptions(active_only=True)
    
    if result['success']:
        subscriptions = result['subscriptions']
        if not subscriptions:
            print("📝 Предварительных подписок не найдено")
        else:
            print(f"📝 Найдено {len(subscriptions)} предварительных подписок:")
            print("-" * 80)
            for sub in subscriptions:
                # subscription_end уже хранится как строка в формате ISO
                end_date = sub['subscription_end']
                # created_at может быть datetime объектом или строкой
                if hasattr(sub['created_at'], 'strftime'):
                    created = sub['created_at'].strftime('%Y-%m-%d %H:%M')
                else:
                    created = str(sub['created_at'])
                print(f"📧 {sub['email']}")
                print(f"   Действует до: {end_date}")
                print(f"   Источник: {sub.get('source', 'manual')}")
                if sub.get('notes'):
                    print(f"   Заметки: {sub['notes']}")
                print(f"   Создана: {created}")
                print("-" * 80)
    else:
        print(f"❌ Ошибка: {result['error']}")
        return False
    
    return True

def cleanup_expired_subscriptions():
    """Очищает истекшие предварительные подписки"""
    print("=== Очистка истекших предварительных подписок ===")
    
    # Подключаемся к MongoDB
    if not user_auth.connect():
        print("❌ Ошибка подключения к MongoDB")
        return False
    
    # Очищаем истекшие подписки
    result = user_auth.cleanup_expired_pre_subscriptions()
    
    if result['success']:
        print(f"✅ Очищено {result['cleaned_count']} истекших предварительных подписок")
    else:
        print(f"❌ Ошибка: {result['error']}")
        return False
    
    return True

def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description='Утилита для управления предварительными подписками')
    parser.add_argument('--email', help='Email пользователя для создания подписки')
    parser.add_argument('--until', help='Дата окончания подписки в формате YYYY-MM-DD')
    parser.add_argument('--source', default='manual', help="Источник подписки (по умолчанию 'manual')")
    parser.add_argument('--notes', help='Заметки (опционально)')
    args = parser.parse_args()

    # Режим: прямое добавление по аргументам
    if args.email or args.until or args.source != 'manual' or args.notes:
        if not args.email or not args.until:
            print("❌ Для прямого добавления укажите оба параметра: --email и --until (YYYY-MM-DD)")
            sys.exit(1)
        ok = add_pre_subscription_via_args(args.email, args.until, args.source, args.notes)
        sys.exit(0 if ok else 2)

    print("🔧 Утилита для управления предварительными подписками")
    print("=" * 50)
    
    while True:
        print("\nВыберите действие:")
        print("1. Добавить одну предварительную подписку")
        print("2. Добавить несколько подписок из файла")
        print("3. Показать список предварительных подписок")
        print("4. Очистить истекшие подписки")
        print("5. Выход")
        
        choice = input("\nВведите номер (1-5): ").strip()
        
        if choice == '1':
            add_pre_subscription_from_input()
        elif choice == '2':
            add_multiple_pre_subscriptions()
        elif choice == '3':
            list_pre_subscriptions()
        elif choice == '4':
            cleanup_expired_subscriptions()
        elif choice == '5':
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")

if __name__ == '__main__':
    main() 