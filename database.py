from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import DATABASE_URL

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    analyses = relationship("ColorAnalysis", back_populates="user")

class ColorAnalysis(Base):
    __tablename__ = 'color_analyses'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    color_type = Column(String)
    image_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="analyses")

# Create database engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# MongoDB функции для работы с продуктами
from mongo_config import mongo_config

def get_products_for_recommendations(color_type=None, kibbe_type=None, body_type=None, 
                                   style_prefs=None, color_prefs=None, top_size=None, 
                                   bottom_size=None, foot_size=None, top_clothing=None, 
                                   bottom_clothing=None, additional_items=None):
    """
    Получает продукты из MongoDB для рекомендаций на основе критериев
    """
    try:
        # Подключаемся к MongoDB
        mongo_config.connect()
        
        # Сопоставление категорий анкеты с категориями БД
        category_mapping = {
            # Верхняя одежда
            'Платья': ['Платья и сарафаны', 'платья и сарафаны'],
            'Блузки': ['Блузы и рубашки', 'блузы и рубашки'],
            'Рубашки': ['Блузы и рубашки', 'блузы и рубашки'],
            'Свитеры': ['Джемперы, свитеры и кардиганы', 'джемперы, свитеры и кардиганы', 'Джемперы и кардиганы', 'джемперы и кардиганы'],
            'Свитшоты': ['Худи и свитшоты', 'худи и свитшоты'],
            'Лонгсливы': ['Футболки и поло', 'футболки и поло'],
            'Футболки': ['Футболки и поло', 'футболки и поло', 'футболки'],
            'Пиджаки': ['Пиджаки и костюмы', 'пиджаки и костюмы'],
            'Худи': ['Худи и свитшоты', 'худи и свитшоты'],
            'Кардиганы': ['Джемперы, свитеры и кардиганы', 'джемперы, свитеры и кардиганы', 'Джемперы и кардиганы', 'джемперы и кардиганы'],
            'Водолазки': ['Топы и майки', 'топы и майки'],
            
            # Нижняя одежда
            'Брюки': ['Брюки', 'брюки'],
            'Джинсы': ['Джинсы', 'джинсы'],
            'Юбки': ['Юбки', 'юбки'],
            'Шорты': ['Шорты', 'шорты'],
            
            # Дополнительные вещи
            'Обувь': ['обувь', 'Обувь'],
            'Сумки': ['сумки', 'Сумки'],
            'Украшения': ['украшения', 'Украшения']
        }
        
        # Функция для поиска ближайших размеров
        def find_nearest_sizes(target_size, available_sizes):
            """Находит ближайшие размеры к целевому"""
            if not target_size or not available_sizes:
                return available_sizes
            
            try:
                target_num = int(target_size)
                nearest_sizes = []
                
                for size in available_sizes:
                    # Извлекаем числа из размера (например, "40/42" -> [40, 42])
                    size_numbers = []
                    for part in size.split('/'):
                        for num in part.split():
                            if num.isdigit():
                                size_numbers.append(int(num))
                    
                    # Если размер содержит целевое число или близкое к нему
                    if target_num in size_numbers:
                        nearest_sizes.append(size)
                    elif any(abs(num - target_num) <= 2 for num in size_numbers):
                        nearest_sizes.append(size)
                
                return nearest_sizes if nearest_sizes else available_sizes
            except:
                return available_sizes
        
        # Получаем все доступные размеры из БД
        all_sizes_pipeline = [
            {'$unwind': '$sizes.Российский'},
            {'$group': {'_id': '$sizes.Российский'}},
            {'$sort': {'_id': 1}}
        ]
        all_available_sizes = [str(item['_id']) for item in mongo_config.collection.aggregate(all_sizes_pipeline)]
        
        # Находим ближайшие размеры для каждого запрошенного размера
        nearest_top_sizes = find_nearest_sizes(top_size, all_available_sizes) if top_size else []
        nearest_bottom_sizes = find_nearest_sizes(bottom_size, all_available_sizes) if bottom_size else []
        nearest_foot_sizes = find_nearest_sizes(foot_size, all_available_sizes) if foot_size else []
        
        # Собираем все подходящие размеры
        all_target_sizes = []
        if nearest_top_sizes:
            all_target_sizes.extend(nearest_top_sizes)
        if nearest_bottom_sizes:
            all_target_sizes.extend(nearest_bottom_sizes)
        if nearest_foot_sizes:
            all_target_sizes.extend(nearest_foot_sizes)
        
        # Убираем дубликаты
        all_target_sizes = list(set(all_target_sizes))
        
        # Собираем все категории для поиска
        all_category_filters = []
        if top_clothing:
            for category in top_clothing:
                if category in category_mapping:
                    all_category_filters.extend(category_mapping[category])
        if bottom_clothing:
            for category in bottom_clothing:
                if category in category_mapping:
                    all_category_filters.extend(category_mapping[category])
        if additional_items:
            for category in additional_items:
                if category in category_mapping:
                    all_category_filters.extend(category_mapping[category])
        
        # Убираем дубликаты категорий
        all_category_filters = list(set(all_category_filters))
        
        # Строим запрос
        query = {}
        
        # ПРИОРИТЕТ 1: Фильтрация по типу фигуры (самый важный критерий)
        if body_type:
            # Сопоставление типов фигуры с полями в БД (значения на русском языке)
            body_type_mapping = {
                'Яблоко': 'Яблоко',
                'Груша': 'Груша', 
                'Треугольник': 'Перевернутый треугольник',  # В БД называется "Перевернутый треугольник"
                'Прямоугольник': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)'],  # В БД есть два варианта
                'Песочные часы': 'Песочные часы'
            }
            
            db_body_types = body_type_mapping.get(body_type)
            if db_body_types:
                if isinstance(db_body_types, list):
                    # Для прямоугольника используем оба варианта
                    query['bodyTypes'] = {'$in': db_body_types}
                    print(f"🔍 Фильтруем по типу фигуры: {body_type} -> {db_body_types}")
                else:
                    query['bodyTypes'] = db_body_types
                    print(f"🔍 Фильтруем по типу фигуры: {body_type} -> {db_body_types}")
        
        # Если есть размеры, добавляем их в запрос
        if all_target_sizes:
            query['sizes.Российский'] = {'$in': all_target_sizes}
        
        # Если есть категории, добавляем их в запрос
        if all_category_filters:
            query['category'] = {'$in': all_category_filters}
        
        # Если нет ни размеров, ни категорий, получаем все товары
        if not query:
            query = {}
        
        # Получаем продукты
        products = list(mongo_config.collection.find(query).limit(200))  # Увеличиваем лимит для 20 рекомендаций
        
        # Преобразуем ObjectId в строки для JSON сериализации
        for product in products:
            if '_id' in product:
                product['_id'] = str(product['_id'])
        
        # Убираем дубликаты из результатов запроса
        unique_products = []
        used_ids = set()
        used_names = set()
        
        for product in products:
            product_id = product.get('_id')
            product_name = product.get('name')
            
            # Проверяем, что у нас есть и ID, и название
            if product_id and product_name:
                if product_id not in used_ids and product_name not in used_names:
                    unique_products.append(product)
                    used_ids.add(product_id)
                    used_names.add(product_name)
        
        print(f"🔍 Найдено {len(products)} товаров, после дедупликации: {len(unique_products)}")
        return unique_products
        
    except Exception as e:
        print(f"Ошибка получения продуктов: {e}")
        return [] 