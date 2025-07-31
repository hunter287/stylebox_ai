# Команды для удаления пользователей в MongoDB

## Через MongoDB Shell

### 1. Подключение к MongoDB
```bash
# Подключиться к MongoDB
mongosh

# Или к конкретной базе данных
mongosh stylist_ai
```

### 2. Удаление пользователя по email
```javascript
// Удалить пользователя по email
db.users.deleteOne({"email": "user@example.com"})

// Также удалить связанные сессии
db.sessions.deleteMany({"email": "user@example.com"})
```

### 3. Удаление пользователя по ID
```javascript
// Удалить пользователя по ObjectId
db.users.deleteOne({"_id": ObjectId("507f1f77bcf86cd799439011")})

// Также удалить связанные сессии
db.sessions.deleteMany({"user_id": ObjectId("507f1f77bcf86cd799439011")})
```

### 4. Удаление всех неактивных пользователей
```javascript
// Удалить всех пользователей без подписки
db.users.deleteMany({"subscription_end": {"$exists": false}})
```

### 5. Удаление пользователей по дате создания
```javascript
// Удалить пользователей созданных до определенной даты
db.users.deleteMany({
    "created_at": {
        "$lt": new Date("2024-01-01")
    }
})
```

### 6. Просмотр пользователей перед удалением
```javascript
// Показать всех пользователей
db.users.find().pretty()

// Показать пользователей без подписки
db.users.find({"subscription_end": {"$exists": false}}).pretty()

// Подсчитать количество пользователей
db.users.countDocuments()
```

## Через Python скрипт

### Использование manage_users.py
```bash
# Запустить скрипт управления пользователями
python3 manage_users.py

# Выберите опцию:
# 1 - Показать всех пользователей
# 2 - Удалить по email
# 3 - Удалить по ID
# 4 - Удалить неактивных
# 5 - Поиск пользователей
```

## Прямые команды в Python

### Удаление по email
```python
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client.stylist_ai

# Удалить пользователя
result = db.users.delete_one({"email": "user@example.com"})
print(f"Удалено пользователей: {result.deleted_count}")

# Удалить сессии
sessions_result = db.sessions.delete_many({"email": "user@example.com"})
print(f"Удалено сессий: {sessions_result.deleted_count}")
```

### Удаление по ID
```python
from pymongo import MongoClient
from bson import ObjectId

client = MongoClient('mongodb://localhost:27017/')
db = client.stylist_ai

# Удалить пользователя по ID
user_id = "507f1f77bcf86cd799439011"
result = db.users.delete_one({"_id": ObjectId(user_id)})
print(f"Удалено пользователей: {result.deleted_count}")

# Удалить сессии
sessions_result = db.sessions.delete_many({"user_id": ObjectId(user_id)})
print(f"Удалено сессий: {sessions_result.deleted_count}")
```

## Безопасность

⚠️ **Внимание!** Удаление пользователей необратимо. Всегда:
1. Сделайте резервную копию перед удалением
2. Проверьте данные перед удалением
3. Удаляйте связанные данные (сессии, токены)

### Резервная копия перед удалением
```bash
# Экспорт данных
python3 export_mongo_data.py

# Или через mongodump
mongodump --db stylist_ai --collection users --out backup/
``` 