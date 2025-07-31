#!/usr/bin/env python3
"""
Скрипт для парсинга товаров из Excel файла с последующим поиском визуально похожих товаров
Использование: python run_excel_enhanced_parser.py [start_row]
Пример: python run_excel_enhanced_parser.py 208  # начать с 208-й строки
"""

import asyncio
import pandas as pd
import sys
import argparse
from enhanced_similar_parser import EnhancedSimilarParser
from mongo_config import mongo_config
from datetime import datetime

def parse_array_field(field_value):
    """Парсит поле с массивами из Excel (разделитель - запятая)"""
    if pd.isna(field_value) or field_value == '':
        return []
    
    # Преобразуем в строку и разделяем по запятой
    if isinstance(field_value, str):
        items = [item.strip() for item in field_value.split(',') if item.strip()]
    else:
        items = [str(field_value).strip()]
    
    return items

def convert_excel_row_to_product_data(row):
    """Конвертирует строку Excel в данные товара"""
    try:
        # Парсим массивы
        color_types = parse_array_field(row.get('Цветотип', ''))
        kibbe_types = parse_array_field(row.get('Типы_Киббе', ''))
        body_types = parse_array_field(row.get('Типы_телосложения', ''))
        heights = parse_array_field(row.get('Росты', ''))
        
        # Создаем базовые данные товара
        product_data = {
            'name': str(row.get('Название', '')).strip(),
            'brand': str(row.get('Бренд', '')).strip(),
            'price': float(row.get('Цена', 0)) if pd.notna(row.get('Цена')) else 0,
            'currency': str(row.get('Валюта', 'RUB')).strip(),
            'url': str(row.get('URL_товара', '')).strip(),
            'imageUrl': str(row.get('URL_изображения', '')).strip(),
            'category': str(row.get('Категория', '')).strip(),
            'subcategory': str(row.get('Подкатегория', '')).strip(),
            'status': str(row.get('Статус', 'available')).strip(),
            'description': str(row.get('Описание', '')).strip(),
            
            # Массивы для множественных значений
            'colorTypes': color_types,
            'kibbeTypes': kibbe_types,
            'bodyTypes': body_types,
            'heights': heights,
            
            # Метаданные
            'createdAt': datetime.now(),
            'updatedAt': datetime.now(),
            'source': 'excel_import'
        }
        
        # Убираем пустые поля
        product_data = {k: v for k, v in product_data.items() if v not in ['', [], {}, None]}
        
        return product_data
        
    except Exception as e:
        print(f"❌ Ошибка конвертации строки Excel: {e}")
        return None

async def process_excel_products(start_row=1):
    """Обрабатывает товары из Excel файла и находит визуально похожие"""
    parser = EnhancedSimilarParser()
    
    try:
        print("🚀 Запуск парсинга товаров из Excel файла...")
        print(f"📍 Начинаем с строки Excel файла: {start_row}")
        
        # Подключаемся к браузеру
        if not await parser.start_browser():
            print("❌ Не удалось подключиться к браузеру")
            return False
        
        # Подключаемся к MongoDB
        mongo_config.connect()
        
        # Создаем коллекцию products_enhanced если её нет
        if not hasattr(mongo_config, 'collection_enhanced'):
            mongo_config.collection_enhanced = mongo_config.db['products_enhanced']
            print("✅ Коллекция products_enhanced настроена")
        
        # Читаем Excel файл
        print("📖 Читаем Excel файл...")
        df = pd.read_excel('product_import_template_02.xlsx')
        
        print(f"📊 Всего строк в Excel файле: {len(df)}")
        
        # Проверяем валидность start_row
        if start_row < 1:
            print("❌ Номер строки должен быть больше 0")
            return False
        
        if start_row > len(df):
            print(f"❌ Номер строки ({start_row}) больше количества строк в Excel файле ({len(df)})")
            return False
        
        # Проверяем, есть ли URL в указанной строке
        target_row = df.iloc[start_row - 1]
        if pd.isna(target_row.get('URL_товара')) or str(target_row.get('URL_товара', '')).strip() == '':
            print(f"❌ Строка {start_row} не содержит URL товара")
            print(f"   URL: {target_row.get('URL_товара', 'N/A')}")
            return False
        
        print(f"✅ Строка {start_row} содержит URL товара: {target_row.get('URL_товара')}")
        
        # Фильтруем строки с данными (ищем строки с URL товара)
        df_filtered = df[df['URL_товара'].notna() & (df['URL_товара'] != '')]
        
        print(f"📊 Найдено товаров с URL: {len(df_filtered)}")
        
        # Находим индекс указанной строки в отфильтрованном DataFrame
        target_index = None
        for i, (index, row) in enumerate(df_filtered.iterrows()):
            if index == start_row - 1:  # Это та же строка
                target_index = i
                break
        
        if target_index is None:
            print(f"❌ Строка {start_row} не найдена в списке товаров с URL")
            return False
        
        print(f"📊 Строка {start_row} соответствует товару #{target_index + 1} в списке товаров с URL")
        
        # Берем только товары с указанной позиции
        remaining_products = df_filtered.iloc[target_index:]
        total_remaining = len(remaining_products)
        
        print(f"📊 Осталось обработать: {total_remaining} товаров (с позиции {target_index + 1})")
        
        # Обрабатываем все товары из Excel файла
        total_added = 0
        total_skipped = 0
        
        print(f"\n🚀 Начинаем обработку {total_remaining} товаров из Excel файла...")
        
        for i, (index, row) in enumerate(remaining_products.iterrows()):
            current_row_number = start_row + i
            current_product_number = target_index + i + 1
            try:
                print(f"\n{'='*60}")
                print(f"📦 Обрабатываем товар #{current_product_number} (Excel строка {index + 1}) - {i + 1}/{total_remaining}")
                print(f"{'='*60}")
                
                # Конвертируем строку Excel в данные товара
                source_product_data = convert_excel_row_to_product_data(row)
                
                if not source_product_data:
                    print(f"❌ Не удалось конвертировать данные товара из Excel (строка {index + 1})")
                    total_skipped += 1
                    continue
                
                print(f"✅ Данные товара из Excel:")
                print(f"   Название: {source_product_data.get('name', 'N/A')}")
                print(f"   Бренд: {source_product_data.get('brand', 'N/A')}")
                print(f"   URL: {source_product_data.get('url', 'N/A')}")
                print(f"   Цветотипы: {source_product_data.get('colorTypes', [])}")
                print(f"   Типы Киббе: {source_product_data.get('kibbeTypes', [])}")
                print(f"   Типы телосложения: {source_product_data.get('bodyTypes', [])}")
                print(f"   Росты: {source_product_data.get('heights', [])}")
                
                # Проверяем, не обрабатывали ли мы уже этот товар
                existing_product = mongo_config.collection_enhanced.find_one({'url': source_product_data['url']})
                if existing_product:
                    print(f"⚠️ Товар уже был обработан ранее:")
                    print(f"   Название: {existing_product.get('name', 'N/A')}")
                    print(f"   Бренд: {existing_product.get('brand', 'N/A')}")
                    total_skipped += 1
                    continue
                
                # Обрабатываем исходный товар и находим похожие
                # Передаем атрибуты из Excel для копирования к похожим товарам
                added_count = await parser.process_source_product_with_attributes(
                    source_product_data['url'], 
                    source_product_data.get('colorTypes', []),
                    source_product_data.get('kibbeTypes', []),
                    source_product_data.get('bodyTypes', []),
                    source_product_data.get('heights', [])
                )
                
                total_added += added_count
                
                # Пауза между товарами
                if i < total_remaining - 1:
                    pause = 5  # 5 секунд между товарами
                    print(f"\n⏸️ Пауза {pause}с перед следующим товаром...")
                    await asyncio.sleep(pause)
                
            except Exception as e:
                print(f"❌ Ошибка обработки товара #{current_product_number}: {e}")
                total_skipped += 1
                continue
        
        print(f"\n{'='*60}")
        print(f"📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
        print(f"{'='*60}")
        print(f"   Обработано товаров: {total_remaining - total_skipped}")
        print(f"   Пропущено: {total_skipped}")
        print(f"   Добавлено похожих товаров: {total_added}")
        
        # Проверяем содержимое коллекции
        total_docs = mongo_config.collection_enhanced.count_documents({})
        print(f"   Всего документов в коллекции products_enhanced: {total_docs}")
        
        print("\n🎉 Обработка всех товаров завершена успешно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при обработке Excel файла: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await parser.close()

def parse_arguments():
    """Парсит аргументы командной строки"""
    parser = argparse.ArgumentParser(
        description='Парсинг товаров из Excel файла с поиском похожих товаров',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python run_excel_enhanced_parser.py          # начать с первой строки
  python run_excel_enhanced_parser.py 208      # начать с 208-й строки
  python run_excel_enhanced_parser.py 250      # начать с последней строки
        """
    )
    
    parser.add_argument(
        'start_row', 
        nargs='?', 
        type=int, 
        default=1,
        help='Номер строки для начала парсинга (по умолчанию: 1)'
    )
    
    return parser.parse_args()

async def main():
    """Основная функция"""
    args = parse_arguments()
    
    print(f"🚀 Запуск парсинга с строки {args.start_row}")
    
    success = await process_excel_products(args.start_row)
    
    if success:
        print("\n✅ Парсинг завершен успешно!")
        print("🚀 Можно запускать обработку всех товаров")
    else:
        print("\n❌ Парсинг завершен с ошибками")
        print("🔧 Требуется исправление перед запуском")

if __name__ == "__main__":
    asyncio.run(main()) 