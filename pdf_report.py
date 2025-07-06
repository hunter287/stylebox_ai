import os
from reportlab.lib.pagesizes import portrait
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from PyPDF2 import PdfReader, PdfWriter

PDF_WIDTH = 1080
PDF_HEIGHT = 1920

USER_PHOTO_DIR = 'static/user_photos/'
REFERENCE_PHOTO_DIR = 'static/reference_photos/'
REPORTS_DIR = 'static/reports/'

pdfmetrics.registerFont(TTFont('Roboto', 'static/Roboto-Regular.ttf'))
pdfmetrics.registerFont(TTFont('OpenSans-Light', 'static/OpenSans-Light.ttf'))


def crop_to_circle(image_path, size=400):
    """Обрезает изображение до квадрата по центру, затем в круг и уменьшает до нужного размера."""
    img = Image.open(image_path).convert('RGBA')
    # Обрезаем до квадрата по центру
    w, h = img.size
    min_side = min(w, h)
    left = (w - min_side) // 2
    top = (h - min_side) // 2
    right = left + min_side
    bottom = top + min_side
    img = img.crop((left, top, right, bottom))
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    img.putalpha(mask)
    return img


def draw_palette_auto_wrap(c, colors, x, y, radius=36, gap=28, max_width=None, cols=9):
    """Рисует палитру цветов с автоматическим переносом по ширине. Возвращает высоту блока."""
    diameter = radius * 2
    step = diameter + gap
    if max_width is not None:
        cols = min(cols, max(1, (max_width + gap) // step))
    rows = (len(colors) + cols - 1) // cols
    for idx, color in enumerate(colors):
        row = idx // cols
        col = idx % cols
        cx = x + col * step
        cy = y - row * step  # ВНИЗ по y
        c.setFillColor(color)
        # Если цвет белый — рисуем серую обводку
        if hasattr(color, 'hexval') and color.hexval().lower() in ['#fff', '#ffffff']:
            c.setStrokeColorRGB(0.7, 0.7, 0.7)
            c.circle(cx, cy, radius, fill=1, stroke=1)
        else:
            c.setStrokeColorRGB(1, 1, 1)
            c.circle(cx, cy, radius, fill=1, stroke=0)
    return rows * step


def safe_hex_color(c):
    try:
        if isinstance(c, str) and c.startswith('#') and len(c) == 7:
            return HexColor(c)
        else:
            print('Невалидный цвет:', repr(c))
    except Exception as e:
        print('Ошибка в safe_hex_color:', repr(c), e)
    return HexColor('#FFFFFF')  # дефолт


def generate_pdf_report(
    analysis: dict,
    user_photo_path: str,
    reference_photos: list = None,
    output_path: str = None
):
    print('PDF GENERATE CALLED')
    temp_files = []  # Список для отслеживания временных файлов
    try:
        if not output_path:
            output_path = os.path.join(REPORTS_DIR, 'report.pdf')
        
        # Создаем директорию для отчетов, если она не существует
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        c = canvas.Canvas(output_path, pagesize=(PDF_WIDTH, PDF_HEIGHT))

        # --- Первая страница ---
        # Заголовок
        c.setFillColorRGB(1, 0.8, 0.6)
        c.rect(0, PDF_HEIGHT-200, PDF_WIDTH, 200, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
        c.setFont('Roboto', 60)
        c.drawString(80, PDF_HEIGHT-140, 'Палитра оттенков в одежде')

        # Фото пользователя (обрезка до круга 456x456)
        circ_img = crop_to_circle(user_photo_path, size=456)
        circ_img_path = user_photo_path + '_circle.png'
        circ_img.save(circ_img_path)
        temp_files.append(circ_img_path)  # Добавляем в список временных файлов
        
        # Выровнять фото по левому краю с отступом 120
        photo_x = 120
        photo_y = PDF_HEIGHT-550
        c.drawImage(circ_img_path, photo_x, photo_y, width=280, height=280, mask='auto')
        os.remove(circ_img_path)

        print('PDF analysis:', analysis)  # Логирование для отладки
        print('main_palette_hex:', analysis.get('main_palette_hex'))
        print('additional_palette_hex:', analysis.get('additional_palette_hex'))
        print('dark_colors_hex:', analysis.get('dark_colors_hex'))
        print('bright_colors_hex:', analysis.get('bright_colors_hex'))
        # --- Описание цветотипа (под фото) ---
        c.setFont('OpenSans-Light', 24)
        c.setFillColorRGB(0, 0, 0)
        text = analysis.get('explanation', '')
        if not isinstance(text, str):
            if isinstance(text, list):
                text = ' '.join(map(str, text))
            else:
                text = str(text)
        # Многострочный вывод с переносом по ширине страницы
        max_width = PDF_WIDTH - 2 * 120  # отступы по краям
        lines = []
        for paragraph in text.split('\n'):
            words = paragraph.split()
            line = ''
            for word in words:
                test_line = (line + ' ' + word).strip()
                if stringWidth(test_line, 'OpenSans-Light', 24) > max_width and line:
                    lines.append(line)
                    line = word
                else:
                    line = test_line
            if line:
                lines.append(line)
        # Координаты для текста сразу под фото
        text_y = photo_y - 50  # уменьшенный отступ (50px) под фото
        for i, line in enumerate(lines):
            c.drawString(120, text_y - i * 30, line)  # 30 — высота строки с небольшим пробелом

        # --- Тёмные цвета ---
        dark_palette = [safe_hex_color(c) for c in analysis.get('dark_colors_hex', []) if c and c != '#fff' and c != '#ffffff']
        c.setFont('Roboto-Bold' if 'Roboto-Bold' in pdfmetrics.getRegisteredFontNames() else 'Roboto', 36)
        y_dark_label = text_y - len(lines) * 30 - 60
        c.drawString(120, y_dark_label, 'Тёмные цвета:')
        y_dark_palette = y_dark_label-32-36
        dark_block_height = draw_palette_auto_wrap(c, dark_palette, 150, y_dark_palette, radius=36, gap=28, cols=9)

        # --- Яркие цвета ---
        bright_palette = [safe_hex_color(c) for c in analysis.get('bright_colors_hex', []) if c and c != '#fff' and c != '#ffffff']
        c.setFont('Roboto-Bold' if 'Roboto-Bold' in pdfmetrics.getRegisteredFontNames() else 'Roboto', 36)
        y_bright_label = y_dark_palette - dark_block_height - 60
        c.drawString(120, y_bright_label, 'Яркие цвета:')
        y_bright_palette = y_bright_label-32-36
        bright_block_height = draw_palette_auto_wrap(c, bright_palette, 150, y_bright_palette, radius=36, gap=28, cols=9)

        # --- Светлые цвета ---
        light_palette_raw = analysis.get('light_colors_hex', [])
        light_palette = [c for c in light_palette_raw if c and c.lower() not in ['#fff', '#ffffff', '#ffffff']]
        print('PDF light_palette filtered:', list(enumerate(light_palette)))
        light_palette = [safe_hex_color(c) for c in light_palette]
        c.setFont('Roboto-Bold' if 'Roboto-Bold' in pdfmetrics.getRegisteredFontNames() else 'Roboto', 36)
        y_light_label = y_bright_palette - bright_block_height - 60
        c.drawString(120, y_light_label, 'Светлые цвета:')
        y_light_palette = y_light_label-32-36
        light_block_height = draw_palette_auto_wrap(c, light_palette, 150, y_light_palette, radius=36, gap=28, cols=9)

        # --- Блок информации о коже, глазах и волосах справа от фото (референс-стиль) ---
        color_info = analysis.get('colors', {})
        info_labels = [('Кожа', 'skin'), ('Волосы', 'hair'), ('Глаза', 'eyes')]
        rect_w, rect_h, rect_r = 80, 48, 12  # ширина, высота, радиус скругления
        info_x = photo_x + 280 + 60  # справа от фото + отступ
        info_y = photo_y + 180  # чуть ниже верхнего края фото
        info_gap_y = 64  # вертикальный отступ между блоками
        for i, (label, key) in enumerate(info_labels):
            y = info_y - i * info_gap_y
            color_data = color_info.get(key, {})
            hex_color = color_data.get('hex', '#cccccc')
            name = color_data.get('name', '')
            # Цветной прямоугольник с радиусом
            c.setFillColor(safe_hex_color(hex_color))
            c.setStrokeColorRGB(1, 1, 1)
            c.roundRect(info_x, y, rect_w, rect_h, rect_r, fill=1, stroke=0)
            # Текст справа от прямоугольника
            c.setFont('Roboto-Bold' if 'Roboto-Bold' in pdfmetrics.getRegisteredFontNames() else 'Roboto', 18)
            c.setFillColorRGB(0, 0, 0)
            c.drawString(info_x + rect_w + 20, y + rect_h - 16, label)
            c.setFont('Roboto', 16)
            c.drawString(info_x + rect_w + 20, y + rect_h - 36, name.capitalize())

        c.save()

        # --- Объединение с шаблоном PDF для цветотипа ---
        color_type_raw = analysis.get('color_type', '').lower().replace('ё', 'е').replace(' ', '_')
        template_aliases = {
            'мягкое_лето': 'soft_summer',
            'soft_summer': 'soft_summer',
            'яркая_весна': 'bright_spring',
            'bright_spring': 'bright_spring',
            'теплая_весна': 'warm_spring',
            'warm_spring': 'warm_spring',
            'светлая_весна': 'light_spring',
            'light_spring': 'light_spring',
            'холодное_лето': 'cool_summer',
            'cool_summer': 'cool_summer',
            'cold_summer': 'cool_summer',
            'глубокая_осень': 'dark_autumn',
            'deep_autumn': 'dark_autumn',
            'темная_осень': 'dark_autumn',
            'тёмная_осень': 'dark_autumn',
            'dark_autumn': 'dark_autumn',
            'тёплая_осень': 'warm_autumn',
            'теплая_осень': 'warm_autumn',
            'warm_autumn': 'warm_autumn',
            'мягкая_осень': 'soft_autumn',
            'soft_autumn': 'soft_autumn',
            'яркая_зима': 'bright_winter',
            'bright_winter': 'bright_winter',
            'глубокая_зима': 'dark_winter',
            'deep_winter': 'dark_winter',
            'темная_зима': 'dark_winter',
            'тёмная_зима': 'dark_winter',
            'dark_winter': 'dark_winter',
            'холодная_зима': 'cool_winter',
            'cool_winter': 'cool_winter',
        }
        color_type_key = template_aliases.get(color_type_raw, color_type_raw)
        template_path = f'static/pdf_templates/{color_type_key}.pdf'
        print('PDF MERGE:', color_type_raw, '->', color_type_key, template_path, os.path.exists(template_path))
        
        try:
            if os.path.exists(template_path):
                print(f'Starting PDF merge with template: {template_path}')
                writer = PdfWriter()
                
                # Первая страница (наш отчет)
                print(f'Adding report pages from: {output_path}')
                with open(output_path, 'rb') as f1:
                    reader1 = PdfReader(f1)
                    print(f'Report PDF has {len(reader1.pages)} pages')
                    for page in reader1.pages:
                        writer.add_page(page)
                
                # Добавляем все страницы romantic.pdf (включая первую)
                if os.path.exists(template_path):
                    with open(template_path, 'rb') as f2:
                        reader2 = PdfReader(f2)
                        for page in reader2.pages:
                            writer.add_page(page)
                
                # Сохраняем объединённый файл
                print(f'Saving merged PDF to: {output_path}')
                with open(output_path, 'wb') as fout:
                    writer.write(fout)
                print('PDF merge completed successfully')
                
                # Проверяем, что файл создался и имеет размер
                if os.path.exists(output_path):
                    file_size = os.path.getsize(output_path)
                    print(f'Merged PDF file size: {file_size} bytes')
                else:
                    print('ERROR: Merged PDF file was not created')
            else:
                print(f'Template file not found: {template_path}')
        except Exception as e:
            print('PDF MERGE ERROR:', str(e))
            import traceback
            print('Traceback:', traceback.format_exc())

        return output_path
    except Exception as e:
        print('PDF ERROR:', e)
        raise
    finally:
        # Удаляем все временные файлы
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f'Error removing temporary file {temp_file}:', e)


def normalize_email_for_filename(email):
    """Нормализует email для использования в имени файла: убирает спецсимволы"""
    if not email:
        return ""
    # Убираем @ и заменяем точки на пустую строку
    normalized = email.replace('@', '').replace('.', '').replace('_', '').replace('-', '')
    # Убираем все остальные спецсимволы, оставляем только буквы и цифры
    normalized = ''.join(c for c in normalized if c.isalnum())
    return normalized.lower()


def generate_kibbe_pdf(user_photo_path: str, kibbe_type: str = None, output_path: str = None, email: str = None):
    """
    Генерирует PDF для типажа Кибби: накладывает фото пользователя на PNG-шаблон первой страницы.
    """
    from reportlab.lib.pagesizes import A4
    from PIL import Image, ImageDraw
    import uuid
    from datetime import datetime
    
    PAGE_WIDTH, PAGE_HEIGHT = A4  # 595 x 842 pt
    
    # Генерируем уникальное имя файла на основе типажа Кибби
    if not output_path:
        kibbe_type_lower = kibbe_type.lower() if kibbe_type else 'romantic'
        # Нормализуем название типажа для использования в имени файла
        kibbe_name_mapping = {
            'романтик': 'romantic',
            'romantic': 'romantic',
            'драматик': 'dramatic',
            'dramatic': 'dramatic',
            'классик': 'classic',
            'classic': 'classic',
            'натурал': 'natural',
            'natural': 'natural',
            'гамин': 'gamine',
            'gamine': 'gamine'
        }
        normalized_kibbe = kibbe_name_mapping.get(kibbe_type_lower, 'romantic')
        
        # Создаем уникальное имя с timestamp и UUID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        
        # Добавляем email в название файла, если он передан
        email_part = ""
        if email:
            normalized_email = normalize_email_for_filename(email)
            if normalized_email:
                email_part = f"_{normalized_email}"
        
        filename = f'kibbe_{normalized_kibbe}_{timestamp}_{unique_id}{email_part}.pdf'
        output_path = os.path.join(REPORTS_DIR, filename)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Определяем шаблон на основе типажа
    kibbe_type_lower = kibbe_type.lower() if kibbe_type else 'romantic'
    template_aliases = {
        'романтик': 'romantic',
        'romantic': 'romantic',
        'драматик': 'romantic',  # пока используем romantic как базовый
        'dramatic': 'romantic',
        'классик': 'classic',
        'classic': 'classic',
        'натурал': 'romantic',
        'natural': 'romantic',
        'гамин': 'gamine',
        'gamine': 'gamine'
    }
    
    template_key = template_aliases.get(kibbe_type_lower, 'romantic')
    jpg_template_path = f'static/pdf_templates/{template_key}_first_page.jpg'
    pdf_template_path = f'static/pdf_templates/{template_key}.pdf'
    
    print(f'Kibbe PDF: тип {kibbe_type} -> JPG шаблон {jpg_template_path}')
    
    if not os.path.exists(jpg_template_path):
        print(f'JPG template not found: {jpg_template_path}, using default')
        jpg_template_path = 'static/pdf_templates/romantic_first_page.jpg'

    try:
        # Загружаем JPG-шаблон
        template_img = Image.open(jpg_template_path).convert('RGBA')
        template_width, template_height = template_img.size
        # --- ВРЕМЕННО: вставляем user_photo_path напрямую в PDF ---
        from reportlab.pdfgen import canvas
        temp_first_pdf = output_path + '_firstpage.pdf'
        c = canvas.Canvas(temp_first_pdf, pagesize=(template_width, template_height))
        c.drawImage(jpg_template_path, 0, 0, width=template_width, height=template_height)
        # Вставляем фото пользователя (без crop, без PIL)
        photo_x = 121
        photo_y = 151
        c.drawImage(user_photo_path, photo_x, photo_y, width=456, height=456)
        c.save()

        # Мерджим с соответствующим PDF шаблоном начиная со второй страницы
        writer = PdfWriter()
        # Добавляем первую страницу (с фото)
        with open(temp_first_pdf, 'rb') as f1:
            reader1 = PdfReader(f1)
            writer.add_page(reader1.pages[0])
        # Добавляем все страницы romantic.pdf (включая первую)
        if os.path.exists(pdf_template_path):
            with open(pdf_template_path, 'rb') as f2:
                reader2 = PdfReader(f2)
                for page in reader2.pages:
                    writer.add_page(page)
        # Сохраняем финальный PDF
        with open(output_path, 'wb') as fout:
            writer.write(fout)
        os.remove(temp_first_pdf)
        
        # Проверяем, что файл создался и имеет размер
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f'Kibbe PDF generated successfully: {output_path}')
            print(f'Kibbe PDF file size: {file_size} bytes')
        else:
            print('ERROR: Kibbe PDF file was not created')
        
        return output_path
        
    except Exception as e:
        print(f'Error generating Kibbe PDF: {str(e)}')
        import traceback
        print('Traceback:', traceback.format_exc())
        raise 