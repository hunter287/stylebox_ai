import os
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from pymongo import MongoClient
from bson import ObjectId
import logging
# Используем переменные окружения напрямую

logger = logging.getLogger(__name__)

class UserAuth:
    def __init__(self):
        self.mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        self.database_name = os.getenv('MONGO_DB_NAME', 'stylist_ai')
        self.client = None
        self.db = None
        self.users_collection = None
        self.sessions_collection = None
        self.pre_subscriptions_collection = None
        
    def connect(self):
        """Подключается к MongoDB"""
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.database_name]
            self.users_collection = self.db['users']
            self.sessions_collection = self.db['sessions']
            self.pre_subscriptions_collection = self.db['pre_subscriptions']
            
            # Создаем индексы
            self._create_indexes()
            
            logger.info("✅ Подключение к MongoDB для пользователей успешно!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к MongoDB: {e}")
            return False
    
    def _create_indexes(self):
        """Создает индексы для коллекций пользователей"""
        try:
            # Индексы для пользователей
            self.users_collection.create_index("email", unique=True)
            self.users_collection.create_index("username", unique=True)
            self.users_collection.create_index("created_at")
            
            # Индексы для сессий
            self.sessions_collection.create_index("session_id", unique=True)
            self.sessions_collection.create_index("user_id")
            self.sessions_collection.create_index("expires_at")
            
            # TTL индекс для автоматического удаления истекших сессий
            try:
                self.sessions_collection.create_index("expires_at", expireAfterSeconds=0)
            except Exception as e:
                # Если индекс уже существует с другими параметрами, игнорируем ошибку
                logger.warning(f"TTL индекс для сессий уже существует: {e}")
            
            # Индексы для токенов сброса пароля
            self.db.password_reset_tokens.create_index("token", unique=True)
            self.db.password_reset_tokens.create_index("email")
            self.db.password_reset_tokens.create_index("expires_at")
            self.db.password_reset_tokens.create_index("used")
            
            # Индексы для предварительных подписок
            self.pre_subscriptions_collection.create_index("email", unique=True)
            self.pre_subscriptions_collection.create_index("subscription_end")
            self.pre_subscriptions_collection.create_index("is_active")
            self.pre_subscriptions_collection.create_index("created_at")
            
            logger.info("✅ Индексы для пользователей созданы")
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания индексов: {e}")
    
    def _hash_password(self, password):
        """Хеширует пароль с солью"""
        salt = secrets.token_hex(16)
        hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return salt + hash_obj.hex()
    
    def _verify_password(self, password, hashed_password):
        """Проверяет пароль"""
        try:
            salt = hashed_password[:32]  # Первые 32 символа - соль
            hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
            return hashed_password == salt + hash_obj.hex()
        except Exception as e:
            logger.error(f"Ошибка проверки пароля: {e}")
            return False
    
    def _generate_session_id(self):
        """Генерирует уникальный ID сессии"""
        return secrets.token_urlsafe(32)
    
    def register_user(self, email, password, username=None):
        """Регистрирует нового пользователя"""
        try:
            email = email.strip().lower()
            
            # Проверяем, что email не занят
            existing_user = self.users_collection.find_one({"email": email})
            if existing_user:
                return {"success": False, "error": "Пользователь с таким email уже существует"}
            
            # Проверяем username если указан
            if username:
                username = username.strip()
                existing_username = self.users_collection.find_one({"username": username})
                if existing_username:
                    return {"success": False, "error": "Пользователь с таким именем уже существует"}
            
            # Проверяем наличие предварительной подписки
            pre_subscription_result = self.get_pre_subscription(email)
            subscription_end = None
            
            if pre_subscription_result["success"]:
                subscription_end = pre_subscription_result["subscription"]["subscription_end"]
                logger.info(f"🔑 Найдена предварительная подписка для {email}, действует до {subscription_end}")
            
            # Создаем пользователя
            user_data = {
                "email": email,
                "password_hash": self._hash_password(password),
                "username": username or email.split('@')[0],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True,
                "subscription_end": subscription_end,  # Автоматически присваиваем подписку если есть
                "profile": {
                    "color_type": None,
                    "kibbe_type": None,
                    "body_type": None,
                    "height": None,
                    "preferences": {}
                }
            }
            
            result = self.users_collection.insert_one(user_data)
            
            # Если была предварительная подписка, удаляем её из коллекции предварительных подписок
            if subscription_end:
                self.remove_pre_subscription(email)
                logger.info(f"✅ Предварительная подписка перенесена в аккаунт пользователя: {email}")
            
            logger.info(f"✅ Пользователь зарегистрирован: {email}")
            return {
                "success": True, 
                "user_id": str(result.inserted_id),
                "message": "Регистрация успешна" + (" (подписка активирована)" if subscription_end else ""),
                "has_subscription": subscription_end is not None
            }
            
        except Exception as e:
            logger.error(f"Ошибка регистрации пользователя: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}
    
    def authenticate_user(self, email, password):
        """Аутентифицирует пользователя"""
        try:
            email = email.strip().lower()
            
            # Ищем пользователя
            user = self.users_collection.find_one({"email": email})
            if not user:
                return {"success": False, "error": "Неверный email или пароль"}
            
            # Проверяем пароль
            if not self._verify_password(password, user["password_hash"]):
                return {"success": False, "error": "Неверный email или пароль"}
            
            # Проверяем активность аккаунта
            if not user.get("is_active", True):
                return {"success": False, "error": "Аккаунт заблокирован"}
            
            # Создаем сессию
            session_id = self._generate_session_id()
            session_data = {
                "session_id": session_id,
                "user_id": user["_id"],
                "email": user["email"],
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(days=30),  # Сессия на 30 дней
                "ip_address": None,  # Можно добавить IP адрес
                "user_agent": None   # Можно добавить User-Agent
            }
            
            self.sessions_collection.insert_one(session_data)
            
            logger.info(f"✅ Пользователь авторизован: {email}")
            return {
                "success": True,
                "session_id": session_id,
                "user": {
                    "id": str(user["_id"]),
                    "email": user["email"],
                    "username": user["username"],
                    "subscription_end": user.get("subscription_end")
                }
            }
            
        except Exception as e:
            logger.error(f"Ошибка аутентификации: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}
    
    def get_user_by_session(self, session_id):
        """Получает пользователя по ID сессии"""
        try:
            session_data = self.sessions_collection.find_one({
                "session_id": session_id,
                "expires_at": {"$gt": datetime.utcnow()}
            })
            
            if not session_data:
                return None
            
            user_id = session_data.get("user_id")
            if not user_id:
                return None
            
            user = self.users_collection.find_one({"_id": user_id})
            return user
            
        except Exception as e:
            logger.error(f"Ошибка получения пользователя по сессии: {e}")
            return None

    def get_user_by_id(self, user_id):
        """Получает пользователя по ID"""
        try:
            if isinstance(user_id, str):
                user_id = ObjectId(user_id)
            
            user = self.users_collection.find_one({"_id": user_id})
            return user
            
        except Exception as e:
            logger.error(f"Ошибка получения пользователя по ID: {e}")
            return None
    
    def logout_user(self, session_id):
        """Выход пользователя"""
        try:
            result = self.sessions_collection.delete_one({"session_id": session_id})
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Ошибка выхода пользователя: {e}")
            return False
    
    def update_user_profile(self, user_id, profile_data):
        """Обновляет профиль пользователя"""
        try:
            user_id = ObjectId(user_id)
            
            update_data = {
                "updated_at": datetime.utcnow(),
                "profile": profile_data
            }
            
            result = self.users_collection.update_one(
                {"_id": user_id},
                {"$set": update_data}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Ошибка обновления профиля: {e}")
            return False
    
    def check_subscription(self, user_id):
        """Проверяет активность подписки пользователя"""
        try:
            user_id = ObjectId(user_id)
            user = self.users_collection.find_one({"_id": user_id})
            
            if not user:
                return False
            
            subscription_end = user.get("subscription_end")
            if not subscription_end:
                return False
            
            return subscription_end > datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Ошибка проверки подписки: {e}")
            return False
    
    def update_subscription(self, user_id, end_date):
        """Обновляет дату окончания подписки"""
        try:
            user_id = ObjectId(user_id)
            
            result = self.users_collection.update_one(
                {"_id": user_id},
                {"$set": {
                    "subscription_end": end_date,
                    "updated_at": datetime.utcnow()
                }}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Ошибка обновления подписки: {e}")
            return False
    
    def get_user_stats(self):
        """Получает статистику пользователей"""
        try:
            total_users = self.users_collection.count_documents({})
            active_users = self.users_collection.count_documents({"is_active": True})
            users_with_subscription = self.users_collection.count_documents({
                "subscription_end": {"$gt": datetime.utcnow()}
            })
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "users_with_subscription": users_with_subscription
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}

    def create_password_reset_token(self, email):
        """Создает токен для сброса пароля"""
        try:
            email = email.strip().lower()
            
            # Ищем пользователя
            user = self.users_collection.find_one({"email": email})
            if not user:
                return {"success": False, "error": "Пользователь с таким email не найден"}
            
            # Генерируем токен
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=24)  # Токен действителен 24 часа
            
            # Сохраняем токен в базе
            reset_data = {
                "email": email,
                "token": token,
                "created_at": datetime.utcnow(),
                "expires_at": expires_at,
                "used": False
            }
            
            # Удаляем старые токены для этого email
            self.db.password_reset_tokens.delete_many({"email": email})
            
            # Сохраняем новый токен
            self.db.password_reset_tokens.insert_one(reset_data)
            
            logger.info(f"✅ Токен сброса пароля создан для: {email}")
            return {
                "success": True,
                "token": token,
                "expires_at": expires_at
            }
            
        except Exception as e:
            logger.error(f"Ошибка создания токена сброса пароля: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def verify_password_reset_token(self, token):
        """Проверяет токен сброса пароля"""
        try:
            # Ищем токен
            reset_data = self.db.password_reset_tokens.find_one({
                "token": token,
                "expires_at": {"$gt": datetime.utcnow()},
                "used": False
            })
            
            if not reset_data:
                return {"success": False, "error": "Недействительный или истекший токен"}
            
            return {
                "success": True,
                "email": reset_data["email"]
            }
            
        except Exception as e:
            logger.error(f"Ошибка проверки токена сброса пароля: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def reset_password(self, token, new_password):
        """Сбрасывает пароль пользователя"""
        try:
            # Проверяем токен
            token_result = self.verify_password_reset_token(token)
            if not token_result["success"]:
                return token_result
            
            email = token_result["email"]
            
            # Ищем пользователя
            user = self.users_collection.find_one({"email": email})
            if not user:
                return {"success": False, "error": "Пользователь не найден"}
            
            # Обновляем пароль
            new_password_hash = self._hash_password(new_password)
            
            result = self.users_collection.update_one(
                {"email": email},
                {
                    "$set": {
                        "password_hash": new_password_hash,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                # Помечаем токен как использованный
                self.db.password_reset_tokens.update_one(
                    {"token": token},
                    {"$set": {"used": True}}
                )
                
                logger.info(f"✅ Пароль сброшен для: {email}")
                return {"success": True, "message": "Пароль успешно изменен"}
            else:
                return {"success": False, "error": "Ошибка обновления пароля"}
            
        except Exception as e:
            logger.error(f"Ошибка сброса пароля: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def add_pre_subscription(self, email, subscription_end, source="manual", notes=None):
        """Добавляет предварительную подписку"""
        try:
            email = email.strip().lower()
            
            # Проверяем, что email не занят
            existing_subscription = self.pre_subscriptions_collection.find_one({"email": email})
            if existing_subscription:
                return {"success": False, "error": "Предварительная подписка для этого email уже существует"}
            
            # Создаем предварительную подписку
            subscription_data = {
                "email": email,
                "subscription_end": subscription_end,
                "is_active": True,
                "source": source,
                "notes": notes,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = self.pre_subscriptions_collection.insert_one(subscription_data)
            
            logger.info(f"✅ Предварительная подписка добавлена: {email}")
            return {
                "success": True,
                "subscription_id": str(result.inserted_id),
                "message": "Предварительная подписка добавлена"
            }
            
        except Exception as e:
            logger.error(f"Ошибка добавления предварительной подписки: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def get_pre_subscription(self, email):
        """Получает предварительную подписку по email"""
        try:
            email = email.strip().lower()
            
            subscription = self.pre_subscriptions_collection.find_one({
                "email": email,
                "is_active": True
            })
            
            if not subscription:
                return {"success": False, "error": "Предварительная подписка не найдена"}
            
            # Проверяем, не истекла ли подписка
            if subscription["subscription_end"] < datetime.utcnow():
                return {"success": False, "error": "Предварительная подписка истекла"}
            
            return {
                "success": True,
                "subscription": {
                    "id": str(subscription["_id"]),
                    "email": subscription["email"],
                    "subscription_end": subscription["subscription_end"],
                    "source": subscription.get("source", "manual"),
                    "notes": subscription.get("notes")
                }
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения предварительной подписки: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def remove_pre_subscription(self, email):
        """Удаляет предварительную подписку"""
        try:
            email = email.strip().lower()
            
            result = self.pre_subscriptions_collection.delete_one({"email": email})
            
            if result.deleted_count > 0:
                logger.info(f"✅ Предварительная подписка удалена: {email}")
                return {"success": True, "message": "Предварительная подписка удалена"}
            else:
                return {"success": False, "error": "Предварительная подписка не найдена"}
            
        except Exception as e:
            logger.error(f"Ошибка удаления предварительной подписки: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def list_pre_subscriptions(self, active_only=True):
        """Получает список предварительных подписок"""
        try:
            filter_query = {}
            if active_only:
                filter_query["is_active"] = True
            
            subscriptions = list(self.pre_subscriptions_collection.find(filter_query).sort("created_at", -1))
            
            # Преобразуем ObjectId в строки
            for sub in subscriptions:
                sub["_id"] = str(sub["_id"])
            
            return {
                "success": True,
                "subscriptions": subscriptions,
                "count": len(subscriptions)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения списка предварительных подписок: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def cleanup_expired_pre_subscriptions(self):
        """Очищает истекшие предварительные подписки"""
        try:
            result = self.pre_subscriptions_collection.update_many(
                {
                    "subscription_end": {"$lt": datetime.utcnow()},
                    "is_active": True
                },
                {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
            )
            
            logger.info(f"✅ Очищено {result.modified_count} истекших предварительных подписок")
            return {
                "success": True,
                "cleaned_count": result.modified_count
            }
            
        except Exception as e:
            logger.error(f"Ошибка очистки истекших предварительных подписок: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

# Создаем глобальный экземпляр
user_auth = UserAuth() 