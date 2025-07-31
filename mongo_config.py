import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

class MongoConfig:
    def __init__(self):
        # Настройки подключения к MongoDB
        self.mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        self.database_name = os.getenv('MONGO_DB_NAME', 'stylist_ai')
        self.collection_name = os.getenv('MONGO_COLLECTION', 'products')
        
        # Создаем клиент
        self.client = None
        self.db = None
        self.collection = None
        self.collection_enhanced = None
    
    def connect(self):
        """Подключается к MongoDB"""
        try:
            print(f"🔌 Подключаемся к MongoDB: {self.mongo_uri}")
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            self.collection_enhanced = self.db["products_enhanced"]
            
            # Проверяем подключение
            self.client.admin.command('ping')
            print(f"✅ Подключение к MongoDB успешно!")
            print(f"📊 База данных: {self.database_name}")
            print(f"📋 Коллекция: {self.collection_name}")
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка подключения к MongoDB: {e}")
            return False
    
    def close(self):
        """Закрывает подключение к MongoDB"""
        if self.client:
            self.client.close()
            print("🔌 Подключение к MongoDB закрыто")
    
    def create_indexes(self):
        """Создает индексы для быстрого поиска"""
        try:
            print("📈 Создаем индексы для быстрого поиска...")
            
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
            
            print("✅ Индексы созданы успешно!")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка создания индексов: {e}")
            return False
    
    def get_stats(self):
        """Получает статистику коллекции"""
        try:
            total_docs = self.collection.count_documents({})
            print(f"📊 Статистика коллекции {self.collection_name}:")
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
            print(f"❌ Ошибка получения статистики: {e}")
            return 0

# Создаем глобальный экземпляр конфигурации
mongo_config = MongoConfig() 