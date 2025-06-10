import os
from config import OPENAI_API_KEY
import colorsys
from openai import OpenAI
import json
from PIL import Image
import io
import base64
import time
from face_parser import FaceParser
import random

class ColorAnalyzer:
    def __init__(self):
        self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
        self.face_parser = FaceParser()
        
        # Пороговые значения для определения характеристик
        self.THRESHOLDS = {
            'brightness': {
                'high': 65,  # Высокая яркость
                'medium': 45,  # Средняя яркость
                'low': 35   # Низкая яркость
            },
            'saturation': {
                'high': 55,  # Высокая насыщенность
                'medium': 40,  # Средняя насыщенность
                'low': 30   # Низкая насыщенность
            }
        }

    def hex_to_rgb(self, hex_color):
        """Преобразует HEX-цвет в RGB-кортеж"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def calculate_contrast(self, color1_hex, color2_hex):
        """Рассчитывает контрастность между двумя цветами"""
        def relative_luminance(r, g, b):
            r, g, b = r/255, g/255, b/255
            r = r/12.92 if r <= 0.03928 else ((r + 0.055)/1.055) ** 2.4
            g = g/12.92 if g <= 0.03928 else ((g + 0.055)/1.055) ** 2.4
            b = b/12.92 if b <= 0.03928 else ((b + 0.055)/1.055) ** 2.4
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        rgb1 = self.hex_to_rgb(color1_hex)
        rgb2 = self.hex_to_rgb(color2_hex)
        
        l1 = relative_luminance(*rgb1)
        l2 = relative_luminance(*rgb2)
        
        contrast = (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
        return contrast

    def analyze_image(self, image_path, max_retries=10, retry_delay=1):
        """Analyze image using OpenAI GPT-4o with retry mechanism"""
        try:
            print("\n=== Starting image analysis ===")
            print(f"Image path: {image_path}")
            
            # Читаем изображение
            try:
                with open(image_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                print("Image successfully read and encoded")
            except Exception as e:
                print(f"Error reading image: {str(e)}")
                return None

            # Проверяем размер изображения
            try:
                with Image.open(image_path) as img:
                    width, height = img.size
                    print(f"\nImage information:")
                    print(f"Size: {width}x{height}")
                    print(f"Format: {img.format}")
                    print(f"Mode: {img.mode}")
                    
                    if width < 100 or height < 100:
                        print("Image too small")
                        return None
                    
                    if img.format not in ['JPEG', 'PNG']:
                        print(f"Unsupported image format: {img.format}")
                        return None
                    
            except Exception as e:
                print(f"Error checking image: {str(e)}")
                return None

            print("\n=== Starting color analysis ===")
            # Первый запрос - получение HEX-кодов и названий цветов
            colors_prompt = """Ты - эксперт по анализу цветов. Проанализируй изображение и определи цвета кожи, волос и глаз. Верни ТОЛЬКО JSON-объект в следующем формате:
{
  "skin_color": {
    "hex": "#HEX",
    "name": "название цвета"  // например: "персиковый", "бежевый", "оливковый"
  },
  "hair_color": {
    "hex": "#HEX",
    "name": "название цвета"  // например: "тёмно-коричневый", "чёрный", "русый"
  },
  "eye_color": {
    "hex": "#HEX",
    "name": "название цвета"  // например: "голубой", "зелёный", "карий"
  }
}

ВАЖНО:
1. Верни ТОЛЬКО JSON-объект, без дополнительного текста
2. Используй формат HEX для цветов (например, "#f2cdb5")
3. Если какой-то элемент не виден, используй "#000000" и "не видно"
4. Не добавляй никаких комментариев или пояснений
5. Если не можешь определить цвет, используй "#000000" и "не определено"
6. Всегда возвращай валидный JSON
7. Если изображение нечеткое или плохого качества, все равно попробуй определить цвета"""

            # Функция для анализа цветов с повторными попытками
            def analyze_colors_with_retry():
                for attempt in range(max_retries):
                    try:
                        print(f"\nAttempt {attempt + 1} of {max_retries} for color analysis")
                        
                        colors_response = self.openai_client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "Ты - эксперт по анализу цветов. Твоя задача - определить цвета кожи, волос и глаз на изображении. Всегда возвращай валидный JSON."
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": colors_prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/jpeg;base64,{base64_image}"
                                            }
                                        }
                                    ]
                                }
                            ],
                            max_tokens=300,
                            temperature=0.3
                        )

                        colors_result = colors_response.choices[0].message.content
                        print("\nColors from GPT:")
                        print(colors_result)

                        # Проверяем, не отказался ли GPT от анализа
                        if "I'm sorry" in colors_result or "I can't help" in colors_result:
                            print(f"GPT refused to analyze on attempt {attempt + 1}")
                            if attempt < max_retries - 1:
                                print(f"Waiting {retry_delay} seconds before next attempt...")
                                time.sleep(retry_delay)
                                continue
                            return None

                        # Очищаем ответ от markdown-форматирования
                        colors_result = colors_result.strip()
                        if colors_result.startswith('```json'):
                            colors_result = colors_result[7:]
                        if colors_result.startswith('```'):
                            colors_result = colors_result[3:]
                        if colors_result.endswith('```'):
                            colors_result = colors_result[:-3]
                        colors_result = colors_result.strip()

                        # Парсим JSON с цветами
                        try:
                            colors = json.loads(colors_result)
                            print("\nParsed colors:")
                            print(json.dumps(colors, ensure_ascii=False, indent=2))
                            
                            # Проверяем наличие всех необходимых полей
                            required_fields = ['skin_color', 'hair_color', 'eye_color']
                            for field in required_fields:
                                if field not in colors:
                                    colors[field] = {"hex": "#000000", "name": "не определено"}
                                if 'hex' not in colors[field]:
                                    colors[field]['hex'] = "#000000"
                                if 'name' not in colors[field]:
                                    colors[field]['name'] = "не определено"

                            # Проверяем валидность HEX-кодов
                            for field in required_fields:
                                hex_color = colors[field]['hex']
                                if not hex_color.startswith('#') or len(hex_color) != 7:
                                    colors[field]['hex'] = "#000000"
                                    colors[field]['name'] = "не определено"

                            return colors
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {str(e)}")
                            if attempt < max_retries - 1:
                                continue
                            return None

                    except Exception as e:
                        print(f"Error on attempt {attempt + 1}: {str(e)}")
                        if attempt < max_retries - 1:
                            print(f"Waiting {retry_delay} seconds before next attempt...")
                            time.sleep(retry_delay)
                        else:
                            return None

            # Получаем цвета с повторными попытками
            colors = analyze_colors_with_retry()
            if colors is None:
                print("Failed to analyze colors after all attempts")
                return None

            print("\n=== Starting color type analysis ===")
            # --- Контрастность между кожей и волосами ---
            skin_hex = colors['skin_color']['hex']
            hair_hex = colors['hair_color']['hex']
            # Ручная проверка: если волосы чёрные и кожа светлая, контрастность = экстремально высокая
            hair_name = colors['hair_color']['name'].lower()
            r, g, b = self.hex_to_rgb(skin_hex)
            _, _, v = self.rgb_to_hsv(r, g, b)
            if ('чёрный' in hair_name or 'черный' in hair_name) and v > 70:
                contrast_level = 'экстремально высокая'
            else:
                contrast_value = self.calculate_contrast(skin_hex, hair_hex)
                if contrast_value > 3.5:
                    contrast_level = 'высокая'
                elif contrast_value > 2.2:
                    contrast_level = 'средняя'
                else:
                    contrast_level = 'низкая'
            print(f"\nContrast analysis:")
            print(f"Skin color: {skin_hex}")
            print(f"Hair color: {hair_hex}")
            print(f"Contrast level: {contrast_level}")

            # Второй запрос - определение цветотипа
            color_type_prompt = f"""Ты - эксперт по определению цветотипов. Проанализируй следующие цвета и определи цветотип, строго следуя описаниям из статей:

{{
  "skin_color": {{
    "hex": "{colors['skin_color']['hex']}",
    "name": "{colors['skin_color']['name']}"
  }},
  "hair_color": {{
    "hex": "{colors['hair_color']['hex']}",
    "name": "{colors['hair_color']['name']}"
  }},
  "eye_color": {{
    "hex": "{colors['eye_color']['hex']}",
    "name": "{colors['eye_color']['name']}"
  }},
  "contrast": "{contrast_level}"
}}

ВАЖНО:
1. Сначала попробуй найти точное соответствие характеристикам из статей
2. Если точного соответствия нет, выбери наиболее близкий цветотип, объяснив почему
3. При выборе ближайшего цветотипа учитывай:
   - Соответствие цвета глаз (самый важный критерий)
   - Соответствие цвета волос (второй по важности)
   - Соответствие цвета кожи (третий по важности)
   - Контрастность между кожей и волосами: если контрастность экстремально высокая (чёрные волосы, светлая кожа, яркие или чистые глаза), это только зима. Если контрастность высокая, но не максимальная (тёмные волосы, тёплая кожа, тёплые глаза), это глубокая осень.
   - ЕСЛИ волосы русые или светлые, даже при тёплой коже, ГЛУБОКАЯ ОСЕНЬ НЕВОЗМОЖНА — выбирай Светлую Весну или другой светлый тип
   - Для Глубокой Осени волосы должны быть только очень тёмные (темно-каштановые, темно-рыжие, почти чёрные), глаза — только тёмные (тёмно-карие, тёмно-зелёные, тёмно-ореховые). Если волосы просто каштановые или тёмно-русые, а кожа персиковая, медовая, бежево-золотистая — это Тёплая Осень.
   - ***ОСОБОЕ ПРАВИЛО: Для Глубокой Осени глаза должны быть только тёмно-зелёные, тёмно-карие или тёмно-ореховые. Если глаза просто зелёные или нейтральные, а не тёмные — это НЕ Глубокая Осень, а скорее Тёплая Осень или Яркая Весна.***
   - Для Тёплой Осени: волосы могут быть тёмно-русые, каштановые, рыжие; глаза — карие, ореховые, янтарные, зелёные (тёплые, с золотистым или коричневым подтоном), тёмно-серые; кожа — оливковая, медовая, бежево-золотистая, персиковая; контрастность ТОЛЬКО средняя, высокая контрастность НЕВОЗМОЖНА.
   - Для Яркой Весны: волосы — светло-русые, золотистые, медные, каштановые (но не тёмно-коричневые!); глаза — яркие голубые, зелёные (чистые, яркие, без тёплого подтона), ореховые; кожа — светлая с персиковым подтоном; контрастность средняя или высокая.
   - ***ОСОБОЕ ПРАВИЛО: Если волосы тёмно-коричневые, а глаза ярко-голубые и кожа персиковая — не относить к Яркой Весне. Если волосы с пепельным подтоном — рассматривать как Холодное Лето.***
   - Для Холодного Лета: волосы только от светло-русых до темно-русых, чаще с пепельным подтоном (исключить каштановые и тёмно-коричневые как основной признак); глаза только синие, голубые, серо-голубые, темно-серые, серо-зеленые; кожа молочного цвета, бежево-розовая, бежево-серая, нейтрального бежевого цвета; контрастность низкая или средняя (высокая только если волосы темно-русые с пепельным подтоном и глаза очень яркие).
   - ***Для Холодного Лета разрешить высокий контраст, если волосы темно-русые (пепельные) и глаза ярко-голубые.***
   - ***ОСОБОЕ ПРАВИЛО: Если глаза яркие, чистые (голубые, зелёные, ореховые), кожа светлая с персиковым подтоном, волосы золотистые, медные или каштановые, а контрастность средняя или высокая — это ВСЕГДА Яркая Весна, даже если оттенок глаз не классический.***
   - ЕСЛИ контрастность высокая или экстремально высокая:
     * Если глаза холодные (холодные голубые, серые, холодные зелёные) — это Зима
     * Если глаза тёплые (тёплые зелёные, янтарные, карие) и волосы светлые с тёплым подтоном — это Яркая Весна
     * Если глаза тёплые и волосы тёмные — это Глубокая Осень
   - ЕСЛИ контрастность средняя:
     * Если глаза тёплые и волосы каштановые или рыжие — это Тёплая Осень
     * Если глаза тёплые и волосы светлые с тёплым подтоном — это Тёплая Весна
   - ЕСЛИ контрастность низкая:
     * Если глаза тёплые — это Светлая Весна или Мягкая Осень
     * Если глаза холодные — это Лето
   - Для Глубокой Осени контрастность средняя или высокая (но не экстремально высокая)
   - Для Глубокой Осени допустимы только тёмно-зелёные глаза. Если глаза зелёные, но светлые или нейтральные по тону — это не Глубокая Осень, а скорее Яркая Весна или Светлая Весна.
   - Для Холодной Зимы характерны только холодные тона глаз: холодный серый, серо-синий, ясный серо-зелёный, карий. НЕВОЗМОЖНЫ тёплые зелёные, тёплые оливковые, ореховые, янтарные глаза, а также мутные, жёлто-зелёные, коричневато-зелёные оттенки.
   - Для Холодной Зимы волосы: только иссине-черные, чёрные, тёмно-каштановые с холодным подтоном.
   - Для Холодной Зимы кожа: фарфоровый розовый, бежевый, бежево-розовый, без тёплого или золотистого подтона.
   - ЕСЛИ волосы чёрные, кожа светлая, глаза холодные (в том числе холодные зелёные) — это всегда зима, даже если оттенок глаз не классический для зимы.
   - ***ОСОБОЕ ПРАВИЛО: Если глаза серо-голубые, волосы каштановые, кожа персиковая, а контрастность не высокая (средняя или низкая), то это ВСЕГДА Тёплая Весна, даже если оттенок глаз холодный.***
4. Всегда возвращай валидный JSON

Цветотипы по статьям:

1. Холодное Лето:
- Глаза: ТОЛЬКО синие, голубые, серо-голубые, темно-серые или серо-зеленые, светло-голубые
- Волосы: ТОЛЬКО от светло-русых до темно-русых с пепельным подтоном
- Кожа: ТОЛЬКО молочного цвета, бежево-розовая, бежево-серая, нейтрального бежевого цвета
- Контрастность: низкая или средняя (высокая только если волосы темно-русые с пепельным подтоном и глаза очень яркие)
- Рекомендуемые цвета: дымчато-розовый, дымчато-голубой, дымчато-синий, дымчато-фиолетовый, серый, мягкий сиреневый, мягкий голубой
- Цвета, которых следует избегать: тёплые оттенки, яркие цвета, чистые тона, чёрный, белый

2. Мягкое Лето:
- Глаза: ТОЛЬКО серо-голубые, серо-зеленые, ореховые
- Волосы: ТОЛЬКО пепельные, мышиные, светло-русые
- Кожа: ТОЛЬКО светлая с сероватым подтоном
- Контрастность: низкая
- Рекомендуемые цвета: мягкий голубой, мягкий розовый, мягкий сиреневый, мягкий серый, мягкий фиолетовый, мягкий синий, мягкий зелёный
- Цвета, которых следует избегать: яркие цвета, тёплые оттенки, чистые тона, чёрный, белый

3. Светлое Лето:
- Глаза: ТОЛЬКО светло-голубые, серо-голубые, серые
- Волосы: ТОЛЬКО светло-русые, пепельные
- Кожа: ТОЛЬКО очень светлая, фарфоровая
- Контрастность: низкая
- Рекомендуемые цвета: светло-голубой, светло-розовый, светло-сиреневый, светло-серый, светло-фиолетовый, светло-синий, светло-зелёный
- Цвета, которых следует избегать: тёмные цвета, тёплые оттенки, яркие цвета, чёрный

4. Светлая Весна:
- Глаза: ТОЛЬКО светло-голубые, зеленые, ореховые
- Волосы: ТОЛЬКО светлые, золотистые, медовые, русые с тёплым оттенком
- Кожа: ТОЛЬКО светлая с золотистым или бежевым подтоном
- Контрастность: низкая
- Рекомендуемые цвета: светло-персиковый, нежно-жёлтый, светло-зелёный, светло-бежевый, светло-коралловый, светло-абрикосовый, светло-розовый
- Цвета, которых следует избегать: тёмные цвета, холодные оттенки, яркие контрастные цвета, чёрный

5. Тёплая Весна:
- Глаза: ТОЛЬКО светло-голубые, серо-голубые, зелёные, ореховые, янтарные
- Волосы: ТОЛЬКО золотистые, медные, каштановые, рыжие, блонд с медовым подтоном, блонд с рыжиной, светло-русые волосы с рыжим отливом
- Кожа: ТОЛЬКО тёплые персиковые тона, бежево-медовый, бежевый цвет кожи
- Контрастность: средняя
- Рекомендуемые цвета: коралловый, персиковый, тёплый жёлтый, тёплый зелёный, тёплый бежевый, абрикосовый, лососевый, тёплый розовый, тёплый оранжевый
- Цвета, которых следует избегать: холодные оттенки, тёмные цвета, приглушённые тона, чёрный, белый

6. Яркая Весна:
- Глаза: ТОЛЬКО яркие голубые, зеленые, ореховые
- Волосы: ТОЛЬКО светло-русые, золотистые, медные, каштановые (но не тёмно-коричневые!)
- Кожа: ТОЛЬКО светлая с персиковым подтоном
- Контрастность: средняя или высокая
- Рекомендуемые цвета: яркий коралловый, яркий жёлтый, яркий зелёный, яркий оранжевый, яркий розовый, бирюзовый, белый
- Цвета, которых следует избегать: приглушённые тона, тёмные цвета, холодные оттенки, пастельные тона

7. Мягкая Осень:
- Глаза: ТОЛЬКО ореховые, зеленые, серо-зеленые
- Волосы: ТОЛЬКО каштановые, русые с рыжим подтоном
- Кожа: ТОЛЬКО светлая с золотистым подтоном
- Контрастность: низкая
- Рекомендуемые цвета: мягкий коричневый, мягкий зелёный, мягкий бежевый, мягкий оливковый, мягкий бордовый, мягкий терракотовый, мягкий оранжевый
- Цвета, которых следует избегать: яркие цвета, холодные оттенки, чистые тона, чёрный, белый

8. Тёплая Осень:
- Глаза: ТОЛЬКО ореховые, зеленые, янтарные, карие (СВЕТЛО-ГОЛУБЫЕ И СЕРО-ГОЛУБЫЕ НЕ ВСТРЕЧАЮТСЯ)
- Волосы: ТОЛЬКО медные, рыжие, каштановые
- Кожа: ТОЛЬКО светлая с золотистым подтоном
- Контрастность: средняя
- Рекомендуемые цвета: терракотовый, оливковый, тёплый коричневый, тёплый зелёный, тёплый бежевый, медный, бордовый, тёплый оранжевый
- Цвета, которых следует избегать: холодные оттенки, яркие цвета, пастельные тона, чёрный, белый

9. Глубокая Осень:
- Глаза: ТОЛЬКО ореховые, зелёные (ТОЛЬКО ТЁМНО-ЗЕЛЁНЫЕ), тёмно-карие. СВЕТЛО-ЗЕЛЁНЫЕ, ОЛИВКОВЫЕ (если они светлые или с холодным подтоном), СЕРО-ЗЕЛЁНЫЕ, СВЕТЛО-ГОЛУБЫЕ ГЛАЗА НЕВОЗМОЖНЫ. ДОПУСТИМЫ оливковые глаза, если они тёплые, мутные, с жёлтым или коричневым подтоном.
- Волосы: ТОЛЬКО темно-каштановые, темно-рыжие (ТОЛЬКО ТЁМНЫЕ)
- Кожа: МОЖЕТ БЫТЬ персиковой, абрикосовой, светлой с золотистым или тёплым подтоном
- Контрастность: средняя или высокая (но не экстремально высокая)
- Рекомендуемые цвета: тёмно-коричневый, тёмно-зелёный, тёмно-бордовый, тёмно-оливковый, тёмно-терракотовый, тёмно-оранжевый, тёмно-бежевый
- Цвета, которых следует избегать: светлые цвета, холодные оттенки, пастельные тона, белый

10. Глубокая Зима:
- Глаза: ТОЛЬКО темно-карие, темно-ореховые, светло-голубые
- Волосы: ТОЛЬКО черные, темно-каштановые
- Кожа: ТОЛЬКО светлая с холодным или оливковым подтоном (НЕ персиковая, НЕ тёплая)
- Контрастность: высокая или экстремально высокая
- Рекомендуемые цвета: тёмно-синий, тёмно-фиолетовый, тёмно-зелёный, тёмно-розовый, чёрный, белый, серебряный
- Цвета, которых следует избегать: светлые цвета, тёплые оттенки, пастельные тона, бежевый

11. Холодная Зима:
- Глаза: ТОЛЬКО холодный серый, серо-синий, ясный серо-зелёный, карий. НЕВОЗМОЖНЫ тёплые зелёные, тёплые оливковые, ореховые, янтарные глаза, а также мутные, жёлто-зелёные, коричневато-зелёные оттенки.
- Волосы: ТОЛЬКО иссине-черные, черные, темно-каштановые с холодным подтоном
- Кожа: ТОЛЬКО фарфоровый розовый, бежевый, бежево-розовый, без тёплого или золотистого подтона
- Контрастность: высокая или экстремально высокая
- Рекомендуемые цвета: королевский синий, изумрудный, фиолетовый, розовый, белый, чёрный, серебряный
- Цвета, которых следует избегать: тёплые оттенки, приглушённые тона, пастельные цвета, бежевый

12. Яркая Зима:
- Глаза: ТОЛЬКО ярко-голубые, холодные светлые, ясные зелёные
- Волосы: ТОЛЬКО черные, темно-каштановые
- Кожа: ТОЛЬКО светлая с розовым подтоном
- Контрастность: высокая или экстремально высокая
- Рекомендуемые цвета: яркий розовый, яркий синий, яркий фиолетовый, яркий зелёный, белый, чёрный, красный
- Цвета, которых следует избегать: приглушённые тона, тёплые оттенки, пастельные цвета, бежевый

Верни ТОЛЬКО JSON-объект в формате:
{{
  "color_type": "название цветотипа",
  "explanation": "подробное объяснение выбора цветотипа, включая описание соответствия или несоответствия характеристикам из статей и контрастности",
  "characteristics": {{
    "temperature": "тёплый/холодный/нейтральный",
    "brightness": "светлый/тёмный/средний",
    "saturation": "яркий/мягкий/глубокий",
    "contrast": "{contrast_level}"
  }},
  "recommended_colors": ["список рекомендуемых цветов из статьи"],
  "avoid_colors": ["список цветов, которых следует избегать из статьи"],
  "color_combinations": ["список рекомендуемых цветовых сочетаний из статьи"]
}}"""

            # Функция для анализа цветотипа с повторными попытками
            def analyze_color_type_with_retry():
                for attempt in range(max_retries + 1):  # Увеличиваем количество попыток
                    try:
                        print(f"\nAttempt {attempt + 1} of {max_retries + 1} for color type")
                        
                        color_type_response = self.openai_client.chat.completions.create(
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
                            max_tokens=500,  # Увеличиваем лимит токенов
                            temperature=0.3
                        )

                        color_type_result = color_type_response.choices[0].message.content
                        print("Color type from GPT:", color_type_result)

                        # Проверяем, не отказался ли GPT от анализа
                        if "I'm sorry" in color_type_result or "I can't help" in color_type_result:
                            print(f"GPT refused to analyze color type on attempt {attempt + 1}")
                            if attempt < max_retries:
                                print(f"Waiting {retry_delay} seconds before next attempt...")
                                time.sleep(retry_delay)
                                continue
                            return None

                        # Парсим JSON с цветотипом
                        try:
                            color_type_result = color_type_result.strip()
                            if color_type_result.startswith('```json'):
                                color_type_result = color_type_result[7:]
                            if color_type_result.startswith('```'):
                                color_type_result = color_type_result[3:]
                            if color_type_result.endswith('```'):
                                color_type_result = color_type_result[:-3]
                            color_type_result = color_type_result.strip()

                            print("\nRaw color type result:")
                            print(color_type_result)

                            color_type_data = json.loads(color_type_result)
                            print("\nParsed color type data:")
                            print(json.dumps(color_type_data, ensure_ascii=False, indent=2))

                            # Проверяем и заполняем пустые поля
                            if not color_type_data.get('color_type') or color_type_data['color_type'].strip() == '':
                                print("Color type is empty, using default")
                                color_type_data['color_type'] = 'не определено'

                            if not color_type_data.get('explanation') or color_type_data['explanation'].strip() == '':
                                print("Explanation is empty, using default")
                                color_type_data['explanation'] = 'Не удалось определить цветотип'

                            # Проверяем характеристики
                            characteristics = color_type_data.get('characteristics', {})
                            if not characteristics.get('temperature') or characteristics['temperature'].strip() == '':
                                characteristics['temperature'] = 'не определено'
                            if not characteristics.get('brightness') or characteristics['brightness'].strip() == '':
                                characteristics['brightness'] = 'не определено'
                            if not characteristics.get('saturation') or characteristics['saturation'].strip() == '':
                                characteristics['saturation'] = 'не определено'
                            if not characteristics.get('contrast') or characteristics['contrast'].strip() == '':
                                characteristics['contrast'] = 'не определено'
                            color_type_data['characteristics'] = characteristics

                            # Проверяем и заполняем пустые массивы
                            if not color_type_data.get('recommended_colors'):
                                color_type_data['recommended_colors'] = []
                            if not color_type_data.get('avoid_colors'):
                                color_type_data['avoid_colors'] = []
                            if not color_type_data.get('color_combinations'):
                                color_type_data['color_combinations'] = []

                            # Проверяем, что все цвета в массивах не пустые
                            color_type_data['recommended_colors'] = [c for c in color_type_data['recommended_colors'] if c and c.strip()]
                            color_type_data['avoid_colors'] = [c for c in color_type_data['avoid_colors'] if c and c.strip()]
                            color_type_data['color_combinations'] = [c for c in color_type_data['color_combinations'] if c and c.strip()]

                            # Если все массивы пустые, добавляем дефолтные значения
                            if not color_type_data['recommended_colors']:
                                color_type_data['recommended_colors'] = ['#000000']
                            if not color_type_data['avoid_colors']:
                                color_type_data['avoid_colors'] = ['#000000']
                            if not color_type_data['color_combinations']:
                                color_type_data['color_combinations'] = ['не определено']

                            print("\nFinal color type data:")
                            print(json.dumps(color_type_data, ensure_ascii=False, indent=2))

                            # --- Пост-валидация: если волосы чёрные, кожа светлая (v > 70), глаза холодные — всегда Холодная Зима ---
                            hair_name = colors['hair_color']['name'].lower()
                            skin_temp = self.get_color_temperature(colors['skin_color']['hex'])
                            eye_name = colors['eye_color']['name'].lower()
                            eye_temp = self.get_color_temperature(colors['eye_color']['hex'])
                            r, g, b = self.hex_to_rgb(colors['skin_color']['hex'])
                            _, _, v_skin = self.rgb_to_hsv(r, g, b)
                            r, g, b = self.hex_to_rgb(colors['eye_color']['hex'])
                            _, _, v_eye = self.rgb_to_hsv(r, g, b)
                            contrast = contrast_level
                            # Холодная Зима пост-валидация
                            if (
                                ('чёрный' in hair_name or 'черный' in hair_name) and
                                v_skin > 70 and
                                eye_temp == 'холодный'
                            ):
                                print('Пост-валидация: волосы чёрные, кожа светлая, глаза холодные — это всегда Холодная Зима')
                                color_type_data['color_type'] = 'Холодная Зима'
                                color_type_data['explanation'] += '\nПост-валидация: волосы чёрные, кожа светлая, глаза холодные — это классический признак Холодной Зимы.'
                            # Яркая Весна пост-валидация
                            if (
                                color_type_data.get('color_type', '').lower() == 'глубокая осень' and
                                'зел' in eye_name and
                                v_eye > 60
                            ):
                                print('Пост-валидация: глаза зелёные и светлые — это не Глубокая Осень, а Яркая Весна')
                                color_type_data['color_type'] = 'Яркая Весна'
                                color_type_data['explanation'] += '\nПост-валидация: глаза зелёные и светлые — это характерно для Яркой Весны, а не для Глубокой Осени.'
                            # Тёплая Осень пост-валидация
                            if (
                                color_type_data.get('color_type', '').lower() == 'глубокая осень' and
                                not ('темно' in hair_name or 'тёмно' in hair_name or 'черн' in hair_name) and
                                any(x in colors['skin_color']['name'].lower() for x in ['персик', 'медов', 'золот', 'беж'] )
                            ):
                                print('Пост-валидация: волосы не очень тёмные и кожа персиковая/медовая/бежево-золотистая — это Тёплая Осень')
                                color_type_data['color_type'] = 'Тёплая Осень'
                                color_type_data['explanation'] += '\nПост-валидация: волосы не очень тёмные и кожа персиковая/медовая/бежево-золотистая — это характерно для Тёплой Осени, а не для Глубокой Осени.'

                            # --- ДОБАВЛЕНО: если color_type определён, но массивы цветов пустые, заполняем их по color_type ---
                            if color_type_data.get('color_type', '').lower() not in ['', 'не определено']:
                                if not color_type_data.get('recommended_colors'):
                                    color_type_data['recommended_colors'] = self.get_color_recommendations(color_type_data['color_type']).get('recommended_colors', [])
                                if not color_type_data.get('avoid_colors'):
                                    color_type_data['avoid_colors'] = self.get_color_recommendations(color_type_data['color_type']).get('avoid_colors', [])
                                if not color_type_data.get('color_combinations'):
                                    color_type_data['color_combinations'] = []

                            return color_type_data

                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {str(e)}")
                            if attempt < max_retries - 1:
                                continue
                            return None

                    except Exception as e:
                        print(f"Error on attempt {attempt + 1}: {str(e)}")
                        if attempt < max_retries:
                            print(f"Waiting {retry_delay} seconds before next attempt...")
                            time.sleep(retry_delay)
                        else:
                            return None

            # Получаем цветотип с повторными попытками
            color_type_data = analyze_color_type_with_retry()
            if color_type_data is None:
                print("Failed to analyze color type after all attempts")
                return None

            print("\nColor type analysis result:")
            print(json.dumps(color_type_data, ensure_ascii=False, indent=2))

            # --- ВОЗВРАЩАЕМ ПРЕСЕТ ДЛЯ ОПРЕДЕЛЁННОГО ЦВЕТОТИПА ---
            preset_result = self.get_preset_analysis(color_type_data.get('color_type', ''))
            if preset_result:
                # Можно добавить в preset_result реальные цвета кожи/волос/глаз, если нужно
                preset_result['colors']['skin']['hex'] = colors['skin_color']['hex']
                preset_result['colors']['skin']['name'] = colors['skin_color']['name']
                preset_result['colors']['hair']['hex'] = colors['hair_color']['hex']
                preset_result['colors']['hair']['name'] = colors['hair_color']['name']
                preset_result['colors']['eyes']['hex'] = colors['eye_color']['hex']
                preset_result['colors']['eyes']['name'] = colors['eye_color']['name']
                return preset_result

            # Если пресета нет, возвращаем старый analysis
            # ... существующий код формирования analysis ...

            # Проверяем и дополняем данные о цветотипе
            if not isinstance(color_type_data, dict):
                print("Invalid color type data format")
                return None

            # Получаем рекомендации по цветам
            color_recommendations = self.get_color_recommendations(color_type_data.get('color_type', ''))
            print("\nColor recommendations:")
            print(json.dumps(color_recommendations, ensure_ascii=False, indent=2))

            # Формируем итоговый результат
            analysis = {
                "image": {
                    "format": img.format,
                    "width": width,
                    "height": height
                },
                "colors": {
                    "skin": {
                        "hex": colors['skin_color']['hex'],
                        "name": colors['skin_color']['name'],
                        "temperature": self.get_color_temperature(colors['skin_color']['hex']),
                        "brightness": self.get_color_brightness(colors['skin_color']['hex'])
                    },
                    "hair": {
                        "hex": colors['hair_color']['hex'],
                        "name": colors['hair_color']['name'],
                        "temperature": self.get_color_temperature(colors['hair_color']['hex']),
                        "brightness": self.get_color_brightness(colors['hair_color']['hex'])
                    },
                    "eyes": {
                        "hex": colors['eye_color']['hex'],
                        "name": colors['eye_color']['name'],
                        "temperature": self.get_color_temperature(colors['eye_color']['hex']),
                        "brightness": self.get_color_brightness(colors['eye_color']['hex'])
                    }
                },
                "color_type": color_type_data.get('color_type', 'Не определен'),
                "explanation": color_type_data.get('explanation', 'Нет объяснения'),
                "characteristics": color_type_data.get('characteristics', {
                    "temperature": "не определено",
                    "brightness": "не определено",
                    "saturation": "не определено",
                    "contrast": contrast_level
                }),
                "recommended_colors": color_type_data.get('recommended_colors', []),
                "avoid_colors": color_type_data.get('avoid_colors', []),
                "color_combinations": color_type_data.get('color_combinations', [])
            }

            # Добавляем тёмные цвета для Светлой Весны
            color_type_normalized = analysis["color_type"].strip().lower().replace("ё", "е")
            print(f"[DEBUG] color_type_normalized: {color_type_normalized}")
            if color_type_normalized in ["светлая весна", "светлая весна.", "svetlaya vesna", "svetlayavesna"]:
                analysis["dark_colors"] = [
                    {"name": "Тёмно-серый", "hex": "#6B726C"},
                    {"name": "Тёплый серый", "hex": "#88867D"},
                    {"name": "Тёмно-коричневый", "hex": "#6A564C"},
                    {"name": "Тёплый коричневый", "hex": "#8B7352"},
                    {"name": "Красновато-коричневый", "hex": "#8B6352"},
                    {"name": "Тёмная бирюза", "hex": "#368B82"},
                    {"name": "Тёмный аквамарин", "hex": "#2B8A9A"},
                    {"name": "Тёмно-синий", "hex": "#2B6C99"},
                    {"name": "Тёмно-васильковый", "hex": "#39548A"},
                    {"name": "Тёмно-фиолетовый", "hex": "#63518A"}
                ]
                analysis["dark_colors_hex"] = [
                    "#6B726C", "#88867D", "#6A564C", "#8B7352", "#8B6352",
                    "#368B82", "#2B8A9A", "#2B6C99", "#39548A", "#63518A"
                ]
                # Яркие цвета для Светлой Весны (HEX-коды из вашей палитры)
                analysis["bright_colors_hex"] = [
                    "#89C97A", "#F5D06F", "#F7A18A", "#F7A86A", "#F76C6C", "#F76C8C", "#F7B6B6",
                    "#5FC16E", "#36B6A2", "#7AC1E4", "#6A8AC7", "#395BAA", "#A18AC7"
                ]
                # Светлые цвета для Светлой Весны (HEX-коды из вашей палитры)
                analysis["light_colors_hex"] = [
                    "#EDE0C8", "#F3D1C4", "#F7B8A3", "#F7C6A3", "#FCD494", "#F8E37A", "#C7E3A3",
                    "#97D7D3", "#7ED1B8", "#8ED4E8", "#A3D1E8", "#B8A3D1", "#F7B8C8", "#F7A3A3"
                ]
                # Цветовые сочетания для Светлой Весны (HEX-коды)
                analysis["color_combinations_hex"] = [
                    ["#FCD494", "#6B5A8A"],
                    ["#A3D1E8", "#395BAA", "#F8E37A"],
                    ["#F7B8C8", "#6B726C", "#BDB89A"],
                    ["#EDE0C8", "#8B6352", "#F7A86A"],
                    ["#F76C8C", "#D9C7A3"],
                    ["#5FC16E", "#F8E37A", "#368B82"]
                ]
                # SVG-композиции для цветовых сочетаний (гардероб: верх, низ, обувь, украшения)
                analysis["color_combinations_svg"] = [
                    [
                        {"type": "rect", "color": "#F9D7B5", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#6B418A", "x": 0, "y": 110, "width": 60, "height": 110}
                    ],
                    [
                        {"type": "rect", "color": "#A3D1E8", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#295A8A", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#F8E37A", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#F8E37A", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#F8E37A", "x": 32, "y": 140, "width": 28, "height": 28}
                    ],
                    [
                        {"type": "rect", "color": "#F7B8C8", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#6B726C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#BDB89A", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#F6E3CF", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#8B7352", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#F9D77A", "x": 10, "y": 0, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#F7A3A3", "x": 0, "y": 0, "width": 60, "height": 220},
                        {"type": "ellipse", "color": "#F8E37A", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#F8E37A", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#E6D3B3", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#6BCB4A", "x": 0, "y": 0, "width": 20, "height": 110},
                        {"type": "rect", "color": "#F8E37A", "x": 20, "y": 0, "width": 20, "height": 110},
                        {"type": "rect", "color": "#6BCB4A", "x": 40, "y": 0, "width": 20, "height": 110},
                        {"type": "rect", "color": "#2B8A7A", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#295A8A", "x": 15, "y": 108, "width": 30, "height": 4}
                    ]
                ]

            # Добавляем тёмные цвета для Тёплой Весны
            if color_type_normalized in [
                "тёплая весна", "теплая весна", "тёплая весна.", "теплая весна.", "warm spring", "warmspring"
            ]:
                analysis["dark_colors"] = [
                    {"name": "Тёмно-серый", "hex": "#5F574E"},
                    {"name": "Коричневый", "hex": "#7A5C3A"},
                    {"name": "Тёмно-коричневый", "hex": "#4A362D"},
                    {"name": "Красновато-коричневый", "hex": "#8B4C3B"},
                    {"name": "Тёплый коричневый", "hex": "#875040"},
                    {"name": "Тёмно-зелёный", "hex": "#21753B"},
                    {"name": "Зелёный", "hex": "#1B7A5C"},
                    {"name": "Бирюзовый", "hex": "#1B9797"},
                    {"name": "Тёмно-синий", "hex": "#14416A"},
                    {"name": "Фиолетовый", "hex": "#6B418A"}
                ]
                analysis["dark_colors_hex"] = [
                    "#5F574E", "#7A5C3A", "#4A362D", "#8B4C3B", "#875040",
                    "#21753B", "#1B7A5C", "#1B9797", "#14416A", "#6B418A"
                ]
                # Яркие цвета для Тёплой Весны (HEX-коды из вашей палитры)
                analysis["bright_colors_hex"] = [
                    "#E8BC4A", "#EBC77A", "#E3B184", "#B7C44A", "#3AAA49", "#6BCB4A", "#44C97A",
                    "#F77C5A", "#E84A4A", "#1BAA8A", "#24A7A7", "#5A7CE8", "#A74AC9"
                ]
                # Светлые цвета для Тёплой Весны (HEX-коды из вашей палитры)
                analysis["light_colors_hex"] = [
                    "#F6E3CF", "#F9D7B5", "#E7D89B", "#F6C1A1", "#F6DF9B", "#CFE07A", "#7ED97A",
                    "#C7C9BC", "#C9B18C", "#C99BD1", "#A1B8E7", "#F67C7A", "#F6B1A1", "#44C9A7"
                ]
                # Цветовые сочетания для Тёплой Весны (HEX-коды)
                analysis["color_combinations_hex"] = [
                    ["#FCD494", "#6B5A8A"],
                    ["#A3D1E8", "#395BAA", "#F8E37A"],
                    ["#F7B8C8", "#6B726C", "#BDB89A"],
                    ["#EDE0C8", "#8B6352", "#F7A86A"],
                    ["#F76C8C", "#D9C7A3"],
                    ["#5FC16E", "#F8E37A", "#368B82"]
                ]
                # SVG-композиции для цветовых сочетаний (гардероб: верх, низ, обувь, украшения)
                analysis["color_combinations_svg"] = [
                    [
                        {"type": "rect", "color": "#E8BC4A", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#5F362D", "x": 0, "y": 110, "width": 60, "height": 110}
                    ],
                    [
                        {"type": "rect", "color": "#F6C1A1", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#7A5C3A", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#F9D7B5", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#F9D7B5", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#F77C5A", "x": 32, "y": 80, "width": 28, "height": 28}
                    ],
                    [
                        {"type": "rect", "color": "#A1B8E7", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#14416A", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#1B7AE7", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#CFE07A", "x": 0, "y": 0, "width": 60, "height": 100},
                        {"type": "rect", "color": "#5F574E", "x": 0, "y": 100, "width": 60, "height": 120},
                        {"type": "rect", "color": "#E8BC4A", "x": 0, "y": 98, "width": 60, "height": 8}
                    ],
                    [
                        {"type": "rect", "color": "#44C9A7", "x": 0, "y": 0, "width": 60, "height": 200},
                        {"type": "ellipse", "color": "#F9D7B5", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#F9D7B5", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#7E7B6A", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#E84A4A", "x": 0, "y": 0, "width": 20, "height": 110},
                        {"type": "rect", "color": "#F6E3CF", "x": 20, "y": 0, "width": 20, "height": 110},
                        {"type": "rect", "color": "#E84A4A", "x": 40, "y": 0, "width": 20, "height": 110},
                        {"type": "rect", "color": "#4A362D", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#E3B184", "x": 32, "y": 140, "width": 28, "height": 28}
                    ]
                ]

            # Добавляем тёмные цвета для Яркой Весны
            if color_type_normalized in [
                "яркая весна", "яркая весна.", "bright spring", "brightspring"
            ]:
                analysis["dark_colors"] = [
                    {"name": "Тёмно-серый", "hex": "#636968"},
                    {"name": "Тёплый серо-коричневый", "hex": "#72665C"},
                    {"name": "Графитовый", "hex": "#3E4343"},
                    {"name": "Чёрный", "hex": "#232323"},
                    {"name": "Тёмно-синий", "hex": "#1B4062"},
                    {"name": "Красно-коричневый", "hex": "#B1463B"},
                    {"name": "Тёмно-зелёный", "hex": "#25462C"},
                    {"name": "Зелёный", "hex": "#317338"},
                    {"name": "Бирюзовый", "hex": "#176973"},
                    {"name": "Фиолетовый", "hex": "#3B326E"},
                    {"name": "Сливовый", "hex": "#8A2B5A"},
                    {"name": "Ярко-розовый", "hex": "#D13C6B"}
                ]
                analysis["dark_colors_hex"] = [
                    "#636968", "#72665C", "#3E4343", "#232323", "#1B4062", "#B1463B",
                    "#25462C", "#317338", "#176973", "#3B326E", "#8A2B5A", "#D13C6B"
                ]
                analysis["bright_colors_hex"] = [
                    "#E94382", "#FF7CB5", "#E95CA0", "#D94C7A", "#D94C5C", "#F05C5C", "#FF7C6C", "#FF9C9C",
                    "#1878C2", "#6C4CA0", "#1C8C8C", "#4CA03C", "#A0C24C", "#F0B24C", "#FFD47C"
                ]
                analysis["light_colors_hex"] = [
                    "#E9DFC6", "#E7E3D5", "#C9DC7C", "#A7E3DD", "#B3E6F2", "#C2C6E7", "#F9CFC6",
                    "#EAE6B7", "#FFD07C", "#F7A9C2", "#F78BCB", "#4CD7DE", "#A07CD7", "#F7A9B2"
                ]
                analysis["color_combinations_svg"] = [
                    [
                        {"type": "rect", "color": "#D94C5C", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#232623", "x": 0, "y": 110, "width": 60, "height": 110}
                    ],
                    [
                        {"type": "rect", "color": "#F9CFC6", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#1C8C8C", "cx": 30, "cy": 30, "rx": 18, "ry": 28, "stroke": "#1C8C8C", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#1B4062", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#C2B8B5", "x": 18, "y": 90, "width": 28, "height": 28}
                    ],
                    [
                        {"type": "rect", "color": "#A0C24C", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#25462C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#72665C", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#FFD47C", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#72665C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#3E4343", "x": 0, "y": 108, "width": 60, "height": 8},
                        {"type": "rect", "color": "#1C8C8C", "x": 16, "y": 0, "width": 28, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#E95CA0", "x": 0, "y": 0, "width": 60, "height": 220},
                        {"type": "ellipse", "color": "#C2C6E7", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#C2C6E7", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#A07CD7", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#1878C2", "x": 0, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#A7E3DD", "x": 18, "y": 0, "width": 24, "height": 110},
                        {"type": "rect", "color": "#1878C2", "x": 42, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#6C4CA0", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#3E4343", "x": 15, "y": 108, "width": 30, "height": 4}
                    ]
                ]

            # Добавляем тёмные цвета для Холодного Лета
            if color_type_normalized in [
                "холодное лето", "холодное лето.", "cool summer", "coolsummer"
            ]:
                analysis["dark_colors"] = [
                    {"name": "Серо-коричневый", "hex": "#635C56"},
                    {"name": "Серо-лиловый", "hex": "#72666C"},
                    {"name": "Графитовый", "hex": "#564E52"},
                    {"name": "Серо-сливовый", "hex": "#6C5A5C"},
                    {"name": "Тёмно-сливовый", "hex": "#4C3A3C"},
                    {"name": "Тёмно-серый", "hex": "#43484C"},
                    {"name": "Тёмно-бирюзовый", "hex": "#23545C"},
                    {"name": "Бордовый", "hex": "#732C3C"},
                    {"name": "Сливовый", "hex": "#8A2B5A"},
                    {"name": "Тёмно-бирюзовый", "hex": "#17696C"},
                    {"name": "Тёмно-зелёный", "hex": "#184C3C"},
                    {"name": "Тёмно-синий", "hex": "#23426C"},
                    {"name": "Тёмно-фиолетовый", "hex": "#4C4A6C"},
                    {"name": "Графитово-синий", "hex": "#32324C"}
                ]
                analysis["dark_colors_hex"] = [
                    "#635C56", "#72666C", "#564E52", "#6C5A5C", "#4C3A3C", "#43484C", "#23545C",
                    "#732C3C", "#8A2B5A", "#17696C", "#184C3C", "#23426C", "#4C4A6C", "#32324C"
                ]
                # Яркие цвета для cool_summer (14 цветов из скриншота)
                analysis["bright_colors_hex"] = [
                    "#b0405a", "#e07a98", "#e05a6d", "#f48a9a", "#8a345a", "#b05a8a", "#5a4a7a",
                    "#24918c", "#29897a", "#17696c", "#3a6f7a", "#3ac1cc", "#5a8aac", "#7a7aac"
                ]
                # Светлые цвета для cool_summer (14 цветов из скриншота)
                analysis["light_colors_hex"] = [
                    "#e5e4db", "#bfc2b4", "#ece6b2", "#c5bcbc", "#a2b1b6", "#a3bcbc", "#ffc7da",
                    "#6ec8b7", "#5fd1c7", "#5fc7e1", "#3fc1cc", "#8ac6e8", "#a3aed8", "#7a7aac"
                ]
                # Генерируем гармоничные сочетания (8-12 штук, 2-3 цвета из разных палитр)
                color_combinations = []
                used = set()
                for _ in range(10):
                    combo = []
                    # Выбираем по одному цвету из каждой палитры
                    bright = random.choice(analysis["bright_colors_hex"])
                    light = random.choice(analysis["light_colors_hex"])
                    dark = random.choice(analysis["dark_colors_hex"])
                    # Случайно решаем, будет ли сочетание из 2 или 3 цветов
                    if random.random() < 0.5:
                        combo = [bright, light, dark]
                    else:
                        combo = random.sample([bright, light, dark], 2)
                    # Чтобы не было одинаковых сочетаний
                    combo_tuple = tuple(sorted(combo))
                    if combo_tuple not in used:
                        color_combinations.append(combo)
                        used.add(combo_tuple)
                analysis["color_combinations"] = color_combinations

                # SVG-комбинации для cool_summer (пиксель-в-пиксель как на референсе)
                svg_templates = [
                    # 1. Два вертикальных прямоугольника (верх+низ)
                    [
                        {"type": "rect", "color": random.choice(analysis["light_colors_hex"]), "x": 0, "y": 0, "width": 160, "height": 220},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 0, "y": 110, "width": 160, "height": 110}
                    ],
                    # 2. Верх+низ+овал+малый rect
                    [
                        {"type": "rect", "color": random.choice(analysis["light_colors_hex"]), "x": 180, "y": 0, "width": 160, "height": 220},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 180, "y": 110, "width": 160, "height": 110},
                        {"type": "ellipse", "color": random.choice(analysis["bright_colors_hex"]), "cx": 260, "cy": 50, "rx": 40, "ry": 48, "stroke": random.choice(analysis["bright_colors_hex"]), "strokeWidth": 4, "fill": "none"},
                        {"type": "rect", "color": random.choice(analysis["bright_colors_hex"]), "x": 240, "y": 120, "width": 60, "height": 48}
                    ],
                    # 3. Верх+низ+малый rect снизу
                    [
                        {"type": "rect", "color": random.choice(analysis["bright_colors_hex"]), "x": 360, "y": 0, "width": 160, "height": 220},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 360, "y": 110, "width": 160, "height": 110},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 410, "y": 200, "width": 60, "height": 32}
                    ],
                    # 4. Верх+низ+полоска сверху+полоска между
                    [
                        {"type": "rect", "color": random.choice(analysis["bright_colors_hex"]), "x": 540, "y": 0, "width": 160, "height": 220},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 540, "y": 110, "width": 160, "height": 110},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 580, "y": 0, "width": 80, "height": 24},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 540, "y": 110, "width": 160, "height": 12}
                    ],
                    # 5. Один большой rect + овал + малый rect снизу
                    [
                        {"type": "rect", "color": random.choice(analysis["bright_colors_hex"]), "x": 720, "y": 0, "width": 160, "height": 220},
                        {"type": "ellipse", "color": random.choice(analysis["light_colors_hex"]), "cx": 800, "cy": 110, "rx": 40, "ry": 90, "stroke": random.choice(analysis["light_colors_hex"]), "strokeWidth": 4, "fill": "none"},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 760, "y": 200, "width": 80, "height": 32}
                    ],
                    # 6. Три вертикальных полосы сверху + низ
                    [
                        {"type": "rect", "color": random.choice(analysis["bright_colors_hex"]), "x": 900, "y": 0, "width": 40, "height": 110},
                        {"type": "rect", "color": random.choice(analysis["light_colors_hex"]), "x": 940, "y": 0, "width": 80, "height": 110},
                        {"type": "rect", "color": random.choice(analysis["bright_colors_hex"]), "x": 1020, "y": 0, "width": 40, "height": 110},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 900, "y": 110, "width": 160, "height": 110},
                        {"type": "rect", "color": random.choice(analysis["dark_colors_hex"]), "x": 960, "y": 110, "width": 40, "height": 12}
                    ]
                ]
                analysis["color_combinations_svg"] = svg_templates

            # Добавляем SVG-комбинации для Холодного Лета
            if color_type_normalized in [
                "холодное лето", "холодное лето.", "cool summer", "coolsummer"
            ]:
                analysis["color_combinations_svg"] = [
                    [
                        {"type": "rect", "color": "#bfc2b4", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#635C56", "x": 0, "y": 110, "width": 60, "height": 110}
                    ],
                    [
                        {"type": "rect", "color": "#e5e4db", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#3ac1cc", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#3ac1cc", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#4C3A3C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#e07a98", "x": 32, "y": 80, "width": 28, "height": 28}
                    ],
                    [
                        {"type": "rect", "color": "#8ac6e8", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#23426C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#6C5A5C", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#ece6b2", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#564E52", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#b05a8a", "x": 0, "y": 108, "width": 60, "height": 8},
                        {"type": "rect", "color": "#3ac1cc", "x": 16, "y": 0, "width": 28, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#f48a9a", "x": 0, "y": 0, "width": 60, "height": 220},
                        {"type": "ellipse", "color": "#a3aed8", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3aed8", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#635C8C", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#24918c", "x": 0, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#e5e4db", "x": 18, "y": 0, "width": 24, "height": 110},
                        {"type": "rect", "color": "#24918c", "x": 42, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#72666C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#564E52", "x": 15, "y": 108, "width": 30, "height": 4}
                    ]
                ]

            # Добавляем SVG-комбинации для Холодного Лета
            if color_type_normalized in [
                "холодное лето", "холодное лето.", "cool summer", "coolsummer"
            ]:
                analysis["color_combinations_svg"] = [
                    [
                        {"type": "rect", "color": "#bfc2b4", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#635C56", "x": 0, "y": 110, "width": 60, "height": 110}
                    ],
                    [
                        {"type": "rect", "color": "#e5e4db", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#3ac1cc", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#3ac1cc", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#4C3A3C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#e07a98", "x": 32, "y": 80, "width": 28, "height": 28}
                    ],
                    [
                        {"type": "rect", "color": "#8ac6e8", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#23426C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#6C5A5C", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#ece6b2", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#564E52", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#b05a8a", "x": 0, "y": 108, "width": 60, "height": 8},
                        {"type": "rect", "color": "#3ac1cc", "x": 16, "y": 0, "width": 28, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#f48a9a", "x": 0, "y": 0, "width": 60, "height": 220},
                        {"type": "ellipse", "color": "#a3aed8", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3aed8", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#635C8C", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#24918c", "x": 0, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#e5e4db", "x": 18, "y": 0, "width": 24, "height": 110},
                        {"type": "rect", "color": "#24918c", "x": 42, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#72666C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#564E52", "x": 15, "y": 108, "width": 30, "height": 4}
                    ]
                ]

            # Добавляем SVG-комбинации для Холодного Лета
            if color_type_normalized in [
                "холодное лето", "холодное лето.", "cool summer", "coolsummer"
            ]:
                analysis["color_combinations_svg"] = [
                    [
                        {"type": "rect", "color": "#bfc2b4", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#635C56", "x": 0, "y": 110, "width": 60, "height": 110}
                    ],
                    [
                        {"type": "rect", "color": "#e5e4db", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#3ac1cc", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#3ac1cc", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#4C3A3C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#e07a98", "x": 32, "y": 80, "width": 28, "height": 28}
                    ],
                    [
                        {"type": "rect", "color": "#8ac6e8", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#23426C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#6C5A5C", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#ece6b2", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#564E52", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#b05a8a", "x": 0, "y": 108, "width": 60, "height": 8},
                        {"type": "rect", "color": "#3ac1cc", "x": 16, "y": 0, "width": 28, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#f48a9a", "x": 0, "y": 0, "width": 60, "height": 220},
                        {"type": "ellipse", "color": "#a3aed8", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3aed8", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#635C8C", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#24918c", "x": 0, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#e5e4db", "x": 18, "y": 0, "width": 24, "height": 110},
                        {"type": "rect", "color": "#24918c", "x": 42, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#72666C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#564E52", "x": 15, "y": 108, "width": 30, "height": 4}
                    ]
                ]

            # Добавляем SVG-комбинации для Холодного Лета
            if color_type_normalized in [
                "холодное лето", "холодное лето.", "cool summer", "coolsummer"
            ]:
                analysis["color_combinations_svg"] = [
                    [
                        {"type": "rect", "color": "#bfc2b4", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#635C56", "x": 0, "y": 110, "width": 60, "height": 110}
                    ],
                    [
                        {"type": "rect", "color": "#e5e4db", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#3ac1cc", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#3ac1cc", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#4C3A3C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#e07a98", "x": 32, "y": 80, "width": 28, "height": 28}
                    ],
                    [
                        {"type": "rect", "color": "#8ac6e8", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#23426C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#6C5A5C", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#ece6b2", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#564E52", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#b05a8a", "x": 0, "y": 108, "width": 60, "height": 8},
                        {"type": "rect", "color": "#3ac1cc", "x": 16, "y": 0, "width": 28, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#f48a9a", "x": 0, "y": 0, "width": 60, "height": 220},
                        {"type": "ellipse", "color": "#a3aed8", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3aed8", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#635C8C", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#24918c", "x": 0, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#e5e4db", "x": 18, "y": 0, "width": 24, "height": 110},
                        {"type": "rect", "color": "#24918c", "x": 42, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#72666C", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#564E52", "x": 15, "y": 108, "width": 30, "height": 4}
                    ]
                ]

            print("\nFinal analysis result:")
            print(json.dumps(analysis, ensure_ascii=False, indent=2))

            # --- ДОБАВЛЯЕМ ПАЛИТРЫ И SVG ИЗ ПРЕСЕТА ДЛЯ ВСЕХ ПОДДЕРЖИВАЕМЫХ ЦВЕТОТИПОВ ---
            preset = self.get_preset_analysis(color_type_normalized)
            if preset:
                for key in [
                    "dark_colors_hex", "bright_colors_hex", "light_colors_hex",
                    "color_combinations_svg", "dark_colors", "bright_colors", "light_colors"
                ]:
                    if key in preset:
                        analysis[key] = preset[key]

            # Добавляем палитры и SVG для Яркой Зимы (bright winter), как для светлой весны
            if color_type_normalized in ["яркая зима", "яркая зима.", "bright winter", "brightwinter"]:
                analysis["dark_colors_hex"] = [
                    "#111111", "#444949", "#6B6A66", "#18514D", "#187144", "#1B7C8C", "#176A8C"
                ]
                analysis["bright_colors_hex"] = [
                    "#F7E37A", "#FFD47C", "#B7DC4A", "#8CB74A", "#1CB75A", "#3AD7A7", "#1CA7A7",
                    "#1C8C8C", "#1C5AA7", "#3A6FA7", "#4C7AE7", "#6A4CA7", "#A74AC9", "#F77C7A",
                    "#F05C5C", "#FF7CB5", "#E94382", "#D94C7A", "#E95CA0"
                ]
                analysis["light_colors_hex"] = [
                    "#FFFFFF", "#D7DBDB", "#F7E1B2", "#F7B8C8", "#B2E7E7", "#E7E1D6", "#F7C6A3",
                    "#E7C6A3", "#E7A3B2", "#E7B8C8", "#E7E7E1", "#B2A3D1"
                ]
                analysis["color_combinations_svg"] = [
                    [
                        {"type": "rect", "color": "#FFD47C", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#23191A", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#F7E1B2", "cx": 20, "cy": 110, "rx": 28, "ry": 18, "stroke": "#F7E1B2", "strokeWidth": 3, "fill": "none"}
                    ],
                    [
                        {"type": "rect", "color": "#4CC7F7", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#1B2652", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#A74AC9", "cx": 30, "cy": 30, "rx": 18, "ry": 18, "stroke": "#A74AC9", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#A74AC9", "x": 32, "y": 90, "width": 28, "height": 28}
                    ],
                    [
                        {"type": "rect", "color": "#1CB75A", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#444949", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#B7DC4A", "cx": 30, "cy": 60, "rx": 18, "ry": 18, "stroke": "#B7DC4A", "strokeWidth": 3, "fill": "none"}
                    ],
                    [
                        {"type": "rect", "color": "#D94C5C", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#111111", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#FFFFFF", "x": 0, "y": 100, "width": 60, "height": 10}
                    ],
                    [
                        {"type": "rect", "color": "#8A2B5A", "x": 0, "y": 0, "width": 60, "height": 220},
                        {"type": "ellipse", "color": "#FFFFFF", "cx": 30, "cy": 110, "rx": 18, "ry": 60, "stroke": "#FFFFFF", "strokeWidth": 3, "fill": "none"}
                    ],
                    [
                        {"type": "rect", "color": "#F7A9C2", "x": 0, "y": 0, "width": 30, "height": 110},
                        {"type": "rect", "color": "#D94C7A", "x": 30, "y": 0, "width": 30, "height": 110},
                        {"type": "rect", "color": "#23234A", "x": 0, "y": 110, "width": 60, "height": 110}
                    ]
                ]

            if color_type_normalized in ["глубокая осень", "глубокая осень.", "deep autumn", "deepautumn"]:
                # Основная палитра (3x3)
                analysis["main_palette_hex"] = [
                    "#5a6a4a", "#353a3a", "#1e6a5a",
                    "#2a5a6a", "#a34a4a", "#8a3a4a",
                    "#3a3a3a", "#2a3a3a", "#b76a5a"
                ]
                # Дополнительная палитра (4x7)
                analysis["additional_palette_hex"] = [
                    "#c97a9a", "#1e6a6a", "#3a6a4a", "#6a6a4a", "#b7a36a", "#e7c6a3", "#e7a36a",
                    "#a34a6a", "#2a4a6a", "#2a6a3a", "#b7b74a", "#d7b97a", "#a3b76a", "#a39b5a",
                    "#b77a5a", "#b75a7a", "#b76a97", "#c97a9a", "#e7a3b2", "#e7b8c8", "#f7b8a3",
                    "#f7c6a3", "#e7e1a3", "#c7d1a3", "#a3d1a3", "#a3d1c2", "#a3d1d1", "#a3c7c7", "#3a2931"
                ]
                # Стандартные ключи для совместимости
                analysis["dark_colors_hex"] = [
                    "#353a3a", "#3a3a3a", "#2a3a3a", "#2a4a6a", "#1e6a5a", "#1e6a6a", "#3a2931", "#5a6a4a", "#6a6a4a"
                ]
                analysis["bright_colors_hex"] = [
                    "#a34a4a", "#a34a6a", "#b76a5a", "#b75a7a", "#b76a97", "#c97a9a", "#b7b74a", "#b7a36a", "#d7b97a"
                ]
                analysis["light_colors_hex"] = [
                    "#e7c6a3", "#e7a36a", "#e7a3b2", "#e7b8c8", "#f7b8a3", "#f7c6a3", "#e7e1a3", "#c7d1a3", "#a3d1a3"
                ]
                analysis["color_combinations_svg"] = [
                    [
                        {"type": "rect", "color": "#353a3a", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#e7c6a3", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#b7b74a", "cx": 30, "cy": 110, "rx": 28, "ry": 18, "stroke": "#b7b74a", "strokeWidth": 3, "fill": "none"}
                    ],
                    [
                        {"type": "rect", "color": "#1e6a5a", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#a34a4a", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "ellipse", "color": "#e7a3b2", "cx": 30, "cy": 30, "rx": 18, "ry": 18, "stroke": "#e7a3b2", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#b76a97", "x": 32, "y": 90, "width": 28, "height": 28}
                    ],
                    [
                        {"type": "rect", "color": "#3a6a4a", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#2a3a3a", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#b7a36a", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#a34a6a", "x": 0, "y": 0, "width": 60, "height": 110},
                        {"type": "rect", "color": "#6a6a4a", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#e7a36a", "x": 0, "y": 108, "width": 60, "height": 8},
                        {"type": "rect", "color": "#a3d1a3", "x": 16, "y": 0, "width": 28, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#b76a5a", "x": 0, "y": 0, "width": 60, "height": 220},
                        {"type": "ellipse", "color": "#e7b8c8", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#e7b8c8", "strokeWidth": 3, "fill": "none"},
                        {"type": "rect", "color": "#b7b74a", "x": 10, "y": 200, "width": 40, "height": 18}
                    ],
                    [
                        {"type": "rect", "color": "#a34a4a", "x": 0, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#e7c6a3", "x": 18, "y": 0, "width": 24, "height": 110},
                        {"type": "rect", "color": "#a34a4a", "x": 42, "y": 0, "width": 18, "height": 110},
                        {"type": "rect", "color": "#353a3a", "x": 0, "y": 110, "width": 60, "height": 110},
                        {"type": "rect", "color": "#2a3a3a", "x": 15, "y": 108, "width": 30, "height": 4}
                    ]
                ]
                # Описание и рекомендации (по референсу)
                analysis["explanation"] = (
                    "У вас тёмный, тёплый колорит. Ваш цветотип — 'Тёмная осень'. "
                    "Бордовая гамма будет смотреться благородно и сдержанно и подчеркнёт ваши глаза. "
                    "Также ваши лучшие оттенки — светлый персиковый, болотный, тёмный зелёный, оливковый, кэмел, тёмный синий, глубокий красный."
                )

            # --- В КОНЦЕ get_preset_analysis ---
            # Гарантируем наличие всех стандартных ключей и нужную длину
            for key, req_len in [
                ("dark_colors_hex", 9),
                ("bright_colors_hex", 27),
                ("light_colors_hex", 14),
                ("color_combinations_svg", 6)
            ]:
                if key not in analysis:
                    analysis[key] = []
                # Для SVG-комбинаций — просто пустые списки, для цветов — пустые строки
                if key == "color_combinations_svg":
                    while len(analysis[key]) < req_len:
                        analysis[key].append([])
                    if len(analysis[key]) > req_len:
                        analysis[key] = analysis[key][:req_len]
                else:
                    while len(analysis[key]) < req_len:
                        analysis[key].append("")
                    if len(analysis[key]) > req_len:
                        analysis[key] = analysis[key][:req_len]
            # Добавляем основные палитры для совместимости с фронтом
            analysis["main_palette_hex"] = analysis.get("bright_colors_hex", [])[:9]
            analysis["additional_palette_hex"] = analysis.get("bright_colors_hex", [])

            # --- ДОБАВЛЕНО: если определён color_type, но нет палитр, заполняем их по color_type ---
            if color_type_normalized not in ["", "не определено"]:
                preset = self.get_preset_analysis(analysis["color_type"])
                for key in ["dark_colors_hex", "bright_colors_hex", "light_colors_hex"]:
                    if key not in analysis or not analysis[key]:
                        if key in preset:
                            analysis[key] = preset[key]

            # --- Фильтрация: убираем пустые и белые цвета из палитр ---
            def filter_valid_colors(colors):
                return [c for c in colors if c and c.lower() not in ['#fff', '#ffffff']]
            analysis["dark_colors_hex"] = filter_valid_colors(analysis.get("dark_colors_hex", []))
            analysis["bright_colors_hex"] = filter_valid_colors(analysis.get("bright_colors_hex", []))
            analysis["light_colors_hex"] = filter_valid_colors(analysis.get("light_colors_hex", []))

            # --- Если определён color_type и есть пресет, всегда подставлять палитру из пресета ---
            color_type = analysis.get("color_type", "")
            if color_type and color_type.lower() not in ["", "не определено"]:
                preset = self.get_preset_analysis(color_type)
                if preset:
                    for key in ["dark_colors_hex", "bright_colors_hex", "light_colors_hex"]:
                        if key in preset:
                            analysis[key] = preset[key]

            # --- Жёстко подставляем палитры и сочетания из пресета, если определён color_type и есть пресет ---
            color_type = analysis.get("color_type", "")
            if color_type and color_type.lower() not in ["", "не определено"]:
                preset = self.get_preset_analysis(color_type)
                if preset:
                    for key in ["dark_colors_hex", "bright_colors_hex", "light_colors_hex", "color_combinations"]:
                        if key in preset:
                            analysis[key] = preset[key]

            # --- Жёстко подставляем всё из пресета, если определён color_type и есть пресет ---
            color_type = analysis.get("color_type", "")
            if color_type and color_type.lower() not in ["", "не определено"]:
                preset = self.get_preset_analysis(color_type)
                if preset:
                    print("[DEBUG] PRESET:", json.dumps(preset, ensure_ascii=False, indent=2))
                    for key in [
                        "recommended_colors", "avoid_colors", "explanation",
                        "dark_colors_hex", "bright_colors_hex", "light_colors_hex"
                    ]:
                        if key in preset:
                            analysis[key] = preset[key]
                    if "color_combinations_svg" in preset:
                        analysis["color_combinations"] = preset["color_combinations_svg"]
                    print("[DEBUG] ANALYSIS AFTER PRESET:", json.dumps(analysis, ensure_ascii=False, indent=2))

            return analysis

        except Exception as e:
            print(f"Attempt failed: {str(e)}")
            return None

    def rgb_to_hsv(self, r, g, b):
        """Convert RGB to HSV color space"""
        r, g, b = r/255.0, g/255.0, b/255.0
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        return h * 360, s * 100, v * 100

    def analyze_skin_tone(self, colors):
        """Analyze skin tone characteristics"""
        # Calculate weighted average of colors
        total_score = sum(c.get('score', 0) for c in colors if isinstance(c, dict) and 'score' in c)
        
        # Если нет данных о score или total_score равен 0, используем равные веса
        if total_score == 0:
            total_score = len([c for c in colors if isinstance(c, dict) and 'color' in c])
            if total_score == 0:  # Если нет валидных цветов вообще
                return {
                    'is_warm': False,
                    'is_cool': False,
                    'is_neutral': True,
                    'brightness_level': 'medium',
                    'saturation_level': 'medium',
                    'brightness': 50,
                    'saturation': 50,
                    'warm_colors': 0,
                    'cool_colors': 0,
                    'bright_colors': 0,
                    'deep_colors': 0,
                    'soft_colors': 0
                }
            weight = 1.0 / total_score
        else:
            weight = None

        avg_h = 0
        avg_s = 0
        avg_v = 0
        warm_colors = 0
        cool_colors = 0
        bright_colors = 0
        deep_colors = 0
        soft_colors = 0

        valid_colors_count = 0
        for color in colors:
            if not isinstance(color, dict) or 'color' not in color:
                continue
                
            r, g, b = color['color']['red'], color['color']['green'], color['color']['blue']
            h, s, v = self.rgb_to_hsv(r, g, b)
            
            if weight is None:
                w = color.get('score', 0) / total_score
            else:
                w = weight
                
            avg_h += h * w
            avg_s += s * w
            avg_v += v * w
            valid_colors_count += 1

            # Анализ цветовых характеристик
            if 0 <= h <= 30 or 330 <= h <= 360:  # Тёплые цвета (красный, оранжевый, жёлтый)
                warm_colors += w
            elif 150 <= h <= 270:  # Холодные цвета (голубой, синий, фиолетовый)
                cool_colors += w

            if v >= 70:  # Яркие цвета
                bright_colors += w
            elif v <= 40:  # Глубокие цвета
                deep_colors += w
            else:  # Мягкие цвета
                soft_colors += w

        # Если нет валидных цветов, возвращаем нейтральные значения
        if valid_colors_count == 0:
            return {
                'is_warm': False,
                'is_cool': False,
                'is_neutral': True,
                'brightness_level': 'medium',
                'saturation_level': 'medium',
                'brightness': 50,
                'saturation': 50,
                'warm_colors': 0,
                'cool_colors': 0,
                'bright_colors': 0,
                'deep_colors': 0,
                'soft_colors': 0
            }

        # Определение температуры
        is_warm = warm_colors > cool_colors
        is_cool = cool_colors > warm_colors
        is_neutral = abs(warm_colors - cool_colors) < 0.1

        # Определение яркости
        if bright_colors > deep_colors and bright_colors > soft_colors:
            brightness_level = 'high'
        elif deep_colors > bright_colors and deep_colors > soft_colors:
            brightness_level = 'low'
        else:
            brightness_level = 'medium'

        # Определение насыщенности
        if avg_s >= self.THRESHOLDS['saturation']['high']:
            saturation_level = 'high'
        elif avg_s >= self.THRESHOLDS['saturation']['medium']:
            saturation_level = 'medium'
        else:
            saturation_level = 'low'

        return {
            'is_warm': is_warm,
            'is_cool': is_cool,
            'is_neutral': is_neutral,
            'brightness_level': brightness_level,
            'saturation_level': saturation_level,
            'brightness': avg_v,
            'saturation': avg_s,
            'warm_colors': warm_colors,
            'cool_colors': cool_colors,
            'bright_colors': bright_colors,
            'deep_colors': deep_colors,
            'soft_colors': soft_colors
        }

    def analyze_eye_colors(self, eye_colors):
        """Analyze eye color characteristics"""
        if not eye_colors:
            return None

        total_score = sum(c.get('score', 0) for c in eye_colors)
        if total_score == 0:
            total_score = len(eye_colors)
            weight = 1.0 / total_score
        else:
            weight = None

        avg_h = 0
        avg_s = 0
        avg_v = 0
        warm_tones = 0
        cool_tones = 0
        bright_tones = 0
        deep_tones = 0

        for color in eye_colors:
            if not isinstance(color, dict) or 'color' not in color:
                continue
                
            r, g, b = color['color']['red'], color['color']['green'], color['color']['blue']
            h, s, v = self.rgb_to_hsv(r, g, b)
            
            if weight is None:
                w = color.get('score', 0) / total_score
            else:
                w = weight
                
            avg_h += h * w
            avg_s += s * w
            avg_v += v * w

            # Анализ цветовых характеристик глаз
            if 0 <= h <= 30 or 330 <= h <= 360:  # Тёплые оттенки
                warm_tones += w
            elif 150 <= h <= 270:  # Холодные оттенки
                cool_tones += w

            if v >= 70:  # Яркие оттенки
                bright_tones += w
            elif v <= 40:  # Глубокие оттенки
                deep_tones += w

        # Определение основных характеристик цвета глаз
        is_warm = warm_tones > cool_tones
        is_cool = cool_tones > warm_tones
        is_bright = bright_tones > deep_tones
        is_deep = deep_tones > bright_tones

        # Определение типа цвета глаз
        if 0 <= avg_h <= 30 or 330 <= avg_h <= 360:  # Коричневые, янтарные
            eye_type = "тёплый"
        elif 150 <= avg_h <= 270:  # Голубые, серые
            eye_type = "холодный"
        else:  # Зелёные, ореховые
            eye_type = "смешанный"

        return {
            'is_warm': is_warm,
            'is_cool': is_cool,
            'is_bright': is_bright,
            'is_deep': is_deep,
            'eye_type': eye_type,
            'hue': avg_h,
            'saturation': avg_s,
            'brightness': avg_v
        }

    def get_color_recommendations(self, color_type):
        """
        Get color recommendations based on color type
        """
        recommendations = {
            "Тёплая весна": {
                "description": "Тёплые, яркие, солнечные цвета. Подходят насыщенные, но не слишком тёмные оттенки.",
                "recommended_colors": [
                    "Коралловый", "Персиковый", "Тёплый жёлтый",
                    "Тёплый зелёный", "Тёплый бежевый", "Абрикосовый",
                    "Лососевый", "Тёплый розовый", "Тёплый оранжевый"
                ],
                "avoid_colors": [
                    "Холодные оттенки", "Тёмные цвета",
                    "Приглушённые тона", "Чёрный", "Белый"
                ]
            },
            "Светлая весна": {
                "description": "Светлые, нежные, тёплые цвета. Подходят пастельные и мягкие оттенки. Также допустимы некоторые тёмные цвета для акцентов.",
                "recommended_colors": [
                    "Светло-персиковый", "Нежно-жёлтый",
                    "Светло-зелёный", "Светло-бежевый", "Светло-коралловый",
                    "Светло-абрикосовый", "Светло-розовый",
                    "Тёмно-серый", "Тёплый серый", "Тёмно-коричневый", "Тёплый коричневый", "Красновато-коричневый",
                    "Тёмная бирюза", "Тёмный аквамарин", "Тёмно-синий", "Тёмно-васильковый", "Тёмно-фиолетовый"
                ],
                "avoid_colors": [
                    "Тёмные цвета", "Холодные оттенки",
                    "Яркие контрастные цвета", "Чёрный"
                ]
            },
            "Яркая весна": {
                "description": "Яркие, чистые, тёплые цвета. Подходят насыщенные и чистые оттенки.",
                "recommended_colors": [
                    "Яркий коралловый", "Яркий жёлтый",
                    "Яркий зелёный", "Яркий оранжевый", "Яркий розовый",
                    "Бирюзовый", "Белый"
                ],
                "avoid_colors": [
                    "Приглушённые тона", "Тёмные цвета",
                    "Холодные оттенки", "Пастельные тона"
                ]
            },
            "Тёплая осень": {
                "description": "Тёплые, насыщенные, землистые цвета. Подходят природные оттенки.",
                "recommended_colors": [
                    "Терракотовый", "Оливковый", "Тёплый коричневый",
                    "Тёплый зелёный", "Тёплый бежевый", "Медный",
                    "Бордовый", "Тёплый оранжевый"
                ],
                "avoid_colors": [
                    "Холодные оттенки", "Яркие цвета",
                    "Пастельные тона", "Чёрный", "Белый"
                ]
            },
            "Мягкая осень": {
                "description": "Мягкие, приглушённые, тёплые цвета. Подходят сложные оттенки.",
                "recommended_colors": [
                    "Мягкий коричневый", "Мягкий зелёный",
                    "Мягкий бежевый", "Мягкий оливковый", "Мягкий бордовый",
                    "Мягкий терракотовый", "Мягкий оранжевый"
                ],
                "avoid_colors": [
                    "Яркие цвета", "Холодные оттенки",
                    "Чистые тона", "Чёрный", "Белый"
                ]
            },
            "Глубокая осень": {
                "description": "Глубокие, насыщенные, тёплые цвета. Подходят тёмные, но тёплые оттенки.",
                "recommended_colors": [
                    "Тёмно-коричневый", "Тёмно-зелёный",
                    "Тёмно-бордовый", "Тёмно-оливковый", "Тёмно-терракотовый",
                    "Тёмно-оранжевый", "Тёмно-бежевый"
                ],
                "avoid_colors": [
                    "Светлые цвета", "Холодные оттенки",
                    "Пастельные тона", "Белый"
                ]
            },
            "Холодное лето": {
                "description": "Холодные, приглушённые, мягкие цвета. Подходят дымчатые оттенки.",
                "recommended_colors": [
                    "Дымчато-розовый", "Дымчато-голубой",
                    "Дымчато-синий", "Дымчато-фиолетовый", "Серый",
                    "Мягкий сиреневый", "Мягкий голубой"
                ],
                "avoid_colors": [
                    "Тёплые оттенки", "Яркие цвета",
                    "Чистые тона", "Чёрный", "Белый"
                ]
            },
            "Светлое лето": {
                "description": "Светлые, холодные, нежные цвета. Подходят пастельные холодные оттенки.",
                "recommended_colors": [
                    "Светло-голубой", "Светло-розовый",
                    "Светло-сиреневый", "Светло-серый", "Светло-фиолетовый",
                    "Светло-синий", "Светло-зелёный"
                ],
                "avoid_colors": [
                    "Тёмные цвета", "Тёплые оттенки",
                    "Яркие цвета", "Чёрный"
                ]
            },
            "Мягкое лето": {
                "description": "Мягкие, приглушённые, холодные цвета. Подходят сложные холодные оттенки.",
                "recommended_colors": [
                    "Мягкий голубой", "Мягкий розовый",
                    "Мягкий сиреневый", "Мягкий серый", "Мягкий фиолетовый",
                    "Мягкий синий", "Мягкий зелёный"
                ],
                "avoid_colors": [
                    "Яркие цвета", "Тёплые оттенки",
                    "Чистые тона", "Чёрный", "Белый"
                ]
            },
            "Холодная зима": {
                "description": "Холодные, чистые, яркие цвета. Подходят насыщенные холодные оттенки.",
                "recommended_colors": [
                    "Королевский синий", "Изумрудный",
                    "Фиолетовый", "Розовый", "Белый",
                    "Чёрный", "Серебряный"
                ],
                "avoid_colors": [
                    "Тёплые оттенки", "Приглушённые тона",
                    "Пастельные цвета", "Бежевый"
                ]
            },
            "Яркая зима": {
                "description": "Яркие, чистые, контрастные цвета. Подходят насыщенные и чистые оттенки.",
                "recommended_colors": [
                    "Яркий розовый", "Яркий синий",
                    "Яркий фиолетовый", "Яркий зелёный", "Белый",
                    "Чёрный", "Красный"
                ],
                "avoid_colors": [
                    "Приглушённые тона", "Тёплые оттенки",
                    "Пастельные цвета", "Бежевый"
                ]
            },
            "Глубокая зима": {
                "description": "Глубокие, насыщенные, холодные цвета. Подходят тёмные холодные оттенки.",
                "recommended_colors": [
                    "Тёмно-синий", "Тёмно-фиолетовый",
                    "Тёмно-зелёный", "Тёмно-розовый", "Чёрный",
                    "Белый", "Серебряный"
                ],
                "avoid_colors": [
                    "Светлые цвета", "Тёплые оттенки",
                    "Пастельные тона", "Бежевый"
                ]
            }
        }
        
        return recommendations.get(color_type, {
            "description": "Рекомендации для этого цветотипа в разработке",
            "recommended_colors": [],
            "avoid_colors": []
        }) 

    def get_color_name(self, h, s, v):
        """Определяет название цвета на основе HSV"""
        print(f"Getting color name for HSV: h={h}, s={s}, v={v}")  # Отладка
        
        # Сначала проверяем яркость
        if v < 30:  # Очень тёмный
            if s < 20:
                return "чёрный"
            if 0 <= h <= 30 or 330 <= h <= 360:
                return "тёмно-коричневый"
            if 30 < h <= 90:
                return "тёмно-коричневый"
            if 90 < h <= 150:
                return "тёмно-оливковый"
            if 150 < h <= 210:
                return "тёмно-зелёный"
            if 210 < h <= 270:
                return "тёмно-синий"
            if 270 < h <= 330:
                return "тёмно-фиолетовый"
            return "тёмно-серый"
            
        if v > 80:  # Очень светлый
            if s < 20:
                return "белый"
            if 0 <= h <= 30 or 330 <= h <= 360:
                return "розовый"
            if 30 < h <= 90:
                return "персиковый"
            if 90 < h <= 150:
                return "бежевый"
            if 150 < h <= 210:
                return "светло-зелёный"
            if 210 < h <= 270:
                return "голубой"
            if 270 < h <= 330:
                return "сиреневый"
            return "светло-серый"
            
        # Средняя яркость
        if s < 20:  # Низкая насыщенность
            return "серый"
            
        # Нормальная насыщенность
        if 0 <= h <= 30 or 330 <= h <= 360:  # Красные оттенки
            if s > 60:
                return "красный"
            if 20 <= s <= 60 and v >= 60:  # Телесные оттенки
                return "персиковый"
            return "коричневый"
        elif 30 < h <= 90:  # Оранжевые/коричневые оттенки
            if s > 60:
                return "оранжевый"
            if 20 <= s <= 60 and v >= 60:  # Телесные оттенки
                return "персиковый"
            return "коричневый"
        elif 90 < h <= 150:  # Жёлтые/зелёные оттенки
            if s > 60:
                return "жёлтый"
            if 20 <= s <= 60 and v >= 60:  # Телесные оттенки
                return "бежевый"
            return "оливковый"
        elif 150 < h <= 210:  # Зелёные оттенки
            if s > 60:
                return "зелёный"
            return "оливковый"
        elif 210 < h <= 270:  # Голубые/синие оттенки
            if s > 60:
                return "голубой"
            return "синий"
        elif 270 < h <= 330:  # Синие/фиолетовые оттенки
            if s > 60:
                return "синий"
            return "фиолетовый"
        return "нейтральный"

    def get_color_name_from_hex(self, hex_color):
        """Get color name from HEX color"""
        print(f"Getting color name from HEX: {hex_color}")  # Отладка
        r, g, b = self.hex_to_rgb(hex_color)
        h, s, v = self.rgb_to_hsv(r, g, b)
        print(f"RGB: {r}, {g}, {b}")  # Отладка
        print(f"HSV: {h}, {s}, {v}")  # Отладка
        color_name = self.get_color_name(h, s, v)
        print(f"Color name result: {color_name}")  # Отладка
        return color_name

    def get_color_temperature(self, hex_color):
        """Определяет температуру цвета (тёплый/холодный/нейтральный)"""
        r, g, b = self.hex_to_rgb(hex_color)
        h, s, v = self.rgb_to_hsv(r, g, b)
        
        if s < 20:  # Низкая насыщенность = нейтральный
            return "нейтральный"
            
        # Тёплые цвета: красные, оранжевые, жёлтые, золотистые
        if (0 <= h <= 60) or (330 <= h <= 360):
            return "тёплый"
        # Холодные цвета: синие, голубые, фиолетовые, розовые
        elif 180 <= h <= 300:
            return "холодный"
        return "нейтральный"

    def get_color_brightness(self, hex_color):
        """Определяет яркость цвета (светлый/средний/тёмный)"""
        r, g, b = self.hex_to_rgb(hex_color)
        h, s, v = self.rgb_to_hsv(r, g, b)
        
        if v >= 70:
            return "светлый"
        elif v <= 40:
            return "тёмный"
        return "средний"

    def get_color_type_explanation(self, color_type):
        """Возвращает объяснение цветотипа с учетом контрастности"""
        explanations = {
            "Тёплая весна": "Тёплый и яркий цветотип с золотистым подтоном кожи. Характерны светлая кожа с теплым подтоном, часто с веснушками, глаза голубые, зеленые или янтарные, волосы светлые, рыжие или светло-русые.",
            "Светлая весна": "Светлый и тёплый цветотип с нежным персиковым подтоном. Характерны светлая кожа с теплым подтоном, глаза голубые, зеленые или янтарные, волосы светлые с теплым подтоном.",
            "Яркая весна": "Яркий и тёплый цветотип с чистым золотистым подтоном. Характерны светлая кожа с теплым подтоном, яркие глаза голубые, зеленые или янтарные, волосы светлые с теплым подтоном.",
            "Тёплая осень": "Тёплый и насыщенный цветотип с золотисто-оливковым подтоном. Характерны теплый цвет кожи, глаза зеленого, серо-зеленого, янтарного или темно-коричневого цвета, волосы русые с теплым подтоном, рыжие или каштановые.",
            "Мягкая осень": "Мягкий и тёплый цветотип с приглушённым золотистым подтоном. Характерны теплый цвет кожи, глаза зеленого или серо-зеленого цвета, волосы русые с теплым подтоном.",
            "Глубокая осень": "Глубокий и тёплый цветотип с насыщенным золотистым подтоном. Характерны теплый цвет кожи, глаза темно-коричневые или янтарные, волосы темно-каштановые или темно-коричневые.",
            "Холодное лето": "Холодный и приглушённый цветотип с розово-оливковым подтоном. Характерны светлая кожа с холодным подтоном, глаза светлые голубые, серые или зеленые, волосы от пепельного блонда до темно-русых.",
            "Светлое лето": "Светлый и холодный цветотип с нежным розовым подтоном. Характерны светлая кожа с холодным подтоном, глаза светлые голубые или серые, волосы пепельные или светло-русые.",
            "Мягкое лето": "Мягкий и холодный цветотип с приглушённым розовым подтоном. Характерны светлая кожа с холодным подтоном, глаза серо-голубые или серо-зеленые, волосы пепельные или мышиные.",
            "Холодная зима": "Холодный и чистый цветотип с розово-голубым подтоном. Характерны бледная кожа с холодным подтоном, яркие глаза холодных оттенков (синие, голубые, серые), волосы темных оттенков.",
            "Яркая зима": "Яркий и холодный цветотип с чистым розовым подтоном. Характерны бледная кожа с холодным подтоном, яркие глаза холодных оттенков, волосы темных оттенков с высокой контрастностью.",
            "Глубокая зима": "Глубокий и холодный цветотип с насыщенным розовым подтоном. Характерны бледная кожа с холодным подтоном, глаза темно-карие или темно-синие, волосы очень темных оттенков."
        }
        return explanations.get(color_type, "Описание цветотипа в разработке")

    def get_recommended_colors(self, color_type):
        """Возвращает рекомендуемые цвета для цветотипа"""
        recommendations = self.get_color_recommendations(color_type)
        return {
            "description": recommendations.get("description", ""),
            "recommended": recommendations.get("recommended_colors", []),
            "avoid": recommendations.get("avoid_colors", [])
        }

    def get_preset_analysis(self, color_type):
        print(f"get_preset_analysis: color_type={color_type!r}")
        # Сопоставление alias -> нормализованное название цветотипа
        aliases = {
            'cool_summer': 'Холодное лето',
            'cold_summer': 'Холодное лето',
            'холодное лето': 'Холодное лето',
            'bright_spring': 'Яркая весна',
            'яркая весна': 'Яркая весна',
            'warm_spring': 'Тёплая весна',
            'теплая весна': 'Тёплая весна',
            'тёплая весна': 'Тёплая весна',
            'light_spring': 'Светлая весна',
            'светлая весна': 'Светлая весна',
            'warm_autumn': 'Тёплая осень',
            'теплая осень': 'Тёплая осень',
            'тёплая осень': 'Тёплая осень',
            'soft_autumn': 'Мягкая осень',
            'мягкая осень': 'Мягкая осень',
            'deep_autumn': 'Глубокая осень',
            'глубокая осень': 'Глубокая осень',
            'light_summer': 'Светлое лето',
            'светлое лето': 'Светлое лето',
            'soft_summer': 'Мягкое лето',
            'мягкое лето': 'Мягкое лето',
            'cool_winter': 'Холодная зима',
            'cool winter': 'Холодная зима',
            'coolwinter': 'Холодная зима',
            'холодная зима': 'Холодная зима',
            'bright_winter': 'Яркая зима',
            'яркая зима': 'Яркая зима',
            'deep_winter': 'Глубокая зима',
            'deep winter': 'Глубокая зима',
            'deepwinter': 'Глубокая зима',
            'глубокая зима': 'Глубокая зима',
        }
        color_type_norm = aliases.get(color_type.lower(), None)
        print(f"color_type_norm: {color_type_norm!r}")
        if not color_type_norm:
            return None
        # Описание и рекомендации
        explanation = self.get_color_type_explanation(color_type_norm)
        recommendations = self.get_color_recommendations(color_type_norm)
        # Характеристики (примерные, для шаблона)
        characteristics = {
            "temperature": "холодный" if "лето" in color_type_norm or "зима" in color_type_norm else "тёплый",
            "brightness": "светлый" if "светл" in color_type_norm else ("тёмный" if "глубок" in color_type_norm else "средний"),
            "saturation": "яркий" if "ярк" in color_type_norm else ("мягкий" if "мягк" in color_type_norm else "средний"),
            "contrast": "средний"
        }
        # Цвета для блока "цвета кожи/волос/глаз" — примерные, для шаблона
        preset_colors = {
            'Холодное лето': {
                'skin': {"hex": "#f2e6e0", "name": "бежево-розовый", "temperature": "холодный", "brightness": "светлый"},
                'hair': {"hex": "#b0a8a0", "name": "пепельно-русый", "temperature": "холодный", "brightness": "средний"},
                'eyes': {"hex": "#a3b7c7", "name": "серо-голубой", "temperature": "холодный", "brightness": "светлый"},
            },
            'Яркая весна': {
                'skin': {"hex": "#ffe0b2", "name": "персиковый", "temperature": "тёплый", "brightness": "светлый"},
                'hair': {"hex": "#e2b07a", "name": "золотисто-русый", "temperature": "тёплый", "brightness": "светлый"},
                'eyes': {"hex": "#7fd1b9", "name": "ярко-зелёный", "temperature": "тёплый", "brightness": "яркий"},
            },
            'Тёплая весна': {
                'skin': {"hex": "#f7d7b5", "name": "бежево-медовый", "temperature": "тёплый", "brightness": "светлый"},
                'hair': {"hex": "#c68642", "name": "медовый блонд", "temperature": "тёплый", "brightness": "светлый"},
                'eyes': {"hex": "#bfa76f", "name": "янтарный", "temperature": "тёплый", "brightness": "средний"},
            },
            'Светлая весна': {
                'skin': {"hex": "#fbe8d3", "name": "светло-бежевый", "temperature": "тёплый", "brightness": "светлый"},
                'hair': {"hex": "#f3e2b8", "name": "светло-русый", "temperature": "тёплый", "brightness": "светлый"},
                'eyes': {"hex": "#b2e3e0", "name": "светло-зелёный", "temperature": "тёплый", "brightness": "светлый"},
            },
            # ... можно добавить для других цветотипов ...
        }
        colors = preset_colors.get(color_type_norm, {
            'skin': {"hex": "#e0cfc2", "name": "бежевый", "temperature": "нейтральный", "brightness": "средний"},
            'hair': {"hex": "#b0a8a0", "name": "русый", "temperature": "нейтральный", "brightness": "средний"},
            'eyes': {"hex": "#a3b7c7", "name": "серо-голубой", "temperature": "нейтральный", "brightness": "средний"},
        })
        # Палитры и сочетания (HEX) — как в analyze_image
        # Используем ту же логику, что и в analyze_image для dark_colors_hex, bright_colors_hex, light_colors_hex, color_combinations_svg
        analysis = {
            "image": {
                "format": "PRESET",
                "width": 0,
                "height": 0
            },
            "colors": {
                "skin": colors['skin'],
                "hair": colors['hair'],
                "eyes": colors['eyes']
            },
            "color_type": color_type_norm,
            "explanation": explanation,
            "characteristics": characteristics,
            "recommended_colors": recommendations.get("recommended_colors", []),
            "avoid_colors": recommendations.get("avoid_colors", []),
            "color_combinations": [],
        }
        # Добавляем палитры и сочетания (HEX, SVG)
        # --- скопировано из analyze_image ---
        color_type_normalized = color_type_norm.strip().lower().replace("ё", "е")
        if color_type_normalized in ["светлая весна", "светлая весна.", "svetlaya vesna", "svetlayavesna"]:
            analysis["dark_colors_hex"] = [
                "#6B726C", "#88867D", "#6A564C", "#8B7352", "#8B6352",
                "#368B82", "#2B8A9A", "#2B6C99", "#39548A", "#63518A"
            ]
            analysis["bright_colors_hex"] = [
                "#89C97A", "#F5D06F", "#F7A18A", "#F7A86A", "#F76C6C", "#F76C8C", "#F7B6B6",
                "#5FC16E", "#36B6A2", "#7AC1E4", "#6A8AC7", "#395BAA", "#A18AC7"
            ]
            analysis["light_colors_hex"] = [
                "#EDE0C8", "#F3D1C4", "#F7B8A3", "#F7C6A3", "#FCD494", "#F8E37A", "#C7E3A3",
                "#97D7D3", "#7ED1B8", "#8ED4E8", "#A3D1E8", "#B8A3D1", "#F7B8C8", "#F7A3A3"
            ]
            analysis["color_combinations_svg"] = [
                [
                    {"type": "rect", "color": "#F9D7B5", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#6B418A", "x": 0, "y": 110, "width": 60, "height": 110}
                ],
                [
                    {"type": "rect", "color": "#A3D1E8", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#295A8A", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "ellipse", "color": "#F8E37A", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#F8E37A", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#F8E37A", "x": 32, "y": 140, "width": 28, "height": 28}
                ],
                [
                    {"type": "rect", "color": "#F7B8C8", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#6B726C", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#BDB89A", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#F6E3CF", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#8B7352", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#F9D77A", "x": 10, "y": 0, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#F7A3A3", "x": 0, "y": 0, "width": 60, "height": 220},
                    {"type": "ellipse", "color": "#F8E37A", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#F8E37A", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#E6D3B3", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#6BCB4A", "x": 0, "y": 0, "width": 20, "height": 110},
                    {"type": "rect", "color": "#F8E37A", "x": 20, "y": 0, "width": 20, "height": 110},
                    {"type": "rect", "color": "#6BCB4A", "x": 40, "y": 0, "width": 20, "height": 110},
                    {"type": "rect", "color": "#2B8A7A", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#295A8A", "x": 15, "y": 108, "width": 30, "height": 4}
                ]
            ]
        if color_type_normalized in ["тёплая весна", "теплая весна", "тёплая весна.", "теплая весна.", "warm spring", "warmspring"]:
            analysis["dark_colors_hex"] = [
                "#5F574E", "#7A5C3A", "#4A362D", "#8B4C3B", "#875040",
                "#21753B", "#1B7A5C", "#1B9797", "#14416A", "#6B418A"
            ]
            analysis["bright_colors_hex"] = [
                "#E8BC4A", "#EBC77A", "#E3B184", "#B7C44A", "#3AAA49", "#6BCB4A", "#44C97A",
                "#F77C5A", "#E84A4A", "#1BAA8A", "#24A7A7", "#5A7CE8", "#A74AC9"
            ]
            analysis["light_colors_hex"] = [
                "#F6E3CF", "#F9D7B5", "#E7D89B", "#F6C1A1", "#F6DF9B", "#CFE07A", "#7ED97A",
                "#C7C9BC", "#C9B18C", "#C99BD1", "#A1B8E7", "#F67C7A", "#F6B1A1", "#44C9A7"
            ]
            # Добавляю SVG-комбинации для тёплой весны (warm_spring)
            analysis["color_combinations_svg"] = [
                [
                    {"type": "rect", "color": "#E8BC4A", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#7A5C3A", "x": 0, "y": 110, "width": 60, "height": 110}
                ],
                [
                    {"type": "rect", "color": "#F6C1A1", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "ellipse", "color": "#F77C5A", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#F77C5A", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#7A5C3A", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#E84A4A", "x": 18, "y": 90, "width": 28, "height": 28}
                ],
                [
                    {"type": "rect", "color": "#A1B8E7", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#14416A", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#1B7AE7", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#CFE07A", "x": 0, "y": 0, "width": 60, "height": 100},
                    {"type": "rect", "color": "#5F574E", "x": 0, "y": 100, "width": 60, "height": 120},
                    {"type": "rect", "color": "#E8BC4A", "x": 0, "y": 98, "width": 60, "height": 8}
                ],
                [
                    {"type": "rect", "color": "#44C9A7", "x": 0, "y": 0, "width": 60, "height": 200},
                    {"type": "ellipse", "color": "#F9D7B5", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#F9D7B5", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#7E7B6A", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#E84A4A", "x": 0, "y": 0, "width": 20, "height": 110},
                    {"type": "rect", "color": "#F6E3CF", "x": 20, "y": 0, "width": 20, "height": 110},
                    {"type": "rect", "color": "#E84A4A", "x": 40, "y": 0, "width": 20, "height": 110},
                    {"type": "rect", "color": "#4A362D", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#E3B184", "x": 32, "y": 140, "width": 28, "height": 28}
                ]
            ]
        if color_type_normalized in ["яркая весна", "яркая весна.", "bright spring", "brightspring"]:
            analysis["dark_colors_hex"] = [
                "#636968", "#72665C", "#3E4343", "#232323", "#1B4062", "#B1463B",
                "#25462C", "#317338", "#176973", "#3B326E", "#8A2B5A", "#D13C6B"
            ]
            analysis["bright_colors_hex"] = [
                "#E94382", "#FF7CB5", "#E95CA0", "#D94C7A", "#D94C5C", "#F05C5C", "#FF7C6C", "#FF9C9C",
                "#1878C2", "#6C4CA0", "#1C8C8C", "#4CA03C", "#A0C24C", "#F0B24C", "#FFD47C"
            ]
            analysis["light_colors_hex"] = [
                "#E9DFC6", "#E7E3D5", "#C9DC7C", "#A7E3DD", "#B3E6F2", "#C2C6E7", "#F9CFC6",
                "#EAE6B7", "#FFD07C", "#F7A9C2", "#F78BCB", "#4CD7DE", "#A07CD7", "#F7A9B2"
            ]
            analysis["color_combinations_svg"] = [
                [
                    {"type": "rect", "color": "#D94C5C", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#232623", "x": 0, "y": 110, "width": 60, "height": 110}
                ],
                [
                    {"type": "rect", "color": "#F9CFC6", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "ellipse", "color": "#1C8C8C", "cx": 30, "cy": 30, "rx": 18, "ry": 28, "stroke": "#1C8C8C", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#1B4062", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#C2B8B5", "x": 18, "y": 90, "width": 28, "height": 28}
                ],
                [
                    {"type": "rect", "color": "#A0C24C", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#25462C", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#72665C", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#FFD47C", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#72665C", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#3E4343", "x": 0, "y": 108, "width": 60, "height": 8},
                    {"type": "rect", "color": "#1C8C8C", "x": 16, "y": 0, "width": 28, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#E95CA0", "x": 0, "y": 0, "width": 60, "height": 220},
                    {"type": "ellipse", "color": "#C2C6E7", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#C2C6E7", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#A07CD7", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#1878C2", "x": 0, "y": 0, "width": 18, "height": 110},
                    {"type": "rect", "color": "#A7E3DD", "x": 18, "y": 0, "width": 24, "height": 110},
                    {"type": "rect", "color": "#1878C2", "x": 42, "y": 0, "width": 18, "height": 110},
                    {"type": "rect", "color": "#6C4CA0", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#3E4343", "x": 15, "y": 108, "width": 30, "height": 4}
                ]
            ]
        if color_type_normalized in ["холодное лето", "холодное лето.", "cool summer", "coolsummer"]:
            analysis["dark_colors_hex"] = [
                "#635C56", "#72666C", "#564E52", "#6C5A5C", "#4C3A3C", "#43484C", "#23545C",
                "#732C3C", "#8A2B5A", "#17696C", "#184C3C", "#23426C", "#4C4A6C", "#32324C"
            ]
            analysis["bright_colors_hex"] = [
                "#b0405a", "#e07a98", "#e05a6d", "#f48a9a", "#8a345a", "#b05a8a", "#5a4a7a",
                "#24918c", "#29897a", "#17696c", "#3a6f7a", "#3ac1cc", "#5a8aac", "#7a7aac"
            ]
            analysis["light_colors_hex"] = [
                "#e5e4db", "#bfc2b4", "#ece6b2", "#c5bcbc", "#a2b1b6", "#a3bcbc", "#ffc7da",
                "#6ec8b7", "#5fd1c7", "#5fc7e1", "#3fc1cc", "#8ac6e8", "#a3aed8", "#7a7aac"
            ]
            analysis["color_combinations_svg"] = [
                [
                    {"type": "rect", "color": "#bfc2b4", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#635C56", "x": 0, "y": 110, "width": 60, "height": 110}
                ],
                [
                    {"type": "rect", "color": "#e5e4db", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "ellipse", "color": "#3ac1cc", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#3ac1cc", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#4C3A3C", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#e07a98", "x": 32, "y": 80, "width": 28, "height": 28}
                ],
                [
                    {"type": "rect", "color": "#8ac6e8", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#23426C", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#6C5A5C", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#ece6b2", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#564E52", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#b05a8a", "x": 0, "y": 108, "width": 60, "height": 8},
                    {"type": "rect", "color": "#3ac1cc", "x": 16, "y": 0, "width": 28, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#f48a9a", "x": 0, "y": 0, "width": 60, "height": 220},
                    {"type": "ellipse", "color": "#a3aed8", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3aed8", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#635C8C", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#24918c", "x": 0, "y": 0, "width": 18, "height": 110},
                    {"type": "rect", "color": "#e5e4db", "x": 18, "y": 0, "width": 24, "height": 110},
                    {"type": "rect", "color": "#24918c", "x": 42, "y": 0, "width": 18, "height": 110},
                    {"type": "rect", "color": "#72666C", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#564E52", "x": 15, "y": 108, "width": 30, "height": 4}
                ]
            ]
        if color_type_normalized in ["светлое лето", "светлое лето.", "light summer", "lightsummer"]:
            analysis["dark_colors_hex"] = [
                "#88837d", "#5b6c75", "#5a3d45", "#b04d6d", "#5e5387",
                "#1e6a5a", "#23837d", "#2a7c8c", "#23628c", "#2b4577"
            ]
            analysis["bright_colors_hex"] = [
                "#f26c76", "#f24d6d", "#e94c6d", "#e94c7a", "#f7a1c2", "#d97ba7", "#6e5a97",
                "#2ed1a7", "#2eb7a7", "#2eb7c2", "#2ea7c2", "#4ca7e7", "#4c7ae7", "#6e87c2"
            ]
            analysis["light_colors_hex"] = [
                "#f7b8c8", "#f7a3b2", "#f7c6b2", "#f7e1b2", "#e7e1d6", "#e7e7e1", "#b2a3c2",
                "#a3d1e7", "#a3e7e7", "#a3e7c2", "#c2e7e7", "#c2d1e7", "#b2a3a3", "#a37a7a"
            ]
            analysis["color_combinations_svg"] = [
                [
                {"type": "rect", "color": "#f7b8c8", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#a37a7a", "x": 0, "y": 110, "width": 60, "height": 110}
            ],
            [
                {"type": "rect", "color": "#f7e1b2", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "ellipse", "color": "#2ea7c2", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#2ea7c2", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#5a3d45", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#23628c", "x": 32, "y": 80, "width": 28, "height": 28}
            ],
            [
                {"type": "rect", "color": "#a3d1e7", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#5e5387", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#1e6a5a", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#2eb7c2", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#5b6c75", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#23628c", "x": 0, "y": 108, "width": 60, "height": 8},
                {"type": "rect", "color": "#a3b3d6", "x": 16, "y": 0, "width": 28, "height": 18}
            ],
            [
                {"type": "rect", "color": "#f7a3b2", "x": 0, "y": 0, "width": 60, "height": 220},
                {"type": "ellipse", "color": "#a3e7e7", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3e7e7", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#b2a3c2", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#b04d6d", "x": 0, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#f7e1b2", "x": 18, "y": 0, "width": 24, "height": 110},
                {"type": "rect", "color": "#b04d6d", "x": 42, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#2b4577", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#5e5387", "x": 15, "y": 108, "width": 30, "height": 4}
            ]
        ]
        if color_type_normalized in ["мягкое лето", "мягкое лето.", "soft summer", "softsummer"]:
            analysis["dark_colors_hex"] = [
                "#543543", "#6a3d45", "#a13d4d", "#7a3d4d", "#444143", "#543a3d",
                "#6a5a6a", "#3a4152", "#2a4d5a", "#2a5a5a"
            ]
            analysis["bright_colors_hex"] = [
                "#a15a6a", "#e76a8a", "#d94c6d", "#e76a7a", "#f7a1a2", "#b97a7a", "#7a7a97",
                "#7a9ab7", "#5a8a97", "#7ab7b7", "#5ab7a7", "#7ab797", "#7ab797", "#97b797"
            ]
            analysis["light_colors_hex"] = [
                "#e7b8c8", "#f7a3b2", "#f7c6b2", "#e7e1b2", "#d7d1c6", "#d7d7d1", "#b2a3b2",
                "#a3b1c7", "#a3c7c7", "#a3c7b2", "#c2c7c7", "#c2c7d7", "#b2a3a3", "#a3a7a7"
            ]
            analysis["color_combinations_svg"] = [
                [
                {"type": "rect", "color": "#a3b1c7", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#a15a6a", "x": 0, "y": 110, "width": 60, "height": 110}
            ],
            [
                {"type": "rect", "color": "#e7e1b2", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "ellipse", "color": "#5a8a97", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#5a8a97", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#543a3d", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#a13d4d", "x": 32, "y": 80, "width": 28, "height": 28}
            ],
            [
                {"type": "rect", "color": "#7a9ab7", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#3a4152", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#2a5a5a", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#7ab7b7", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#6a5a6a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#2a4d5a", "x": 0, "y": 108, "width": 60, "height": 8},
                {"type": "rect", "color": "#b2a3b2", "x": 16, "y": 0, "width": 28, "height": 18}
            ],
            [
                {"type": "rect", "color": "#f7a3b2", "x": 0, "y": 0, "width": 60, "height": 220},
                {"type": "ellipse", "color": "#a3c7c7", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3c7c7", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#b2a3b2", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#a13d4d", "x": 0, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#e7e1b2", "x": 18, "y": 0, "width": 24, "height": 110},
                {"type": "rect", "color": "#a13d4d", "x": 42, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#2a5a5a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#543a3d", "x": 15, "y": 108, "width": 30, "height": 4}
            ]
        ]
        if color_type_normalized in ["мягкая осень", "мягкая осень.", "soft autumn", "softautumn"]:
            analysis["dark_colors_hex"] = [
                "#6b6a62", "#3a4343", "#453634", "#5a3d3a", "#5a3d3a",
                "#3a4a3a", "#7a3d3a", "#8a2b3a", "#2a3a5a", "#1a3a3a"
            ]
            analysis["bright_colors_hex"] = [
                "#edd09c", "#e2b07a", "#a36a5a", "#a35a5a", "#b04d6d", "#e76a6a", "#f7a1a2",
                "#b7b78a", "#4a8a6a", "#2a8a7a", "#2a8a8a", "#2a6a8a", "#4a6a8a", "#6a7a8a"
            ]
            analysis["light_colors_hex"] = [
                "#e7e7e1", "#d7d7c6", "#edd09c", "#e2b07a", "#b7b78a", "#a3b78a", "#a3d1c2",
                "#a3d1d1", "#a3c7c7", "#a3c7b2", "#c2c7c7", "#c2c7d7", "#f7b8c8", "#f7a3b2"
            ]
            analysis["color_combinations_svg"] = [
                [
                {"type": "rect", "color": "#e7e7e1", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#8a2b3a", "x": 0, "y": 110, "width": 60, "height": 110}
            ],
            [
                {"type": "rect", "color": "#a3d1c2", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "ellipse", "color": "#b7b78a", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#b7b78a", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#1a3a3a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#edd09c", "x": 32, "y": 80, "width": 28, "height": 28}
            ],
            [
                {"type": "rect", "color": "#a3b78a", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#2a3a5a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#4a8a6a", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#edd09c", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#3a4343", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#2a8a7a", "x": 0, "y": 108, "width": 60, "height": 8},
                {"type": "rect", "color": "#a3c7c7", "x": 16, "y": 0, "width": 28, "height": 18}
            ],
            [
                {"type": "rect", "color": "#f7a3b2", "x": 0, "y": 0, "width": 60, "height": 220},
                {"type": "ellipse", "color": "#a3d1d1", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3d1d1", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#b7b78a", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#b04d6d", "x": 0, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#edd09c", "x": 18, "y": 0, "width": 24, "height": 110},
                {"type": "rect", "color": "#b04d6d", "x": 42, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#2a3a5a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#5a3d3a", "x": 15, "y": 108, "width": 30, "height": 4}
            ]
        ]
        if color_type_normalized in ["тёплая осень", "теплая осень", "тёплая осень.", "теплая осень.", "warm autumn", "warmautumn"]:
            analysis["dark_colors_hex"] = [
                "#66514f", "#4a4a44", "#5a463d", "#7a5a3a", "#7a3d3a",
                "#3a3a2a", "#1a3a2a", "#1a4a4a", "#1a4a6a", "#3a3a5a"
            ]
            analysis["bright_colors_hex"] = [
                "#f7a15a", "#e77a4a", "#c74a3a", "#e77a7a", "#e76a8a", "#f7a1a2", "#b7b74a",
                "#4a8a6a", "#2a8a7a", "#2a8a8a", "#2a6a8a", "#4a6a8a", "#6a7a8a", "#3a7a4a"
            ]
            analysis["light_colors_hex"] = [
                "#f7e1c2", "#f7c6b2", "#f7b8a3", "#e7c6a3", "#e7e1a3", "#c7d1a3", "#a3d1a3",
                "#a3d1c2", "#a3d1d1", "#a3c7c7", "#c2c7c7", "#c2c7d7", "#f7b8c8", "#f7a3b2"
            ]
            analysis["color_combinations_svg"] = [
                [
                {"type": "rect", "color": "#1a8a8a", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#5a463d", "x": 0, "y": 110, "width": 60, "height": 110}
            ],
            [
                {"type": "rect", "color": "#f7c6b2", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "ellipse", "color": "#4a6a8a", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#4a6a8a", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#3a3a2a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#e77a4a", "x": 32, "y": 80, "width": 28, "height": 28}
            ],
            [
                {"type": "rect", "color": "#a3d1a3", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#1a4a6a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#3a7a4a", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#f7a15a", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#66514f", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#2a8a7a", "x": 0, "y": 108, "width": 60, "height": 8},
                {"type": "rect", "color": "#a3d1c2", "x": 16, "y": 0, "width": 28, "height": 18}
            ],
            [
                {"type": "rect", "color": "#f7b8c8", "x": 0, "y": 0, "width": 60, "height": 220},
                {"type": "ellipse", "color": "#a3d1d1", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3d1d1", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#b7b74a", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#b04d6d", "x": 0, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#f7e1c2", "x": 18, "y": 0, "width": 24, "height": 110},
                {"type": "rect", "color": "#b04d6d", "x": 42, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#1a4a6a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#5a463d", "x": 15, "y": 108, "width": 30, "height": 4}
            ]
        ]
        if color_type_normalized in ["глубокая осень", "глубокая осень.", "deep autumn", "deepautumn"]:
            analysis["dark_colors_hex"] = [
                "#1d3c37", "#18413f", "#2c322a", "#3a2931", "#635253", "#5a513b", "#232322",
                "#7a2b38", "#5a2328", "#7a3d3a", "#3a2320", "#2a3a4a", "#23324a", "#1d3c37"
            ]
            analysis["bright_colors_hex"] = [
                "#f48c8c", "#e97a6d", "#d94c5c", "#e94c6d", "#b13a5a", "#a13d4d", "#b7b74a",
                "#d7b97a", "#a3b76a", "#a39b5a", "#b77a5a", "#b75a7a", "#b76a97", "#c97a9a"
            ]
            analysis["light_colors_hex"] = [
                "#e7e1d6", "#f7d1b2", "#f7e1b2", "#a3d1e7", "#e7b8c8", "#e7a3b2", "#f7b8a3",
                "#f7c6a3", "#e7e1a3", "#c7d1a3", "#a3d1a3", "#a3d1c2", "#a3d1d1", "#a3c7c7"
            ]
            analysis["color_combinations_svg"] = [
                [
                {"type": "rect", "color": "#18413f", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "ellipse", "color": "#d7b97a", "cx": 20, "cy": 150, "rx": 28, "ry": 18, "stroke": "#d7b97a", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#3a2931", "x": 0, "y": 110, "width": 60, "height": 110}
            ],
            [
                {"type": "rect", "color": "#b76a97", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "ellipse", "color": "#e7a3b2", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#e7a3b2", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#5a2328", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#7a2b38", "x": 32, "y": 80, "width": 28, "height": 28}
            ],
            [
                {"type": "rect", "color": "#b77a5a", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#2c322a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#3a2320", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#f7d1b2", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#635253", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#7a2b38", "x": 0, "y": 108, "width": 60, "height": 8},
                {"type": "rect", "color": "#a3d1a3", "x": 16, "y": 0, "width": 28, "height": 18}
            ],
            [
                {"type": "rect", "color": "#e7a3b2", "x": 0, "y": 0, "width": 60, "height": 220},
                {"type": "ellipse", "color": "#a3d1d1", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#a3d1d1", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#b7b74a", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#b13a5a", "x": 0, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#e7e1d6", "x": 18, "y": 0, "width": 24, "height": 110},
                {"type": "rect", "color": "#b13a5a", "x": 42, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#2c322a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#5a2328", "x": 15, "y": 108, "width": 30, "height": 4}
            ]
        ]
        if color_type_normalized in ["глубокая зима", "глубокая зима.", "deep winter", "deepwinter"]:
            analysis["dark_colors_hex"] = [
                "#000000", "#44494a", "#78736e", "#5a2330", "#322523", "#1a3a36", "#176153",
                "#176a5a", "#1a4a4a", "#1a4a6a", "#23324a", "#1d3c37", "#5a2328", "#3a2320"
            ]
            analysis["bright_colors_hex"] = [
                "#f7e37a", "#f7d07a", "#a3d76a", "#e76a97", "#e76a8a", "#b13a5a", "#b76a97",
                "#7a7ae7", "#5a8ae7", "#1a7aa7", "#1a7a97", "#1a7a7a", "#1aa7a7", "#1aa77a"
            ]
            analysis["light_colors_hex"] = [
                "#ffffff", "#d7dbdb", "#e7e1d6", "#e7e7e1", "#f7e1b2", "#b2e7e7", "#a3d1e7",
                "#b2c7e7", "#b2a3d1", "#e7b8c8", "#e7a3b2", "#f7b8a3", "#f7c6a3", "#e7e1a3"
            ]
            analysis["color_combinations_svg"] = [
                [
                {"type": "rect", "color": "#e76a8a", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#4a2a4a", "x": 0, "y": 110, "width": 60, "height": 110}
            ],
            [
                {"type": "rect", "color": "#b2a3d1", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "ellipse", "color": "#b2e7e7", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#b2e7e7", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#322523", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#e76a97", "x": 32, "y": 80, "width": 28, "height": 28}
            ],
            [
                {"type": "rect", "color": "#f7e37a", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#1a7a97", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#000000", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#ffffff", "x": 0, "y": 0, "width": 60, "height": 110},
                {"type": "rect", "color": "#1a7aa7", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#5a8ae7", "x": 0, "y": 108, "width": 60, "height": 8},
                {"type": "rect", "color": "#1a7a97", "x": 16, "y": 0, "width": 28, "height": 18}
            ],
            [
                {"type": "rect", "color": "#b13a5a", "x": 0, "y": 0, "width": 60, "height": 220},
                {"type": "ellipse", "color": "#b2a3d1", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#b2a3d1", "strokeWidth": 3, "fill": "none"},
                {"type": "rect", "color": "#1a7aa7", "x": 10, "y": 200, "width": 40, "height": 18}
            ],
            [
                {"type": "rect", "color": "#e76a97", "x": 0, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#d7dbdb", "x": 18, "y": 0, "width": 24, "height": 110},
                {"type": "rect", "color": "#e76a97", "x": 42, "y": 0, "width": 18, "height": 110},
                {"type": "rect", "color": "#1a4a6a", "x": 0, "y": 110, "width": 60, "height": 110},
                {"type": "rect", "color": "#44494a", "x": 15, "y": 108, "width": 30, "height": 4}
            ]
        ]
        if color_type_normalized in ["холодная зима", "холодная зима.", "cool winter", "coolwinter"]:
            analysis["dark_colors_hex"] = [
                "#1A1A1A", "#2C2C2C", "#3C3C3C", "#4C4C4C", "#5C5C5C",
                "#1B4062", "#25462C", "#317338", "#176973", "#3B326E", "#8A2B5A", "#D13C6B"
            ]
            analysis["bright_colors_hex"] = [
                "#E94382", "#FF7CB5", "#E95CA0", "#D94C7A", "#D94C5C", "#F05C5C", "#FF7C6C", "#FF9C9C",
                "#1878C2", "#6C4CA0", "#1C8C8C", "#4CA03C", "#A0C24C", "#F0B24C", "#FFD47C"
            ]
            analysis["light_colors_hex"] = [
                "#FFFFFF", "#F5F5F5", "#E5E5E5", "#D5D5D5", "#C5C5C5",
                "#B3E6F2", "#C2C6E7", "#F9CFC6", "#EAE6B7", "#FFD07C", "#F7A9C2", "#F78BCB", "#4CD7DE", "#A07CD7"
            ]
            analysis["color_combinations_svg"] = [
                [
                    {"type": "rect", "color": "#FFFFFF", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#1A1A1A", "x": 0, "y": 110, "width": 60, "height": 110}
                ],
                [
                    {"type": "rect", "color": "#F5F5F5", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "ellipse", "color": "#1878C2", "cx": 30, "cy": 35, "rx": 18, "ry": 28, "stroke": "#1878C2", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#1B4062", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#E94382", "x": 32, "y": 90, "width": 28, "height": 28}
                ],
                [
                    {"type": "rect", "color": "#B3E6F2", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#176973", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#1C8C8C", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#E5E5E5", "x": 0, "y": 0, "width": 60, "height": 100},
                    {"type": "rect", "color": "#2C2C2C", "x": 0, "y": 100, "width": 60, "height": 120},
                    {"type": "rect", "color": "#D94C5C", "x": 0, "y": 98, "width": 60, "height": 8}
                ],
                [
                    {"type": "rect", "color": "#C2C6E7", "x": 0, "y": 0, "width": 60, "height": 200},
                    {"type": "ellipse", "color": "#FFFFFF", "cx": 30, "cy": 80, "rx": 18, "ry": 60, "stroke": "#FFFFFF", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#3B326E", "x": 10, "y": 200, "width": 40, "height": 18}
                ],
                [
                    {"type": "rect", "color": "#D94C5C", "x": 0, "y": 0, "width": 20, "height": 110},
                    {"type": "rect", "color": "#FFFFFF", "x": 20, "y": 0, "width": 20, "height": 110},
                    {"type": "rect", "color": "#D94C5C", "x": 40, "y": 0, "width": 20, "height": 110},
                    {"type": "rect", "color": "#1A1A1A", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#1878C2", "x": 32, "y": 140, "width": 28, "height": 28}
                ]
            ]
        if color_type_normalized in ["яркая зима", "яркая зима.", "bright winter", "brightwinter"]:
            analysis["dark_colors_hex"] = [
                "#111111", "#444949", "#6B6A66", "#18514D", "#187144", "#1B7C8C", "#176A8C"
            ]
            analysis["bright_colors_hex"] = [
                "#F7E37A", "#FFD47C", "#B7DC4A", "#8CB74A", "#1CB75A", "#3AD7A7", "#1CA7A7",
                "#1C8C8C", "#1C5AA7", "#3A6FA7", "#4C7AE7", "#6A4CA7", "#A74AC9", "#F77C7A",
                "#F05C5C", "#FF7CB5", "#E94382", "#D94C7A", "#E95CA0"
            ]
            analysis["light_colors_hex"] = [
                "#FFFFFF", "#D7DBDB", "#F7E1B2", "#F7B8C8", "#B2E7E7", "#E7E1D6", "#F7C6A3",
                "#E7C6A3", "#E7A3B2", "#E7B8C8", "#E7E7E1", "#B2A3D1"
            ]
            analysis["color_combinations_svg"] = [
                [
                    {"type": "rect", "color": "#FFD47C", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#23191A", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "ellipse", "color": "#F7E1B2", "cx": 20, "cy": 110, "rx": 28, "ry": 18, "stroke": "#F7E1B2", "strokeWidth": 3, "fill": "none"}
                ],
                [
                    {"type": "rect", "color": "#4CC7F7", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#1B2652", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "ellipse", "color": "#A74AC9", "cx": 30, "cy": 30, "rx": 18, "ry": 18, "stroke": "#A74AC9", "strokeWidth": 3, "fill": "none"},
                    {"type": "rect", "color": "#A74AC9", "x": 32, "y": 90, "width": 28, "height": 28}
                ],
                [
                    {"type": "rect", "color": "#1CB75A", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#444949", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "ellipse", "color": "#B7DC4A", "cx": 30, "cy": 60, "rx": 18, "ry": 18, "stroke": "#B7DC4A", "strokeWidth": 3, "fill": "none"}
                ],
                [
                    {"type": "rect", "color": "#D94C5C", "x": 0, "y": 0, "width": 60, "height": 110},
                    {"type": "rect", "color": "#111111", "x": 0, "y": 110, "width": 60, "height": 110},
                    {"type": "rect", "color": "#FFFFFF", "x": 0, "y": 100, "width": 60, "height": 10}
                ],
                [
                    {"type": "rect", "color": "#8A2B5A", "x": 0, "y": 0, "width": 60, "height": 220},
                    {"type": "ellipse", "color": "#FFFFFF", "cx": 30, "cy": 110, "rx": 18, "ry": 60, "stroke": "#FFFFFF", "strokeWidth": 3, "fill": "none"}
                ],
                [
                    {"type": "rect", "color": "#F7A9C2", "x": 0, "y": 0, "width": 30, "height": 110},
                    {"type": "rect", "color": "#D94C7A", "x": 30, "y": 0, "width": 30, "height": 110},
                    {"type": "rect", "color": "#23234A", "x": 0, "y": 110, "width": 60, "height": 110}
                ]
            ]
        return analysis

if __name__ == "__main__":
    analyzer = ColorAnalyzer()
    # Замените путь на путь к вашему изображению, если нужно
    result = analyzer.analyze_image("test_face.jpg")
    print(json.dumps(result, ensure_ascii=False, indent=2)) 
    print(json.dumps(result, ensure_ascii=False, indent=2)) 