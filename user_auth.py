import os
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from pymongo import MongoClient
from bson import ObjectId
import logging
# Убрали импорты Google Sheets - больше не нужны
# import gspread
# from google.oauth2.service_account import Credentials
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
            # Убираем уникальность по email, так как у одного email может быть подписка + гайды
            self.pre_subscriptions_collection.create_index("email")
            self.pre_subscriptions_collection.create_index("subscription_end")
            self.pre_subscriptions_collection.create_index("is_active")
            self.pre_subscriptions_collection.create_index("created_at")
            
            # Новые индексы для поддержки гайдов
            self.pre_subscriptions_collection.create_index("product_type")
            self.pre_subscriptions_collection.create_index([
                ("email", 1), 
                ("product_type", 1), 
                ("status", 1)
            ])
            # Уникальный индекс только для подписок ИИ-стилиста (один email = одна подписка)
            self.pre_subscriptions_collection.create_index([
                ("email", 1), 
                ("product_type", 1)
            ], unique=True)
            self.pre_subscriptions_collection.create_index([
                ("product_type", 1), 
                ("guide_data.sent", 1)
            ])
            self.pre_subscriptions_collection.create_index("transaction_id")
            self.pre_subscriptions_collection.create_index("amount")
            
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
            has_pre_subscription = pre_subscription_result["success"]
            
            if has_pre_subscription:
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
                "profile": {
                    "color_type": None,
                    "kibbe_type": None,
                    "body_type": None,
                    "height": None,
                    "preferences": {}
                }
            }
            
            result = self.users_collection.insert_one(user_data)
            
            # Предварительная подписка остается в коллекции pre_subscriptions
            # и будет проверяться при каждом обращении к check_subscription
            if has_pre_subscription:
                logger.info(f"✅ Пользователь зарегистрирован с предварительной подпиской: {email}")
            
            logger.info(f"✅ Пользователь зарегистрирован: {email}")
            return {
                "success": True, 
                "user_id": str(result.inserted_id),
                "message": "Регистрация успешна" + (" (подписка активирована)" if has_pre_subscription else ""),
                "has_subscription": has_pre_subscription
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
            
            logger.info(f"🔑 Создаем сессию для пользователя {email}: {session_id}")
            result = self.sessions_collection.insert_one(session_data)
            logger.info(f"✅ Сессия сохранена в БД с ID: {result.inserted_id}")
            
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
            logger.info(f"🔍 Ищем сессию: {session_id}")
            
            session_data = self.sessions_collection.find_one({
                "session_id": session_id,
                "expires_at": {"$gt": datetime.utcnow()}
            })
            
            if not session_data:
                logger.warning(f"⚠️ Сессия не найдена или истекла: {session_id}")
                return None
            
            logger.info(f"✅ Сессия найдена для пользователя: {session_data.get('email')}")
            
            user_id = session_data.get("user_id")
            if not user_id:
                logger.error(f"❌ В сессии отсутствует user_id: {session_id}")
                return None
            
            user = self.users_collection.find_one({"_id": user_id})
            if not user:
                logger.error(f"❌ Пользователь не найден по ID: {user_id}")
                return None
            
            logger.info(f"✅ Пользователь получен: {user.get('email')}")
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
        """Проверяет активность подписки пользователя через предварительные подписки"""
        try:
            user_id = ObjectId(user_id)
            user = self.users_collection.find_one({"_id": user_id})
            
            if not user:
                logger.warning(f"⚠️ Пользователь не найден: {user_id}")
                return False
            
            email = user.get("email")
            if not email:
                logger.warning(f"⚠️ У пользователя нет email: {user_id}")
                return False
            
            logger.info(f"🔍 Проверяем подписку для пользователя: {email}")
            
            # Проверяем активную предварительную подписку
            pre_sub_result = self.get_pre_subscription(email)
            
            logger.info(f"🔍 Результат get_pre_subscription: {pre_sub_result}")
            
            if pre_sub_result['success']:
                subscription = pre_sub_result['subscription']
                subscription_end = subscription.get('subscription_end')
                
                if subscription_end:
                    # Проверяем, что подписка еще действует
                    is_active = subscription_end > datetime.utcnow()
                    logger.info(f"🔍 Подписка активна: {is_active}, окончание: {subscription_end}")
                    return is_active
                else:
                    logger.warning(f"⚠️ У подписки нет даты окончания: {email}")
            else:
                logger.warning(f"⚠️ Предварительная подписка не найдена: {email}")
            
            return False
            
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
            
            # Подсчитываем пользователей с активными предварительными подписками
            users_with_subscription = 0
            users = self.users_collection.find({})
            
            for user in users:
                email = user.get("email")
                if email:
                    pre_sub_result = self.get_pre_subscription(email)
                    if pre_sub_result['success']:
                        subscription = pre_sub_result['subscription']
                        subscription_end = subscription.get('subscription_end')
                        if subscription_end and subscription_end > datetime.utcnow():
                            users_with_subscription += 1
            
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

    def add_pre_subscription(self, email, subscription_end, source="manual", notes=None, product_type="subscription"):
        """Добавляет предварительную подписку"""
        try:
            # Проверяем подключение к MongoDB
            if self.db is None or self.pre_subscriptions_collection is None:
                logger.warning("MongoDB не подключена, пытаемся переподключиться...")
                if not self.connect():
                    logger.error("Не удалось подключиться к MongoDB")
                    return {"success": False, "error": "Ошибка подключения к базе данных"}
            
            email = email.strip().lower()
            
            # Проверяем, что email не занят (только для подписок ИИ-стилиста)
            if product_type == "subscription":
                existing_subscription = self.pre_subscriptions_collection.find_one({
                    "email": email,
                    "product_type": "subscription"
                })
                if existing_subscription:
                    return {"success": False, "error": "Предварительная подписка для этого email уже существует"}
            else:
                # Для гайдов разрешаем множественные покупки
                existing_subscription = None
            
            # Создаем предварительную подписку
            subscription_data = {
                "email": email,
                "subscription_end": subscription_end,
                "is_active": True,
                "source": source,
                "notes": notes,
                "product_type": product_type,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = self.pre_subscriptions_collection.insert_one(subscription_data)
            
            if product_type == "subscription":
                logger.info(f"✅ Предварительная подписка добавлена: {email}")
            else:
                logger.info(f"✅ Покупка гайда {product_type} добавлена: {email}")
            return {
                "success": True,
                "subscription_id": str(result.inserted_id),
                "message": "Предварительная подписка добавлена" if product_type == "subscription" else f"Покупка гайда {product_type} добавлена"
            }
            
        except Exception as e:
            logger.error(f"Ошибка добавления предварительной подписки: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def get_pre_subscription(self, email, product_type="subscription"):
        """Получает предварительную подписку по email"""
        try:
            # Проверяем подключение к MongoDB
            if self.db is None or self.pre_subscriptions_collection is None:
                logger.warning("MongoDB не подключена, пытаемся переподключиться...")
                if not self.connect():
                    logger.error("Не удалось подключиться к MongoDB")
                    return {"success": False, "error": "Ошибка подключения к базе данных"}
            
            email = email.strip().lower()
            
            # Ищем подписку ИИ-стилиста (subscription_end есть И product_type != "guide")
            if product_type == "subscription":
                subscription = self.pre_subscriptions_collection.find_one({
                    "email": email,
                    "subscription_end": {"$exists": True, "$ne": None},
                    "$or": [
                        {"product_type": {"$exists": False}},  # Старые записи без product_type
                        {"product_type": "subscription"}       # Новые записи с product_type
                    ]
                })
            else:
                # Для гайдов ищем по product_type
                subscription = self.pre_subscriptions_collection.find_one({
                    "email": email,
                    "product_type": product_type
                })
            
            if not subscription:
                if product_type == "subscription":
                    return {"success": False, "error": "Предварительная подписка не найдена"}
                else:
                    return {"success": False, "error": f"Покупка гайда {product_type} не найдена"}
            
            # Для подписок ИИ-стилиста проверяем дату окончания
            if product_type == "subscription":
                subscription_end = subscription.get("subscription_end")
                if not subscription_end:
                    return {"success": False, "error": "У предварительной подписки нет даты окончания"}
                
                # Если subscription_end - строка, конвертируем в datetime
                if isinstance(subscription_end, str):
                    try:
                        subscription_end = datetime.fromisoformat(subscription_end.replace('Z', '+00:00'))
                    except ValueError:
                        return {"success": False, "error": "Неверный формат даты окончания подписки"}
                
                if subscription_end < datetime.utcnow():
                    return {"success": False, "error": "Предварительная подписка истекла"}
                
                return {
                    "success": True,
                    "subscription": {
                        "id": str(subscription["_id"]),
                        "email": subscription["email"],
                        "subscription_end": subscription_end,
                        "source": subscription.get("source", "manual"),
                        "notes": subscription.get("notes"),
                        "created_at": subscription.get("created_at")
                    }
                }
            else:
                # Для гайдов возвращаем информацию о покупке
                return {
                    "success": True,
                    "subscription": {
                        "id": str(subscription["_id"]),
                        "email": subscription["email"],
                        "product_type": subscription.get("product_type"),
                        "status": subscription.get("status", "completed"),
                        "guide_data": subscription.get("guide_data", {}),
                        "created_at": subscription.get("created_at")
                    }
                }
            
        except Exception as e:
            logger.error(f"Ошибка получения {'предварительной подписки' if product_type == 'subscription' else f'покупки гайда {product_type}'}: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def remove_pre_subscription(self, email, product_type="subscription"):
        """Удаляет предварительную подписку"""
        try:
            # Проверяем подключение к MongoDB
            if self.db is None or self.pre_subscriptions_collection is None:
                logger.warning("MongoDB не подключена, пытаемся переподключиться...")
                if not self.connect():
                    logger.error("Не удалось подключиться к MongoDB")
                    return {"success": False, "error": "Ошибка подключения к базе данных"}
            
            email = email.strip().lower()
            
            if product_type == "subscription":
                result = self.pre_subscriptions_collection.delete_one({
                    "email": email,
                    "product_type": "subscription"
                })
            else:
                result = self.pre_subscriptions_collection.delete_one({
                    "email": email,
                    "product_type": product_type
                })
            
            if result.deleted_count > 0:
                if product_type == "subscription":
                    logger.info(f"✅ Предварительная подписка удалена: {email}")
                    return {"success": True, "message": "Предварительная подписка удалена"}
                else:
                    logger.info(f"✅ Покупка гайда {product_type} удалена: {email}")
                    return {"success": True, "message": f"Покупка гайда {product_type} удалена"}
            else:
                if product_type == "subscription":
                    return {"success": False, "error": "Предварительная подписка не найдена"}
                else:
                    return {"success": False, "error": f"Покупка гайда {product_type} не найдена"}
            
        except Exception as e:
            logger.error(f"Ошибка удаления {'предварительной подписки' if product_type == 'subscription' else f'покупки гайда {product_type}'}: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def list_pre_subscriptions(self, active_only=True, product_type=None):
        """Получает список предварительных подписок"""
        try:
            # Фильтруем по product_type если указан
            filter_query = {}
            if product_type:
                filter_query["product_type"] = product_type
            
            subscriptions = list(self.pre_subscriptions_collection.find(filter_query).sort("created_at", -1))
            
            # Если нужны только активные, фильтруем по дате
            if active_only:
                current_time = datetime.utcnow()
                active_subscriptions = []
                
                for sub in subscriptions:
                    subscription_end = sub.get("subscription_end")
                    if subscription_end:
                        # Если subscription_end - строка, конвертируем в datetime
                        if isinstance(subscription_end, str):
                            try:
                                subscription_end = datetime.fromisoformat(subscription_end.replace('Z', '+00:00'))
                            except ValueError:
                                # Если не удается распарсить, пропускаем
                                continue
                        
                        if subscription_end > current_time:
                            active_subscriptions.append(sub)
                
                subscriptions = active_subscriptions
            
            # Преобразуем ObjectId в строки
            for sub in subscriptions:
                sub["_id"] = str(sub["_id"])
            
            return {
                "success": True,
                "subscriptions": subscriptions,
                "count": len(subscriptions)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения списка {'предварительных подписок' if not product_type else f'покупок гайдов {product_type}'}: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def cleanup_expired_pre_subscriptions(self, product_type="subscription"):
        """Очищает истекшие предварительные подписки"""
        try:
            if product_type == "subscription":
                # Для подписок ИИ-стилиста очищаем по дате
                current_time = datetime.utcnow()
                result = self.pre_subscriptions_collection.update_many(
                    {
                        "product_type": "subscription",
                        "subscription_end": {"$lt": current_time}
                    },
                    {"$set": {"is_active": False}}
                )
            else:
                # Для гайдов очистка не требуется
                return {"success": True, "cleaned_count": 0}
            
            logger.info(f"✅ Очищено {result.modified_count} истекших предварительных подписок")
            return {
                "success": True,
                "cleaned_count": result.modified_count
            }
            
        except Exception as e:
            logger.error(f"Ошибка очистки истекших {'предварительных подписок' if product_type == 'subscription' else f'покупок гайдов {product_type}'}: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def add_guide_purchase(self, email, product_type, amount, transaction_id, source="cloudpayments", notes=None):
        """Добавляет покупку гайда"""
        try:
            # Проверяем подключение к MongoDB
            if self.db is None or self.pre_subscriptions_collection is None:
                logger.warning("MongoDB не подключена, пытаемся переподключиться...")
                if not self.connect():
                    logger.error("Не удалось подключиться к MongoDB")
                    return {"success": False, "error": "Ошибка подключения к базе данных"}
            
            email = email.strip().lower()
            
            # Создаем запись о покупке гайда
            guide_data = {
                "email": email,
                "product_type": product_type,
                "subscription_end": None,  # У гайдов нет subscription_end
                "amount": amount,
                "currency": "RUB",
                "status": "completed",
                "payment_provider": "cloudpayments",
                "transaction_id": transaction_id,
                "source": source,
                "notes": notes,
                "guide_data": {
                    "sent": False,
                    "sent_at": None,
                    "pdf_path": None,
                    "attempts": 0,
                    "last_attempt": None
                },
                "metadata": {
                    "user_agent": None,
                    "ip": None,
                    "utm_source": None
                },
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = self.pre_subscriptions_collection.insert_one(guide_data)
            
            logger.info(f"✅ Покупка гайда {product_type} добавлена: {email}, transaction_id: {transaction_id}")
            return {
                "success": True,
                "guide_id": str(result.inserted_id),
                "message": f"Покупка гайда {product_type} добавлена"
            }
            
        except Exception as e:
            logger.error(f"Ошибка добавления покупки гайда: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def can_send_guide(self, email, product_type):
        """Проверяет, можно ли отправить гайд"""
        try:
            print(f"[DEBUG] can_send_guide: Проверяем для {email}, тип: {product_type}")
            
            # Проверяем подключение к MongoDB
            if self.db is None or self.pre_subscriptions_collection is None:
                logger.warning("MongoDB не подключена, пытаемся переподключиться...")
                if not self.connect():
                    logger.error("Не удалось подключиться к MongoDB")
                    return False
            
            # 1. Сначала проверяем, есть ли прямая покупка гайда
            print(f"[DEBUG] can_send_guide: Ищем прямую покупку гайда в MongoDB...")
            
            # Сначала найдем ВСЕ записи для этого email
            all_records = list(self.pre_subscriptions_collection.find({"email": email}))
            print(f"[DEBUG] can_send_guide: Найдено {len(all_records)} записей для {email}")
            
            for i, record in enumerate(all_records):
                print(f"[DEBUG] can_send_guide: Запись {i+1}: {record}")
            
            guide_purchase = self.pre_subscriptions_collection.find_one({
                "email": email,
                "product_type": product_type,
                "subscription_end": None,  # У гайдов нет subscription_end
                "status": "completed",
                "guide_data.sent": False
            })
            
            if guide_purchase is not None:
                print(f"[DEBUG] can_send_guide: ✅ Прямая покупка гайда найдена в MongoDB для {email}")
                return True
            
            # 2. Если прямой покупки нет, проверяем действующую подписку на ИИ-стилиста
            print(f"[DEBUG] can_send_guide: Проверяем подписку на ИИ-стилиста для {email}...")
            
            # Ищем подписку с разными возможными product_type
            subscription = None
            possible_subscription_types = ["subscription", "ai_stylist", "premium", "stylist", "ai_subscription"]
            possible_statuses = ["completed", "active", "paid", "confirmed"]
            
            for sub_type in possible_subscription_types:
                for status in possible_statuses:
                    print(f"[DEBUG] can_send_guide: Проверяем {sub_type} со статусом {status}...")
                    
                    # Ищем подписку с текущим статусом
                    temp_sub = self.pre_subscriptions_collection.find_one({
                        "email": email,
                        "product_type": sub_type,
                        "status": status
                    })
                    
                    if temp_sub:
                        print(f"[DEBUG] can_send_guide: Найдена запись {sub_type} со статусом {status}")
                        
                        # Проверяем, не истекла ли подписка
                        subscription_end = temp_sub.get('subscription_end')
                        if subscription_end:
                            if subscription_end > datetime.utcnow():
                                print(f"[DEBUG] can_send_guide: ✅ Подписка {sub_type} активна до {subscription_end}")
                                subscription = temp_sub
                                break
                            else:
                                print(f"[DEBUG] can_send_guide: ⚠️ Подписка {sub_type} истекла {subscription_end}")
                        else:
                            print(f"[DEBUG] can_send_guide: ✅ Подписка {sub_type} без срока окончания")
                            subscription = temp_sub
                            break
                
                if subscription:
                    break
            
            if subscription is not None:
                print(f"[DEBUG] can_send_guide: ✅ Действующая подписка на ИИ-стилиста найдена для {email}")
                print(f"[DEBUG] can_send_guide: Подписка действует до: {subscription.get('subscription_end')}")
                
                # Проверяем, не был ли уже отправлен гайд этого типа
                guide_sent_check = self.pre_subscriptions_collection.find_one({
                    "email": email,
                    "product_type": product_type,
                    "guide_data.sent": True
                })
                
                if guide_sent_check is None:
                    print(f"[DEBUG] can_send_guide: ✅ Гайд {product_type} еще не был отправлен подписчику {email}")
                    return True
                else:
                    print(f"[DEBUG] can_send_guide: ⚠️ Гайд {product_type} уже был отправлен подписчику {email}")
                    return False
            
            print(f"[DEBUG] can_send_guide: ❌ Пользователь {email} не найден в MongoDB для гайда {product_type} и не имеет действующей подписки")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки возможности отправки гайда: {e}")
            return False

    def mark_guide_sent(self, email, product_type, pdf_path):
        """Помечает гайд как отправленный"""
        try:
            print(f"🚀 [DEBUG] mark_guide_sent: Начало для {email}, {product_type}, {pdf_path}")
            
            # Проверяем подключение к MongoDB
            if self.db is None or self.pre_subscriptions_collection is None:
                print(f"🚀 [DEBUG] mark_guide_sent: MongoDB не подключена, пытаемся переподключиться...")
                logger.warning("MongoDB не подключена, пытаемся переподключиться...")
                if not self.connect():
                    print(f"🚀 [ERROR] mark_guide_sent: Не удалось подключиться к MongoDB")
                    logger.error("Не удалось подключиться к MongoDB")
                    return {"success": False, "error": "Ошибка подключения к базе данных"}
            
            print(f"🚀 [DEBUG] mark_guide_sent: MongoDB подключение проверено")
            
            # Сначала пытаемся найти и обновить существующую покупку в MongoDB
            result = self.pre_subscriptions_collection.update_one(
                {
                    "email": email,
                    "product_type": product_type,
                    "status": "completed"
                },
                {
                    "$set": {
                        "guide_data.sent": True,
                        "guide_data.sent_at": datetime.utcnow(),
                        "guide_data.pdf_path": pdf_path,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                print(f"🚀 [DEBUG] mark_guide_sent: ✅ Гайд {product_type} помечен как отправленный: {email}")
                logger.info(f"✅ Гайд {product_type} помечен как отправленный: {email}")
                return {"success": True, "message": "Гайд помечен как отправленный"}
            
            # Если покупка не найдена, проверяем, есть ли действующая подписка
            print(f"🚀 [DEBUG] mark_guide_sent: Проверяем подписку для {email}...")
            
            # Ищем подписку с разными возможными product_type
            subscription = None
            possible_subscription_types = ["subscription", "ai_stylist", "premium", "stylist", "ai_subscription"]
            possible_statuses = ["completed", "active", "paid", "confirmed"]
            
            for sub_type in possible_subscription_types:
                for status in possible_statuses:
                    print(f"[DEBUG] mark_guide_sent: Проверяем {sub_type} со статусом {status}...")
                    
                    # Ищем подписку с текущим статусом
                    temp_sub = self.pre_subscriptions_collection.find_one({
                        "email": email,
                        "product_type": sub_type,
                        "status": status
                    })
                    
                    if temp_sub:
                        print(f"[DEBUG] mark_guide_sent: Найдена запись {sub_type} со статусом {status}")
                        
                        # Проверяем, не истекла ли подписка
                        subscription_end = temp_sub.get('subscription_end')
                        if subscription_end:
                            if subscription_end > datetime.utcnow():
                                print(f"[DEBUG] mark_guide_sent: ✅ Подписка {sub_type} активна до {subscription_end}")
                                subscription = temp_sub
                                break
                            else:
                                print(f"[DEBUG] mark_guide_sent: ⚠️ Подписка {sub_type} истекла {subscription_end}")
                        else:
                            print(f"[DEBUG] mark_guide_sent: ✅ Подписка {sub_type} без срока окончания")
                            subscription = temp_sub
                            break
                
                if subscription:
                    break
            
            if subscription is not None:
                print(f"[DEBUG] mark_guide_sent: ✅ Действующая подписка найдена для {email}, создаем запись о гайде")
                
                # Создаем запись о том, что гайд был отправлен подписчику
                guide_data = {
                    "email": email,
                    "product_type": product_type,
                    "subscription_end": None,
                    "amount": 0,  # Бесплатно для подписчиков
                    "currency": "RUB",
                    "status": "completed",
                    "payment_provider": "subscription",
                    "transaction_id": f"sub_{int(time.time())}",
                    "source": "subscription_benefit",
                    "notes": f"Гайд отправлен как бонус для подписчика ИИ-стилиста",
                    "guide_data": {
                        "sent": True,
                        "sent_at": datetime.utcnow(),
                        "pdf_path": pdf_path,
                        "attempts": 1,
                        "last_attempt": datetime.utcnow()
                    },
                    "metadata": {
                        "user_agent": None,
                        "ip": None,
                        "utm_source": None
                    },
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                
                result = self.pre_subscriptions_collection.insert_one(guide_data)
                print(f"🚀 [DEBUG] mark_guide_sent: ✅ Запись об отправке гайда {product_type} подписчику создана: {email}")
                logger.info(f"✅ Запись об отправке гайда {product_type} подписчику создана: {email}")
                return {"success": True, "message": "Гайд помечен как отправленный подписчику"}
            
            # Если ни покупки, ни подписки нет, возвращаем ошибку
            print(f"🚀 [DEBUG] mark_guide_sent: Ни покупки, ни подписки не найдено для {email}")
            return {"success": False, "error": "Покупка гайда не найдена и нет действующей подписки"}
            
        except Exception as e:
            print(f"🚀 [ERROR] mark_guide_sent: Исключение: {e}")
            print(f"🚀 [ERROR] mark_guide_sent: Тип исключения: {type(e).__name__}")
            import traceback
            print(f"🚀 [ERROR] mark_guide_sent: Traceback: {traceback.format_exc()}")
            logger.error(f"Ошибка пометки гайда как отправленного: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

    def get_guide_purchase_stats(self):
        """Получает статистику по покупкам гайдов"""
        try:
            # Проверяем подключение к MongoDB
            if self.db is None or self.pre_subscriptions_collection is None:
                logger.warning("MongoDB не подключена, пытаемся переподключиться...")
                if not self.connect():
                    logger.error("Не удалось подключиться к MongoDB")
                    return {"success": False, "error": "Ошибка подключения к базе данных"}
            
            # Статистика по типам гайдов
            guide_stats = self.pre_subscriptions_collection.aggregate([
                {
                    "$match": {
                        "product_type": {"$in": ["color_guide", "kibbe_guide"]},
                        "subscription_end": None
                    }
                },
                {
                    "$group": {
                        "_id": "$product_type",
                        "total_purchases": {"$sum": 1},
                        "total_amount": {"$sum": "$amount"},
                        "sent_count": {
                            "$sum": {"$cond": ["$guide_data.sent", 1, 0]}
                        },
                        "pending_count": {
                            "$sum": {"$cond": ["$guide_data.sent", 0, 1]}
                        }
                    }
                }
            ])
            
            stats = list(guide_stats)
            
            return {
                "success": True,
                "stats": stats,
                "total_guides": sum(stat["total_purchases"] for stat in stats),
                "total_sent": sum(stat["sent_count"] for stat in stats),
                "total_pending": sum(stat["pending_count"] for stat in stats)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики по гайдам: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}

# Создаем глобальный экземпляр
user_auth = UserAuth() 