import pandas as pd
import json
import re
from sqlalchemy.orm import Session
from database_config import SessionLocal, engine
from models import Product, ProductAttribute, Base
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataImporter:
    def __init__(self):
        self.db = SessionLocal()
        self.imported_count = 0
        self.errors_count = 0
    
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
                return {}
        except json.JSONDecodeError as e:
            logger.warning(f"Ошибка парсинга JSON: {e}")
            return {}
    
    def extract_category_from_name(self, name):
        """Извлекает категорию из названия товара"""
        if not name:
            return None
        
        name_lower = name.lower()
        
        # Определяем категорию по ключевым словам
        if any(word in name_lower for word in ['платье', 'dress']):
            return 'платье'
        elif any(word in name_lower for word in ['блуз', 'blouse', 'bluza']):
            return 'блузка'
        elif any(word in name_lower for word in ['рубаш', 'shirt', 'rubashka']):
            return 'рубашка'
        elif any(word in name_lower for word in ['джинс', 'jeans', 'dzhins']):
            return 'джинсы'
        elif any(word in name_lower for word in ['юбк', 'skirt', 'yubka']):
            return 'юбка'
        elif any(word in name_lower for word in ['жакет', 'jacket', 'zhaket']):
            return 'жакет'
        elif any(word in name_lower for word in ['пиджак', 'blazer']):
            return 'пиджак'
        elif any(word in name_lower for word in ['куртк', 'coat', 'kurtka']):
            return 'куртка'
        elif any(word in name_lower for word in ['пальт', 'overcoat', 'palto']):
            return 'пальто'
        elif any(word in name_lower for word in ['кардиган', 'cardigan']):
            return 'кардиган'
        elif any(word in name_lower for word in ['свитер', 'sweater', 'pulover']):
            return 'свитер'
        elif any(word in name_lower for word in ['топ', 'top']):
            return 'топ'
        elif any(word in name_lower for word in ['лонгслив', 'longsleeve']):
            return 'лонгслив'
        elif any(word in name_lower for word in ['футболк', 't-shirt', 'futbolka']):
            return 'футболка'
        elif any(word in name_lower for word in ['поло', 'polo']):
            return 'поло'
        elif any(word in name_lower for word in ['сарафан', 'sundress', 'sarafan']):
            return 'сарафан'
        elif any(word in name_lower for word in ['брюк', 'pants', 'bryuki']):
            return 'брюки'
        else:
            return 'одежда'
    
    def extract_subcategory_from_name(self, name, category):
        """Извлекает подкатегорию из названия товара"""
        if not name:
            return None
        
        name_lower = name.lower()
        
        # Определяем подкатегорию по ключевым словам
        if category == 'платье':
            if any(word in name_lower for word in ['вечерн', 'evening']):
                return 'вечернее платье'
            elif any(word in name_lower for word in ['повседневн', 'casual']):
                return 'повседневное платье'
            elif any(word in name_lower for word in ['делов', 'business']):
                return 'деловое платье'
            else:
                return 'повседневное платье'
        elif category == 'блузка':
            if any(word in name_lower for word in ['делов', 'business']):
                return 'деловая блузка'
            else:
                return 'повседневная блузка'
        elif category == 'рубашка':
            if any(word in name_lower for word in ['делов', 'business']):
                return 'деловая рубашка'
            else:
                return 'повседневная рубашка'
        
        return None
    
    def create_product_attributes(self, product, description_data):
        """Создает атрибуты товара из описания"""
        try:
            attributes = ProductAttribute(
                product_id=product.id,
                fabric=description_data.get('Тип ткани'),
                pattern=description_data.get('Узор'),
                season=description_data.get('Сезон'),
                features=description_data
            )
            
            # Извлекаем цвет
            color = description_data.get('Цвет')
            if color:
                attributes.primary_color = color
            
            # Определяем стиль по описанию
            description = description_data.get('Description', '').lower()
            if any(word in description for word in ['классич', 'classic']):
                attributes.style = 'классический'
            elif any(word in description for word in ['романтич', 'romantic']):
                attributes.style = 'романтичный'
            elif any(word in description for word in ['спортив', 'sport']):
                attributes.style = 'спортивный'
            elif any(word in description for word in ['бохо', 'boho']):
                attributes.style = 'бохо'
            else:
                attributes.style = 'повседневный'
            
            # Определяем силуэт
            silhouette = description_data.get('Тип силуэта')
            if silhouette:
                attributes.silhouette = silhouette
            else:
                attributes.silhouette = 'стандартный'
            
            # Определяем повод
            if any(word in description for word in ['делов', 'business', 'офис']):
                attributes.occasion = 'деловой'
            elif any(word in description for word in ['вечер', 'evening', 'выход']):
                attributes.occasion = 'вечерний'
            elif any(word in description for word in ['спорт', 'sport']):
                attributes.occasion = 'спортивный'
            else:
                attributes.occasion = 'повседневный'
            
            return attributes
            
        except Exception as e:
            logger.error(f"Ошибка создания атрибутов для товара {product.id}: {e}")
            return None
    
    def import_product(self, row):
        """Импортирует один товар в базу данных"""
        try:
            # Извлекаем данные из строки
            name = row['Название']
            brand = row['Бренд']
            price = row['Цена']
            url = row['URL_товара']
            image_url = row['URL_изображения']
            description_str = row['Описание']
            
            # Проверяем, существует ли товар
            existing_product = self.db.query(Product).filter(Product.url == url).first()
            if existing_product:
                logger.info(f"Товар уже существует: {name}")
                return existing_product
            
            # Парсим описание
            description_data = self.parse_description_json(description_str)
            
            # Определяем категорию и подкатегорию
            category = row.get('Категория') or self.extract_category_from_name(name)
            subcategory = row.get('Подкатегория') or self.extract_subcategory_from_name(name, category)
            
            # Создаем товар
            product = Product(
                name=name,
                brand=brand,
                price=float(price) if pd.notna(price) else None,
                currency='RUB',
                url=url,
                image_url=image_url if pd.notna(image_url) else None,
                category=category,
                subcategory=subcategory,
                status='available'
            )
            
            # Добавляем в базу данных
            self.db.add(product)
            self.db.flush()  # Получаем ID товара
            
            # Создаем атрибуты товара
            if description_data:
                attributes = self.create_product_attributes(product, description_data)
                if attributes:
                    self.db.add(attributes)
            
            self.imported_count += 1
            logger.info(f"✅ Импортирован товар {self.imported_count}: {name}")
            
            return product
            
        except Exception as e:
            self.errors_count += 1
            logger.error(f"❌ Ошибка импорта товара: {e}")
            return None
    
    def import_from_excel(self, filename):
        """Импортирует все товары из Excel файла"""
        try:
            logger.info(f"📁 Загружаем файл: {filename}")
            df = pd.read_excel(filename)
            total_count = len(df)
            logger.info(f"📊 Найдено {total_count} товаров для импорта")
            
            # Импортируем товары
            for index, row in df.iterrows():
                self.import_product(row)
                
                # Сохраняем каждые 10 товаров
                if (index + 1) % 10 == 0:
                    self.db.commit()
                    logger.info(f"💾 Сохранено {index + 1}/{total_count} товаров")
            
            # Финальное сохранение
            self.db.commit()
            
            logger.info(f"🎉 Импорт завершен!")
            logger.info(f"📊 Статистика:")
            logger.info(f"   Всего товаров: {total_count}")
            logger.info(f"   Импортировано: {self.imported_count}")
            logger.info(f"   Ошибок: {self.errors_count}")
            logger.info(f"   Успешность: {(self.imported_count / total_count * 100):.1f}%")
            
        except Exception as e:
            logger.error(f"❌ Ошибка импорта: {e}")
            self.db.rollback()
        finally:
            self.db.close()
    
    def check_existing_data(self):
        """Проверяет существующие данные в базе"""
        try:
            total_products = self.db.query(Product).count()
            total_attributes = self.db.query(ProductAttribute).count()
            
            logger.info(f"📊 Данные в базе:")
            logger.info(f"   Товаров: {total_products}")
            logger.info(f"   Атрибутов: {total_attributes}")
            
            return total_products, total_attributes
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки данных: {e}")
            return 0, 0

def main():
    """Основная функция"""
    importer = DataImporter()
    
    # Проверяем существующие данные
    logger.info("🔍 Проверяем существующие данные...")
    importer.check_existing_data()
    
    # Импортируем данные
    filename = "lamoda_with_descriptions_20250723_222810.xlsx"
    importer.import_from_excel(filename)
    
    # Финальная проверка
    logger.info("🔍 Финальная проверка данных...")
    final_importer = DataImporter()
    final_importer.check_existing_data()
    final_importer.db.close()

if __name__ == "__main__":
    main() 