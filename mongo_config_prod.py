import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

class MongoConfigProd:
    def __init__(self):
        # Настройки подключения к MongoDB для продакшена
        self.mongo_uri = os.getenv('MONGO_URI_PROD', 'mongodb://localhost:27018/')
        self.database_name = os.getenv('MONGO_DB_NAME_PROD', 'stylist_ai_prod')
        self.collection_name = os.getenv('MONGO_COLLECTION_PROD', 'products')
        
        # Создаем клиент
        self.client = None
        self.db = None
        self.collection = None
        self.collection_enhanced = None
    
    def connect(self):
        """Подключается к MongoDB для продакшена"""
        try:
            print(f"🔌 Подключаемся к MongoDB (PROD): {self.mongo_uri}")
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            self.collection_enhanced = self.db["products_enhanced"]
            
            # Проверяем подключение
            self.client.admin.command('ping')
            print(f"✅ Подключение к MongoDB (PROD) успешно!")
            print(f"📊 База данных: {self.database_name}")
            print(f"📋 Коллекция: {self.collection_name}")
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка подключения к MongoDB (PROD): {e}")
            return False
    
    def close(self):
        """Закрывает подключение к MongoDB"""
        if self.client:
            self.client.close()
            print("🔌 Подключение к MongoDB (PROD) закрыто")
    
    def create_indexes(self):
        """Создает индексы для быстрого поиска"""
        try:
            print("📈 Создаем индексы для быстрого поиска (PROD)...")
            
            # Основные индексы
            self.collection.create_index("brand")
            self.collection.create_index("price")
            self.collection.create_index("category")
            self.collection.create_index("url", unique=True)
            
            # Индексы для массивов (по отдельности)
            self.collection.create_index("colorTypes")
            self.collection.create_index("kibbeTypes")
            self.collection.create_index("bodyTypes")
            self.collection.create_index("heights")
            self.collection.create_index("tags")
            
            # Индексы для вложенных полей описания
            self.collection.create_index("description.Тип ткани")
            self.collection.create_index("description.Состав, %")
            self.collection.create_index("description.Сезон")
            self.collection.create_index("description.Цвет")
            
            # Составные индексы (без параллельных массивов)
            self.collection.create_index([("brand", 1), ("price", 1)])
            self.collection.create_index([("brand", 1), ("category", 1)])
            self.collection.create_index([("price", 1), ("category", 1)])
            
            print("✅ Индексы созданы успешно (PROD)!")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка создания индексов (PROD): {e}")
            return False
    
    def get_stats(self):
        """Получает статистику коллекции"""
        try:
            total_docs = self.collection.count_documents({})
            print(f"📊 Статистика коллекции {self.collection_name} (PROD):")
            print(f"   Всего документов: {total_docs}")
            
            # Статистика по брендам
            brand_stats = self.collection.aggregate([
                {"$group": {"_id": "$brand", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ])
            
            print("   Топ-5 брендов:")
            for stat in brand_stats:
                print(f"     {stat['_id']}: {stat['count']} товаров")
            
            return total_docs
            
        except Exception as e:
            print(f"❌ Ошибка получения статистики (PROD): {e}")
            return 0

# Создаем глобальный экземпляр конфигурации для продакшена
mongo_config_prod = MongoConfigProd() 