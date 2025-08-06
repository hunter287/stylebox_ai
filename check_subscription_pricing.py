#!/usr/bin/env python3
"""
Скрипт для проверки настроек стоимости подписки
"""

import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def check_subscription_pricing():
    """Проверяет настройки стоимости подписки"""
    print("=== Проверка настроек стоимости подписки ===")
    
    # Получаем значения из переменных окружения
    subscription_price = os.getenv('SUBSCRIPTION_PRICE', '4990.00')
    subscription_price_special = os.getenv('SUBSCRIPTION_PRICE_SPECIAL', '4490.00')
    
    print(f"📊 Обычная стоимость подписки: {subscription_price} руб")
    print(f"🎯 Специальная стоимость подписки: {subscription_price_special} руб")
    
    # Проверяем, что значения являются числами
    try:
        price_float = float(subscription_price)
        special_price_float = float(subscription_price_special)
        
        print(f"✅ Обычная стоимость корректна: {price_float} руб")
        print(f"✅ Специальная стоимость корректна: {special_price_float} руб")
        
        # Проверяем, что специальная цена меньше обычной
        if special_price_float < price_float:
            print(f"✅ Специальная цена меньше обычной (скидка: {price_float - special_price_float} руб)")
        else:
            print("⚠️ Специальная цена не меньше обычной")
            
    except ValueError as e:
        print(f"❌ Ошибка в формате стоимости: {e}")
        return False
    
    # Проверяем наличие файла .env
    if os.path.exists('.env'):
        print("✅ Файл .env найден")
    else:
        print("⚠️ Файл .env не найден, используются значения по умолчанию")
    
    return True

def show_env_example():
    """Показывает пример настроек"""
    print("\n=== Пример настроек в .env ===")
    print("SUBSCRIPTION_PRICE=4990.00")
    print("SUBSCRIPTION_PRICE_SPECIAL=4490.00")
    print("\nДля изменения стоимости отредактируйте эти переменные в файле .env")

if __name__ == "__main__":
    print("🚀 Проверка настроек стоимости подписки")
    
    if check_subscription_pricing():
        print("\n✅ Настройки корректны!")
    else:
        print("\n❌ Обнаружены проблемы в настройках")
    
    show_env_example()
    
    print("\n✨ Проверка завершена!") 