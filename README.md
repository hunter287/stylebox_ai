# Color Type Analysis Telegram Bot

Телеграм-бот для определения цветотипа по фотографии и подбора подходящих цветов в одежде.

## Требования

- Python 3.8+
- Telegram Bot Token
- Google Cloud Vision API credentials

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` в корневой директории проекта и добавьте следующие переменные:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GOOGLE_CLOUD_CREDENTIALS=path_to_your_google_cloud_credentials.json
DATABASE_URL=sqlite:///color_analysis.db
```

4. Создайте учетные данные Google Cloud Vision API:
   - Перейдите в [Google Cloud Console](https://console.cloud.google.com)
   - Создайте новый проект
   - Включите Cloud Vision API
   - Создайте сервисный аккаунт и скачайте JSON-файл с учетными данными
   - Укажите путь к этому файлу в переменной `GOOGLE_CLOUD_CREDENTIALS`

## Запуск

```bash
python bot.py
```

## Использование

1. Найдите бота в Telegram по его username
2. Отправьте команду `/start`
3. Отправьте фотографию для анализа
4. Получите результат определения цветотипа

## Текущие возможности

- Определение базового цветотипа по фотографии
- Сохранение результатов анализа в базе данных
- Обработка ошибок и логирование

## Планируемые улучшения

- Более точное определение цветотипа
- Рекомендации по подбору цветов
- Сохранение избранных цветовых комбинаций
- Сравнение цветов на совместимость
- Ограничение количества запросов в сутки 