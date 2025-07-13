from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database_config import Base

class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    color_type = Column(String)  # весна, лето, осень, зима
    kibbe_type = Column(String)  # романтик, гамин, классик, натурал, драматик
    body_type = Column(String)   # груша, яблоко, песочные часы, прямоугольник
    height = Column(String)      # до 160, 161-165, 166-170, 171-175, 176+
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Связи
    recommendations = relationship("Recommendation", back_populates="user")
    preferences = relationship("UserPreference", back_populates="user")

class Product(Base):
    """Модель товара"""
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    brand = Column(String)
    price = Column(Float)
    original_price = Column(Float)
    currency = Column(String, default="RUB")
    url = Column(String, unique=True, nullable=False)  # ссылка на товар в магазине
    image_url = Column(String)
    category = Column(String)  # платье, блузка, джинсы, юбка, пиджак, обувь
    subcategory = Column(String)  # повседневное платье, вечернее платье
    status = Column(String, default="available")  # available, out_of_stock, discontinued
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Связи
    attributes = relationship("ProductAttribute", back_populates="product", uselist=False)
    recommendations = relationship("Recommendation", back_populates="product")

class ProductAttribute(Base):
    """Атрибуты товара для рекомендаций"""
    __tablename__ = "product_attributes"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), unique=True)
    
    # Цветовые характеристики
    color_type = Column(String)  # весна, лето, осень, зима
    primary_color = Column(String)  # красный, синий, зеленый
    color_hex = Column(String)  # #FF0000
    
    # Стилевые характеристики
    kibbe_type = Column(String)  # романтик, гамин, классик, натурал, драматик
    style = Column(String)  # классический, романтичный, спортивный, бохо
    silhouette = Column(String)  # приталенный, свободный, оверсайз
    
    # Материалы и детали
    fabric = Column(String)  # хлопок, шелк, шерсть, джинс
    pattern = Column(String)  # однотонный, цветочный, геометрический
    occasion = Column(String)  # повседневный, деловой, вечерний, спортивный
    
    # Сезонность
    season = Column(String)  # весна, лето, осень, зима, всесезонный
    
    # Дополнительные характеристики
    features = Column(JSON)  # карманы, молния, пуговицы и т.д.
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Связи
    product = relationship("Product", back_populates="attributes")

class Recommendation(Base):
    """История рекомендаций"""
    __tablename__ = "recommendations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    score = Column(Float)  # оценка релевантности (0-1)
    reason = Column(String)  # причина рекомендации
    shown_at = Column(DateTime(timezone=True), server_default=func.now())
    clicked = Column(Boolean, default=False)
    clicked_at = Column(DateTime(timezone=True))
    
    # Связи
    user = relationship("User", back_populates="recommendations")
    product = relationship("Product", back_populates="recommendations")

class UserPreference(Base):
    """Предпочтения пользователя"""
    __tablename__ = "user_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    category = Column(String)  # платья, блузки, джинсы
    style = Column(String)  # классический, романтичный
    price_range_min = Column(Float)
    price_range_max = Column(Float)
    preferred_brands = Column(JSON)  # список брендов
    excluded_brands = Column(JSON)  # исключенные бренды
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Связи
    user = relationship("User", back_populates="preferences")

class Analytics(Base):
    """Аналитика взаимодействий"""
    __tablename__ = "analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String)
    event_type = Column(String)  # view, click, like, dislike, purchase
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    page_url = Column(String)
    user_agent = Column(String)
    ip_address = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Дополнительные данные события
    event_data = Column(JSON) 