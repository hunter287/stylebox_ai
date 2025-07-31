import pandas as pd
import json
import re
from datetime import datetime
from mongo_config import mongo_config
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MongoImporter:
    def __init__(self):
        self.mongo_config = mongo_config
        self.imported_count = 0
        self.errors_count = 0
        self.updated_count = 0
    
    def parse_description_json(self, description_str):
        """Парсит JSON строку с описанием и характеристиками"""
        if not description_str or pd.isna(description_str):
            return {}
        
        try:
            # Убираем лишние символы и парсим JSON
            description_str = description_str.strip()
            if description_str.startswith('{') and description_str.endswith('}'):
                return json.loads(description_str)
            else:
                return {"Description": description_str}
        except json.JSONDecodeError as e:
            logger.warning(f"Ошибка парсинга JSON: {e}")
            return {"Description": description_str}
    
    def parse_array_field(self, field_value):
        """Парсит поле, которое может содержать массив значений"""
        if pd.isna(field_value) or not field_value:
            return []
        
        # Если это строка, пробуем распарсить как JSON
        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value)
                if isinstance(parsed, list):
                    return parsed
                else:
                    return [parsed] if parsed else []
            except json.JSONDecodeError:
                # Если не JSON, разбиваем по запятой
                return [item.strip() for item in field_value.split(',') if item.strip()]
        
        return [field_value] if field_value else []
    
    def convert_to_mongo_document(self, row):
        """Конвертирует строку Excel в документ MongoDB"""
        try:
            # Парсим описание
            description = self.parse_description_json(row.get('Описание', ''))
            
            # Парсим массивы
            color_types = self.parse_array_field(row.get('Цветотип', ''))
            kibbe_types = self.parse_array_field(row.get('Типы_Киббе', ''))
            body_types = self.parse_array_field(row.get('Типы_телосложения', ''))
            heights = self.parse_array_field(row.get('Росты', ''))
            tags = self.parse_array_field(row.get('Теги', ''))
            
            # Создаем документ MongoDB
            document = {
                "name": str(row.get('Название', '')).strip(),
                "brand": str(row.get('Бренд', '')).strip(),
                "price": float(row.get('Цена', 0)) if pd.notna(row.get('Цена')) else 0,
                "currency": str(row.get('Валюта', 'RUB')).strip(),
                "url": str(row.get('URL_товара', '')).strip(),
                "imageUrl": str(row.get('URL_изображения', '')).strip(),
                "category": str(row.get('Категория', '')).strip(),
                "subcategory": str(row.get('Подкатегория', '')).strip(),
                "status": str(row.get('Статус', 'available')).strip(),
                
                # JSON описание - нативно в MongoDB
                "description": description,
                
                # Массивы для множественных значений
                "colorTypes": color_types,
                "kibbeTypes": kibbe_types,
                "bodyTypes": body_types,
                "heights": heights,
                "tags": tags,
                
                # Метаданные
                "createdAt": datetime.now(),
                "updatedAt": datetime.now(),
                "source": "lamoda"
            }
            
            # Убираем пустые поля
            document = {k: v for k, v in document.items() if v not in ['', [], {}, None]}
            
            return document
            
        except Exception as e:
            logger.error(f"Ошибка конвертации строки: {e}")
            return None
    
    def import_excel_to_mongo(self, excel_file):
        """Импортирует данные из Excel файла в MongoDB"""
        try:
            print(f"📖 Читаем Excel файл: {excel_file}")
            df = pd.read_excel(excel_file)
            print(f"📊 Найдено {len(df)} товаров в файле")
            
            # Подключаемся к MongoDB
            if not self.mongo_config.connect():
                return False
            
            # Создаем индексы
            self.mongo_config.create_indexes()
            
            print("🚀 Начинаем импорт в MongoDB...")
            
            for index, row in df.iterrows():
                try:
                    # Конвертируем в документ MongoDB
                    document = self.convert_to_mongo_document(row)
                    
                    if not document:
                        self.errors_count += 1
                        continue
                    
                    # Проверяем, существует ли уже товар с таким URL
                    existing = self.mongo_config.collection.find_one({"url": document["url"]})
                    
                    if existing:
                        # Обновляем существующий документ
                        self.mongo_config.collection.update_one(
                            {"url": document["url"]},
                            {
                                "$set": {
                                    **document,
                                    "updatedAt": datetime.now()
                                }
                            }
                        )
                        self.updated_count += 1
                        print(f"🔄 Обновлен: {document['name']}")
                    else:
                        # Вставляем новый документ
                        self.mongo_config.collection.insert_one(document)
                        self.imported_count += 1
                        print(f"✅ Импортирован: {document['name']}")
                    
                    # Показываем прогресс каждые 10 товаров
                    if (index + 1) % 10 == 0:
                        print(f"📈 Прогресс: {index + 1}/{len(df)} ({(index + 1)/len(df)*100:.1f}%)")
                
                except Exception as e:
                    logger.error(f"Ошибка импорта товара {index + 1}: {e}")
                    self.errors_count += 1
                    continue
            
            # Получаем статистику
            self.mongo_config.get_stats()
            
            print("\n🎉 Импорт завершен!")
            print(f"📊 Результаты:")
            print(f"   ✅ Импортировано: {self.imported_count}")
            print(f"   🔄 Обновлено: {self.updated_count}")
            print(f"   ❌ Ошибок: {self.errors_count}")
            print(f"   📈 Всего: {self.imported_count + self.updated_count}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка импорта: {e}")
            return False
        
        finally:
            self.mongo_config.close()
    
    def test_queries(self):
        """Тестирует различные запросы к MongoDB"""
        try:
            print("\n🧪 Тестируем запросы к MongoDB...")
            
            if not self.mongo_config.connect():
                return
            
            collection = self.mongo_config.collection
            
            # 1. Поиск по бренду
            print("\n1️⃣ Поиск товаров бренда 'Sela':")
            sela_products = collection.find({"brand": "Sela"}).limit(3)
            for product in sela_products:
                print(f"   - {product['name']} ({product['price']} ₽)")
            
            # 2. Поиск по ценовому диапазону
            print("\n2️⃣ Товары от 1000 до 5000 ₽:")
            price_products = collection.find({
                "price": {"$gte": 1000, "$lte": 5000}
            }).limit(3)
            for product in price_products:
                print(f"   - {product['name']} ({product['price']} ₽)")
            
            # 3. Поиск по цветотипу
            print("\n3️⃣ Товары для цветотипа 'весна':")
            spring_products = collection.find({"colorTypes": "весна"}).limit(3)
            for product in spring_products:
                print(f"   - {product['name']} (цветотипы: {product.get('colorTypes', [])})")
            
            # 4. Поиск по типу ткани
            print("\n4️⃣ Товары из трикотажа:")
            fabric_products = collection.find({"description.Тип ткани": "Трикотаж"}).limit(3)
            for product in fabric_products:
                print(f"   - {product['name']} (ткань: {product.get('description', {}).get('Тип ткани', 'N/A')})")
            
            # 5. Сложный поиск
            print("\n5️⃣ Сложный поиск: Sela, 1000-5000₽, весна:")
            complex_products = collection.find({
                "brand": "Sela",
                "price": {"$gte": 1000, "$lte": 5000},
                "colorTypes": "весна"
            }).limit(3)
            for product in complex_products:
                print(f"   - {product['name']} ({product['price']} ₽)")
            
            # 6. Статистика по брендам
            print("\n6️⃣ Статистика по брендам:")
            brand_stats = collection.aggregate([
                {"$group": {"_id": "$brand", "count": {"$sum": 1}, "avgPrice": {"$avg": "$price"}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ])
            for stat in brand_stats:
                print(f"   - {stat['_id']}: {stat['count']} товаров, средняя цена: {stat['avgPrice']:.0f} ₽")
            
            print("\n✅ Тестирование запросов завершено!")
            
        except Exception as e:
            logger.error(f"Ошибка тестирования: {e}")
        
        finally:
            self.mongo_config.close()

def main():
    """Основная функция"""
    importer = MongoImporter()
    
    # Импортируем данные
    excel_file = "lamoda_with_descriptions_20250723_222810.xlsx"
    success = importer.import_excel_to_mongo(excel_file)
    
    if success:
        # Тестируем запросы
        importer.test_queries()

if __name__ == "__main__":
    main() 