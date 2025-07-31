# Настройка MongoDB для продакшена

## Обзор

Поскольку staging и продакшен находятся на одном сервере, нам нужно создать отдельный контейнер MongoDB для продакшена на другом порту.

## Шаги настройки

### 1. Создание контейнера MongoDB для продакшена

На сервере выполните:

```bash
# Создадим директорию для данных MongoDB продакшена
sudo mkdir -p /var/lib/mongodb_prod_data
sudo chown 999:999 /var/lib/mongodb_prod_data

# Создадим новый контейнер MongoDB для продакшена на порту 27018
docker run -d --name mongodb_prod -v /var/lib/mongodb_prod_data:/data/db -p 27018:27017 --restart unless-stopped mongo:6.0
```

### 2. Проверка контейнеров

```bash
# Проверим статус контейнеров
docker ps | grep mongo
```

Должны быть два контейнера:
- `mongodb` (staging) на порту 27017
- `mongodb_prod` (production) на порту 27018

### 3. Настройка переменных окружения

Создайте файл `.env` в директории продакшена с настройками:

```bash
# MongoDB для продакшена
MONGO_URI_PROD=mongodb://localhost:27018/
MONGO_DB_NAME_PROD=stylist_ai_prod
MONGO_COLLECTION_PROD=products
```

### 4. Экспорт данных со staging

```bash
# На staging сервере
cd /home/thunderhunt/stylist_ai_staging
python3 export_mongo_data.py
```

### 5. Импорт данных на продакшен

```bash
# На продакшен сервере
cd /home/thunderhunt/stylist_ai
python3 import_mongo_data_prod.py
```

### 6. Проверка данных

```bash
# Проверим данные в продакшен MongoDB
python3 view_mongo_data_prod.py
```

## Структура контейнеров

```
Сервер:
├── mongodb (staging)
│   ├── Порт: 27017
│   ├── Данные: /var/lib/mongodb_data
│   └── База: stylist_ai
└── mongodb_prod (production)
    ├── Порт: 27018
    ├── Данные: /var/lib/mongodb_prod_data
    └── База: stylist_ai_prod
```

## Скрипты

- `export_mongo_data_prod.py` - экспорт данных для продакшена
- `import_mongo_data_prod.py` - импорт данных на продакшен
- `mongo_config_prod.py` - конфигурация MongoDB для продакшена

## Проверка работы

После настройки проверьте:

1. Оба контейнера работают: `docker ps | grep mongo`
2. Данные импортированы: `python3 view_mongo_data_prod.py`
3. Приложение работает с новой базой данных

## Резервное копирование

Для резервного копирования продакшен данных:

```bash
# Экспорт
python3 export_mongo_data_prod.py

# Импорт
python3 import_mongo_data_prod.py
``` 