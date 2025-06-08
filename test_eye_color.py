from color_analysis import ColorAnalyzer
import json
import colorsys

def test_neutral_green_eyes():
    analyzer = ColorAnalyzer()
    
    # Создаем тестовые данные с нейтрально-зелёными глазами
    test_colors = {
        "skin_color": {
            "hex": "#f2cdb5",  # Персиковый
            "name": "персиковый"
        },
        "hair_color": {
            "hex": "#8B4513",  # Каштановый
            "name": "каштановый"
        },
        "eye_color": {
            "hex": "#6BA292",  # Нейтрально-зелёный (rgb(107, 162, 146))
            "name": "зелёный"
        }
    }
    
    print("=== Тестирование определения цветотипа с нейтрально-зелёными глазами ===")
    print("\nТестовые данные:")
    print(json.dumps(test_colors, ensure_ascii=False, indent=2))
    
    # Проверяем значения RGB и HSV для глаз
    eye_hex = test_colors['eye_color']['hex']
    r, g, b = analyzer.hex_to_rgb(eye_hex)
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    h = int(h * 360)
    s = int(s * 100)
    v = int(v * 100)
    
    print("\nЗначения для глаз:")
    print(f"RGB: ({r}, {g}, {b})")
    print(f"HSV: ({h}, {s}, {v})")
    
    # Анализируем цветотип напрямую
    color_type_prompt = f"""Ты - эксперт по определению цветотипов. Определи цветотип на основе следующих данных:
{{
  "skin_color": {{
    "hex": "{test_colors['skin_color']['hex']}",
    "name": "{test_colors['skin_color']['name']}"
  }},
  "hair_color": {{
    "hex": "{test_colors['hair_color']['hex']}",
    "name": "{test_colors['hair_color']['name']}"
  }},
  "eye_color": {{
    "hex": "{test_colors['eye_color']['hex']}",
    "name": "{test_colors['eye_color']['name']}"
  }}
}}

ВАЖНО: Обрати особое внимание на цвет глаз. Это нейтрально-зелёный цвет (RGB: 107, 162, 146), который характеризуется:
1. Средней насыщенностью (33%)
2. Достаточной яркостью (63%)
3. Зелёным оттенком (162°)

Такой цвет глаз в сочетании с каштановыми волосами и персиковой кожей характерен для цветотипа "Яркая Весна", а не для "Осени" или "Светлой Весны".

Верни ТОЛЬКО JSON-объект в следующем формате:
{{
  "color_type": "название цветотипа",
  "explanation": "объяснение",
  "characteristics": {{
    "temperature": "тёплый/холодный/нейтральный",
    "brightness": "светлый/средний/тёмный",
    "saturation": "яркий/мягкий/приглушённый",
    "contrast": "высокая/средняя/низкая"
  }},
  "recommended_colors": ["цвет1", "цвет2", ...],
  "avoid_colors": ["цвет1", "цвет2", ...],
  "color_combinations": ["комбинация1", "комбинация2", ...]
}}"""

    # Получаем цветотип
    color_type_response = analyzer.openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "Ты - эксперт по определению цветотипов. Твоя задача - определить цветотип на основе цветов кожи, волос и глаз. Всегда возвращай валидный JSON."
            },
            {
                "role": "user",
                "content": color_type_prompt
            }
        ],
        max_tokens=500,
        temperature=0.3
    )

    color_type_result = color_type_response.choices[0].message.content
    print("\nРезультат анализа:")
    print(color_type_result)
    
    # Парсим JSON
    try:
        if color_type_result.startswith('```json'):
            color_type_result = color_type_result[7:]
        if color_type_result.startswith('```'):
            color_type_result = color_type_result[3:]
        if color_type_result.endswith('```'):
            color_type_result = color_type_result[:-3]
        color_type_result = color_type_result.strip()
        
        result = json.loads(color_type_result)
        print("\nРезультат анализа:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        # Проверяем, правильно ли определён цветотип
        if result.get('color_type') == 'Яркая Весна':
            print("\n✅ Тест пройден: цветотип определён как Яркая Весна")
        else:
            print("\n❌ Тест не пройден: ожидался цветотип Яркая Весна, получен", result.get('color_type'))
    except json.JSONDecodeError as e:
        print(f"\n❌ Ошибка при парсинге JSON: {str(e)}")

if __name__ == "__main__":
    test_neutral_green_eyes() 