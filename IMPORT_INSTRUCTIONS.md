# Инструкции по импорту данных на продакшен

## Шаг 1: Отправка файлов на сервер

### Создайте архив с данными:
```bash
tar -czf mongo_export_$(date +%Y%m%d_%H%M%S).tar.gz mongo_export_20250731_052857/
```

### Отправьте архив на сервер:
```bash
scp mongo_export_*.tar.gz username@your-production-server.com:/path/to/backup/
```

### Или отправьте папку целиком:
```bash
scp -r mongo_export_20250731_052857/ username@your-production-server.com:/path/to/backup/
```

## Шаг 2: Подключение к серверу

```bash
ssh username@your-production-server.com
cd /path/to/backup/
```

## Шаг 3: Распаковка данных (если отправляли архив)

```bash
tar -xzf mongo_export_*.tar.gz
cd mongo_export_20250731_052857/
```

## Шаг 4: Импорт данных

### Вариант A: Быстрый импорт (рекомендуется)

```bash
# Убедитесь, что у вас установлен Python и pymongo
pip install pymongo

# Скопируйте скрипт на сервер или создайте его
python quick_import.py
```

### Вариант B: Интерактивный импорт

```bash
python import_mongo_data.py
```

### Вариант C: Ручной импорт через MongoDB shell

```bash
# Подключитесь к MongoDB
mongosh stylist_ai

# Импортируйте каждую коллекцию
db.users.drop()
db.users.insertMany(JSON.parse(cat("users.json")))

db.sessions.drop()
db.sessions.insertMany(JSON.parse(cat("sessions.json")))

db.password_reset_tokens.drop()
db.password_reset_tokens.insertMany(JSON.parse(cat("password_reset_tokens.json")))

db.pre_subscriptions.drop()
db.pre_subscriptions.insertMany(JSON.parse(cat("pre_subscriptions.json")))

db.products.drop()
db.products.insertMany(JSON.parse(cat("products.json")))

db.products_enhanced.drop()
db.products_enhanced.insertMany(JSON.parse(cat("products_enhanced.json")))

db.chat_sessions.drop()
db.chat_sessions.insertMany(JSON.parse(cat("chat_sessions.json")))
```

## Шаг 5: Проверка импорта

### Проверьте количество документов в каждой коллекции:

```bash
mongosh stylist_ai --eval "
db.users.countDocuments()
db.sessions.countDocuments()
db.password_reset_tokens.countDocuments()
db.pre_subscriptions.countDocuments()
db.products.countDocuments()
db.products_enhanced.countDocuments()
db.chat_sessions.countDocuments()
"
```

### Или используйте скрипт для проверки:

```bash
python import_mongo_data.py
# Выберите опцию 4 - "Проверить подключение к MongoDB"
```

## Шаг 6: Настройка переменных окружения

Убедитесь, что на продакшен сервере настроены переменные окружения:

```bash
export MONGO_URI="mongodb://localhost:27017/"
export MONGO_DB_NAME="stylist_ai"
```

## Структура файлов

После импорта у вас должны быть следующие коллекции:

- `users` - пользователи системы
- `sessions` - активные сессии пользователей
- `password_reset_tokens` - токены для сброса паролей
- `pre_subscriptions` - предварительные подписки
- `products` - товары (основная коллекция)
- `products_enhanced` - товары с дополнительными атрибутами
- `chat_sessions` - сессии чата

## Важные замечания

1. **Резервная копия**: Перед импортом сделайте резервную копию существующих данных
2. **Время простоя**: Импорт может занять несколько минут, планируйте время простоя
3. **Проверка**: После импорта обязательно проверьте целостность данных
4. **Индексы**: Убедитесь, что все необходимые индексы созданы

## Команды для резервной копии

```bash
# Создание резервной копии перед импортом
mongodump --db stylist_ai --out backup_before_import_$(date +%Y%m%d_%H%M%S)

# Восстановление из резервной копии (если нужно)
mongorestore --db stylist_ai backup_before_import_YYYYMMDD_HHMMSS/stylist_ai/
```

## Устранение проблем

### Ошибка подключения к MongoDB:
- Проверьте, что MongoDB запущен: `systemctl status mongod`
- Проверьте настройки подключения в переменных окружения

### Ошибка импорта коллекции:
- Проверьте права доступа к файлам
- Убедитесь, что JSON файлы не повреждены
- Проверьте свободное место на диске

### Ошибка "duplicate key":
- Коллекция уже содержит документы с такими же _id
- Используйте опцию очистки коллекции перед импортом 