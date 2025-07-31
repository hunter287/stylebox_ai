# Папка с анкетами пользователей

Эта папка содержит JSON файлы с полными анкетами пользователей, включая анализ цветотипа и типажа внешности.

## Структура файлов

Каждый файл имеет формат: `survey_YYYY-MM-DD_HH-MM-SS.json`

Пример: `survey_2024-01-15_14-30-25.json`

## Структура данных в JSON файле

### Основные поля:
- **timestamp**: ISO timestamp создания анкеты
- **survey_data**: Все ответы пользователя на вопросы анкеты
- **metadata**: Дополнительная информация о сессии

### Данные анкеты (survey_data):
- **style_preferences**: Предпочтения стиля (массив)
- **color_preferences**: Цветовая гамма (массив)
- **height**: Рост (строка)
- **top_size**: Размер верха (строка)
- **bottom_size**: Размер низа (строка)
- **foot_size**: Размер ноги (строка)
- **body_type**: Тип фигуры (строка)
- **top_clothing**: Верхняя одежда (массив)
- **bottom_clothing**: Нижняя одежда (массив)
- **additional_items**: Дополнительные вещи (массив)
- **fit**: Посадка (массив)
- **photo_analysis**: Результаты анализа фото

### Анализ фото (photo_analysis):
- **color_analysis**: Результаты анализа цветотипа
  - color_type: Определенный цветотип
  - explanation: Объяснение цветотипа
  - dark_colors_hex: Темные цвета (массив HEX)
  - bright_colors_hex: Яркие цвета (массив HEX)
  - light_colors_hex: Светлые цвета (массив HEX)
- **kibbe_analysis**: Результаты анализа типажа
  - kibbe_type: Определенный типаж
  - vertical_lines: Вертикальные линии
  - horizontal_lines: Горизонтальные линии
  - face_features: Особенности лица
  - body_features: Особенности тела
  - description: Описание типажа
  - style_recommendations: Рекомендации по стилю
- **photo_uploaded**: Флаг загрузки фото (boolean)

### Метаданные (metadata):
- **total_questions**: Общее количество вопросов
- **completed_at**: Дата и время завершения (локальное время)
- **user_agent**: User-Agent браузера
- **screen_resolution**: Разрешение экрана
- **timezone**: Часовой пояс пользователя

## Пример использования

```python
import json

# Чтение анкеты
with open('survey_responses/survey_2024-01-15_14-30-25.json', 'r', encoding='utf-8') as f:
    survey = json.load(f)

# Получение цветотипа
color_type = survey['survey_data']['photo_analysis']['color_analysis']['color_type']

# Получение типажа
kibbe_type = survey['survey_data']['photo_analysis']['kibbe_analysis']['kibbe_type']

# Получение предпочтений стиля
style_prefs = survey['survey_data']['style_preferences']
```

## Автоматическое создание

Файлы создаются автоматически при завершении анкеты пользователем через веб-интерфейс. Система:

1. Собирает все ответы пользователя
2. Выполняет анализ загруженного фото
3. Создает уникальное имя файла с датой и временем
4. Сохраняет все данные в JSON формате
5. Логирует успешное сохранение

## Безопасность

- Проверка безопасности имен файлов
- Валидация входящих данных
- Логирование всех операций
- Обработка ошибок 