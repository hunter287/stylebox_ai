from flask import Flask, request, jsonify, render_template, send_file, session
import os
from werkzeug.utils import secure_filename
from color_analysis import ColorAnalyzer
from pdf_report import generate_pdf_report, generate_kibbe_pdf
import cv2
import json
from config import CLOUDPAYMENTS_PUBLIC_ID, UNISENDER_API_KEY, UNISENDER_LIST_ID, UNISENDER_GO_API_KEY, OPENAI_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SHEET_RANGE, GOOGLE_SHEET_WORKSHEET, GOOGLE_SHEET_KIBBE_WORKSHEET, GOOGLE_SERVICE_ACCOUNT_FILE
import requests
import random
import string
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import re
import shutil
import uuid
import pillow_heif
from PIL import Image, UnidentifiedImageError, ExifTags
import logging
import gspread
from google.oauth2.service_account import Credentials
import traceback
import time
from openai import OpenAI
import base64
import pillow_avif

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()  # Для вывода в консоль
    ]
)
logger = logging.getLogger(__name__)
logger.info("Приложение запущено")

# Регистрация поддержки HEIF
pillow_heif.register_heif_opener()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key')

# Список доступных пресетов цветотипов
PRESET_COLOR_TYPES = [
    'яркая зима', 'холодная зима', 'глубокая зима',
    'яркая весна', 'тёплая весна', 'светлая весна',
    'яркое лето', 'холодное лето', 'мягкое лето',
    'яркая осень', 'тёплая осень', 'глубокая осень',
    'soft_summer', 'deep_winter', 'warm_autumn',
    'cool_winter', 'cool winter', 'cold_winter', 'cold winter', 'холодная зима'
]

# Создаем директорию для загрузок, если она не существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/reports', exist_ok=True)

# Список поддерживаемых форматов изображений
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic', 'heif', 'avif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def fix_orientation(img):
    """Поворачивает изображение согласно EXIF Orientation, если нужно"""
    try:
        exif = img._getexif()
        if exif:
            orientation_tag = None
            for tag, value in ExifTags.TAGS.items():
                if value == 'Orientation':
                    orientation_tag = tag
                    break
            if orientation_tag:
                orientation = exif.get(orientation_tag, 1)
                if orientation == 3:
                    img = img.rotate(180, expand=True)
                    logger.info("EXIF: Применен поворот на 180 градусов")
                elif orientation == 6:
                    img = img.rotate(270, expand=True)
                    logger.info("EXIF: Применен поворот на 270 градусов (Rotate 90 CW)")
                elif orientation == 8:
                    img = img.rotate(90, expand=True)
                    logger.info("EXIF: Применен поворот на 90 градусов (Rotate 270 CW)")
                else:
                    logger.info(f"EXIF: Ориентация {orientation}, поворот не требуется")
            else:
                logger.info("EXIF: Тег Orientation не найден")
        else:
            logger.info("EXIF: Данные отсутствуют")
    except Exception as e:
        logger.info(f'EXIF orientation error: {e}')
    return img

def convert_to_jpg(image_path, target_width=800):
    try:
        logger.info(f"Начало конвертации изображения: {image_path}")
        with Image.open(image_path) as img:
            logger.info(f"Исходное изображение: формат={img.format}, размер={img.size}, режим={img.mode}")
            # Применяем EXIF-ориентацию
            img = fix_orientation(img)
            # Ресайз с сохранением пропорций
            w_percent = (target_width / float(img.size[0]))
            h_size = int((float(img.size[1]) * float(w_percent)))
            img = img.resize((target_width, h_size), Image.LANCZOS)
            logger.info(f"Изображение изменено до размеров {img.size}")
            # Конвертация в RGB, если нужно
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            # Сохраняем как JPG
            jpg_path = os.path.splitext(image_path)[0] + '.jpg'
            img.save(jpg_path, 'JPEG', quality=95)
            logger.info(f"JPG успешно создан, размер: {os.path.getsize(jpg_path)} байт")
            return jpg_path
    except Exception as e:
        logger.error(f"Ошибка при конвертации изображения: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise

def resize_image(image_path, max_size=800):
    """Изменяет размер изображения, сохраняя пропорции.
    max_size - максимальный размер по длинной стороне в пикселях"""
    try:
        with Image.open(image_path) as img:
            # Получаем текущие размеры
            width, height = img.size
            
            # Определяем, какая сторона длиннее
            if width > height:
                new_width = max_size
                new_height = int(height * (max_size / width))
            else:
                new_height = max_size
                new_width = int(width * (max_size / height))
            
            # Изменяем размер
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Сохраняем с тем же именем
            resized_img.save(image_path, quality=95, optimize=True)
            logger.info(f"Изображение изменено до размеров {new_width}x{new_height}")
            return image_path
    except Exception as e:
        logger.error(f"Ошибка при изменении размера изображения: {str(e)}")
        raise

def cleanup_temp_files(filepath):
    """Удаляет временные файлы после анализа"""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Временный файл удален: {filepath}")
    except Exception as e:
        logger.error(f"Ошибка при удалении временного файла {filepath}: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html', config={'CLOUDPAYMENTS_PUBLIC_ID': CLOUDPAYMENTS_PUBLIC_ID})

@app.route('/payment-success')
def payment_success():
    return render_template('payment_success.html')

@app.route('/analyze', methods=['POST', 'GET'])
def analyze():
    print("=== DEBUG: Запрос получен ===")
    logger.info("=== Начало обработки запроса /analyze ===")
    logger.info(f"Метод запроса: {request.method}")
    logger.info(f"Заголовки запроса: {dict(request.headers)}")
    logger.info(f"Форма запроса: {request.form}")
    logger.info(f"Файлы в запросе: {request.files}")
    
    if 'image' not in request.files:
        logger.warning("Файл изображения не найден в запросе")
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['image']
    if file.filename == '':
        logger.warning("Имя файла пустое")
        return jsonify({'error': 'No selected file'}), 400
    
    logger.info(f"Получен файл: {file.filename}")
    logger.info(f"Тип файла: {file.content_type}")
    
    # Проверяем, является ли файл HEIC
    is_heic = file.filename.lower().endswith(('.heic', '.heif'))
    logger.info(f"Файл HEIC/HEIF: {is_heic}")
    
    if not allowed_file(file.filename):
        logger.warning(f"Неподдерживаемый формат файла: {file.filename}")
        return jsonify({'error': f'Неподдерживаемый формат файла. Поддерживаемые форматы: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    try:
        # Сохраняем файл
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Логируем информацию о файле до сохранения
        logger.info("=== Информация о загружаемом файле ===")
        logger.info(f"Исходное имя файла: {file.filename}")
        logger.info(f"Безопасное имя файла: {filename}")
        logger.info(f"Тип файла: {file.content_type}")
        file_content = file.read()
        logger.info(f"Размер файла: {len(file_content)} байт")
        file.seek(0)  # Возвращаем указатель в начало файла
        
        # Проверяем, что это действительно HEIC файл
        if is_heic:
            logger.info("Обнаружен HEIC/HEIF файл")
            try:
                # Пробуем открыть файл как HEIC до сохранения
                with Image.open(file) as img:
                    logger.info(f"HEIC файл успешно открыт: формат={img.format}, размер={img.size}, режим={img.mode}")
            except Exception as e:
                logger.error(f"Ошибка при проверке HEIC файла: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return jsonify({'error': 'Ошибка при проверке HEIC файла'}), 400
        
        logger.info(f"Сохранение файла: {filepath}")
        file.save(filepath)
        
        logger.info(f"Файл сохранен: {filepath}")
        logger.info(f"Размер файла на диске: {os.path.getsize(filepath)} байт")
        logger.info(f"Тип файла: {file.content_type}")

        # Проверяем и конвертируем изображение если нужно
        try:
            logger.info("Открытие изображения для проверки")
            with Image.open(filepath) as img:
                logger.info(f"Формат изображения: {img.format}")
                logger.info(f"Размер: {img.size}")
                logger.info(f"Режим: {img.mode}")
                
                # Проверяем, что изображение не пустое
                if img.size[0] == 0 or img.size[1] == 0:
                    raise Exception("Изображение имеет нулевой размер")
                
        except UnidentifiedImageError:
            logger.error(f"Неподдерживаемый формат изображения: {filepath}")
            cleanup_temp_files(filepath)
            return jsonify({'error': 'Неподдерживаемый формат изображения'}), 400
        except Exception as e:
            logger.error(f"Ошибка при открытии изображения: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            cleanup_temp_files(filepath)
            return jsonify({'error': 'Ошибка при обработке изображения'}), 400

        # Конвертируем в JPG если это не JPG
        original_filepath = filepath
        if not filename.lower().endswith(('.jpg', '.jpeg')):
            try:
                logger.info(f"Начало конвертации {filename} в JPG")
                jpg_path = convert_to_jpg(filepath)
                cleanup_temp_files(filepath)  # Удаляем оригинальный файл
                filepath = jpg_path
                logger.info(f"Изображение сконвертировано в JPG: {filepath}")
            except Exception as e:
                logger.error(f"Ошибка при конвертации в JPG: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                cleanup_temp_files(filepath)
                return jsonify({'error': 'Ошибка при конвертации изображения'}), 500

        # Изменяем размер изображения
        try:
            filepath = resize_image(filepath, max_size=800)
            logger.info(f"Размер изображения изменен: {filepath}")
        except Exception as e:
            logger.error(f"Ошибка при изменении размера: {str(e)}")
            # Продолжаем работу с оригинальным размером

        # Проверяем имя файла: если это цветотип, возвращаем готовый результат
        filename_wo_ext = os.path.splitext(os.path.basename(filepath))[0].lower()
        analyzer = ColorAnalyzer()
        if filename_wo_ext in PRESET_COLOR_TYPES:
            logger.info(f"Используем пресет для: {filename_wo_ext}")
            preset_result = analyzer.get_preset_analysis(filename_wo_ext)
            preset_result["main_palette_hex"] = preset_result.get("bright_colors_hex", [])[:9]
            preset_result["additional_palette_hex"] = preset_result.get("bright_colors_hex", [])
            session['last_analysis'] = preset_result
            session['last_image_path'] = filepath
            return jsonify(preset_result)

        # Обычный анализ изображения
        result = analyzer.analyze_image(filepath)
        logger.info(f"Результат анализа: {json.dumps(result, ensure_ascii=False)}")
        
        if not result:
            logger.error("Анализ вернул пустой результат")
            # cleanup_temp_files(filepath)
            return jsonify({'error': 'Не удалось проанализировать изображение'}), 500

        session['last_analysis'] = result
        session['last_image_path'] = filepath
        
        # Генерируем analysis_id и сохраняем анализ/изображение
        analysis_id = str(uuid.uuid4())
        result['analysis_id'] = analysis_id
        
        # Сохраняем результаты анализа
        analysis_path = f'static/reports/last_analysis_{analysis_id}.json'
        with open(analysis_path, 'w') as f:
            json.dump(result, f)
        
        # Копируем изображение в reports
        image_path = f'static/reports/last_image_{analysis_id}.jpg'
        shutil.copyfile(filepath, image_path)
        
        # Удаляем временный файл после успешного анализа
        # cleanup_temp_files(filepath)
        
        logger.info(f"Анализ сохранен с ID: {analysis_id}")
        return jsonify({**result, 'analysis_id': analysis_id})
        
    except Exception as e:
        logger.error(f"Ошибка в /analyze: {str(e)}")
        if 'filepath' in locals():
            # cleanup_temp_files(filepath)
            pass
        return jsonify({'error': 'Произошла ошибка при обработке изображения'}), 500

def make_report_filename(email):
    # Берём только буквы/цифры до @
    prefix_raw = ''.join([c for c in email.split('@')[0] if c.isalnum()])
    prefix = prefix_raw[:4] if len(prefix_raw) > 1 else prefix_raw
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    date = datetime.now().strftime('%Y%m%d')
    return f"{prefix}_{rand}_report_{date}.pdf"

def send_guide_email(email, pdf_path):
    # Используем Web API Unisender Go для транзакционных писем
    api_key = UNISENDER_GO_API_KEY
    api_url = "https://go2.unisender.ru/ru/transactional/api/v1/email/send.json"
    from_email = 'info@stylebox.live'
    to_email = email

    # Формируем URL для скачивания PDF
    pdf_url = request.host_url.rstrip('/') + '/' + pdf_path

    payload = {
        "api_key": api_key,
        "message": {
            "recipients": [
                {"email": to_email}
            ],
            "from_email": from_email,
            "from_name": "Style Box AI",
            "subject": "Ваш персональный цветовой гайд",
            "body": {
                "html": (
                    "<html><body>"
                    "<p>Здравствуйте!<br><br>"
                    "Спасибо за приобретение персонального цветового гайда.<br>"
                    f"Скачать ваш гайд можно по <a href=\"{pdf_url}\">ссылке</a>.<br><br>"
                    "Вы также можете оформить <b><a href=\"https://ai.stylebox.live/oto?utm_source=emai_guide\" style=\"color:#bb279b;\">предзаказ на ИИ-стилиста</a></b> с дополнительной скидкой 500 руб., т.к. вы купили персональный гайд.<br>"
                    "Итого, для вас ИИ-стилист на целый год будет стоить <b>4490 руб.<br><br>"
                    "С уважением,<br>"
                    "Style Box AI<br><br>"
                    "<a href=\"https://noreply.stylebox.live/ru/go2_unsubscribe\" style=\"color:#7C3AED;\">Отписаться от рассылки</a>"
                    "</p></body></html>"
                ),
                "plaintext": "Здравствуйте! Спасибо за приобретение персонального цветового гайда. Ссылка на ваш гайд: {pdf_url}\n\nВы также можете оформить предзаказ на ИИ-стилиста со скидкой 500 руб. по ссылке: https://ai.stylebox.live/oto?utm_source=emai_guide\nИтого, для вас ИИ-стилист на целый год будет стоить 4490 руб.".format(pdf_url=pdf_url)
            }
        }
    }

    print("Отправка письма через Unisender Go Transactional API...")
    print(f"API URL: {api_url}")
    print(f"From: {from_email}")
    print(f"To: {to_email}")
    print(f"PDF URL: {pdf_url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")

    try:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        response = requests.post(api_url, json=payload, headers=headers, verify=False)
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {response.headers}")
        print(f"Response body: {response.text}")

        if response.status_code == 200:
            print("Письмо отправлено через Unisender Go Transactional API!")
            return True
        else:
            print(f"Ошибка отправки письма: {response.text}")
            return False
    except requests.exceptions.SSLError as e:
        print(f"SSL ошибка: {str(e)}")
        return False
    except Exception as e:
        print(f"Ошибка при отправке письма: {str(e)}")
        return False


def send_kibbe_guide_email(email, pdf_path):
    # Используем Web API Unisender Go для транзакционных писем
    api_key = UNISENDER_GO_API_KEY
    api_url = "https://go2.unisender.ru/ru/transactional/api/v1/email/send.json"
    from_email = 'info@stylebox.live'
    to_email = email

    # Формируем URL для скачивания PDF
    pdf_url = request.host_url.rstrip('/') + '/' + pdf_path

    payload = {
        "api_key": api_key,
        "message": {
            "recipients": [
                {"email": to_email}
            ],
            "from_email": from_email,
            "from_name": "Style Box AI",
            "subject": "Ваш персональный гайд по стилю",
            "body": {
                "html": (
                    "<html><body>"
                    "<p>Здравствуйте!<br><br>"
                    "Спасибо за приобретение персонального гайда по стилю.<br>"
                    f"Скачать ваш гайд можно по <a href=\"{pdf_url}\">ссылке</a>.<br><br>"
                    "Вы также можете оформить <b><a href=\"https://ai.stylebox.live/oto?utm_source=emai_guide\" style=\"color:#bb279b;\">предзаказ на ИИ-стилиста</a></b> с дополнительной скидкой 500 руб., т.к. вы купили персональный гайд.<br>"
                    "Итого, для вас ИИ-стилист на целый год будет стоить <b>4490 руб.<br><br>"
                    "С уважением,<br>"
                    "Style Box AI<br><br>"
                    "<a href=\"https://noreply.stylebox.live/ru/go2_unsubscribe\" style=\"color:#7C3AED;\">Отписаться от рассылки</a>"
                    "</p></body></html>"
                ),
                "plaintext": "Здравствуйте! Спасибо за приобретение персонального гайда по стилю. Ссылка на ваш гайд: {pdf_url}\n\nВы также можете оформить предзаказ на ИИ-стилиста со скидкой 500 руб. по ссылке: https://ai.stylebox.live/oto?utm_source=emai_guide\nИтого, для вас ИИ-стилист на целый год будет стоить 4490 руб.".format(pdf_url=pdf_url)
            }
        }
    }

    print("Отправка письма с гайдом по Кибби через Unisender Go Transactional API...")
    print(f"API URL: {api_url}")
    print(f"From: {from_email}")
    print(f"To: {to_email}")
    print(f"PDF URL: {pdf_url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")

    try:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        response = requests.post(api_url, json=payload, headers=headers, verify=False)
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {response.headers}")
        print(f"Response body: {response.text}")

        if response.status_code == 200:
            print("Письмо с гайдом по Кибби отправлено через Unisender Go Transactional API!")
            return True
        else:
            print(f"Ошибка отправки письма с гайдом по Кибби: {response.text}")
            return False
    except requests.exceptions.SSLError as e:
        print(f"SSL ошибка: {str(e)}")
        return False
    except Exception as e:
        print(f"Ошибка при отправке письма с гайдом по Кибби: {str(e)}")
        return False

def wait_for_file_complete(filepath, min_size=10*1024, timeout=10):
    """Ждёт, пока файл не появится и не станет больше min_size байт."""
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(filepath) and os.path.getsize(filepath) > min_size:
            return True
        time.sleep(0.2)
    return False

@app.route('/send_guide_email', methods=['POST'])
def send_guide():
    """Endpoint to send the guide via email"""
    try:
        data = request.get_json()
        email = data.get('email')
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        if 'last_analysis' not in session or 'last_image_path' not in session:
            return jsonify({'error': 'No analysis found'}), 400
        # Генерируем уникальное имя PDF
        filename = make_report_filename(email)
        pdf_path = os.path.join('static/reports', filename)
        analysis = session['last_analysis']
        image_path = session['last_image_path']
        # Пытаемся сгенерировать PDF до 10 раз
        max_attempts = 10
        for attempt in range(max_attempts):
            full_pdf_path = generate_pdf_report(analysis, image_path, output_path=pdf_path)
            print(f"PDF path (attempt {attempt+1}):", full_pdf_path)
            print("PDF exists:", os.path.exists(full_pdf_path))
            # Ждём, пока файл полностью создастся
            if wait_for_file_complete(full_pdf_path):
                break
            else:
                print(f"PDF не был полностью создан (попытка {attempt+1})")
        # Явная проверка после merge
        if os.path.exists(full_pdf_path):
            file_size = os.path.getsize(full_pdf_path)
            print(f"PDF готов к отправке, размер: {file_size} байт")
        else:
            print("PDF не найден после merge!")
        if os.path.exists(full_pdf_path) and os.path.getsize(full_pdf_path) > 10*1024:
            # Отправляем email с вложением
            if send_guide_email(email, full_pdf_path):
                print("Email отправлен после успешного merge PDF!")
                return jsonify({'success': True})
            else:
                print("Ошибка при отправке email после merge PDF!")
                return jsonify({'error': 'Failed to send email'}), 500
        else:
            # Если не удалось — письмо с извинением
            send_guide_email_apology(email)
            return jsonify({'error': 'PDF not created after 10 attempts, apology email sent'}), 500
    except Exception as e:
        print(f"Error in send_guide: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/send_kibbe_guide_email', methods=['POST'])
def send_kibbe_guide():
    """Endpoint to send the Kibbe guide via email"""
    try:
        data = request.get_json()
        email = data.get('email')
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        if 'last_kibbe_analysis' not in session or 'last_kibbe_image_path' not in session:
            return jsonify({'error': 'No Kibbe analysis found'}), 400
        
        analysis = session['last_kibbe_analysis']
        image_path = session['last_kibbe_image_path']
        kibbe_type = analysis.get('kibbe_type', 'romantic')
        
        # Проверяем, что файл с фото существует
        if not os.path.exists(image_path):
            print(f"Image file not found: {image_path}")
            send_guide_email_apology(email)
            return jsonify({'error': 'Image file not found'}), 404
        
        preview_image_dataurl = data.get('preview_image')
        preview_image_path = None
        if preview_image_dataurl:
            import base64, re, time
            header, encoded = preview_image_dataurl.split(',', 1)
            ext = 'jpg' if 'jpeg' in header or 'jpg' in header else 'png'
            preview_image_path = f"uploads/kibbe_preview_{int(time.time())}.{ext}"
            with open(preview_image_path, 'wb') as f:
                f.write(base64.b64decode(encoded))
            print(f"[send_kibbe_guide_email] Saved preview image: {preview_image_path}")
        # Для PDF используем превью, если оно есть
        pdf_photo_path = preview_image_path if preview_image_path else image_path
        # Генерируем PDF для Кибби
        try:
            full_pdf_path = generate_kibbe_pdf(
                user_photo_path=pdf_photo_path,
                kibbe_type=kibbe_type,
                email=email
            )
            print(f"Kibbe PDF generated: {full_pdf_path}")
            if preview_image_path:
                try:
                    os.remove(preview_image_path)
                except Exception as e:
                    print(f"[send_kibbe_guide_email] Error removing temp preview: {e}")
            
            if os.path.exists(full_pdf_path) and os.path.getsize(full_pdf_path) > 10*1024:
                # Отправляем email с гайдом по Кибби
                if send_kibbe_guide_email(email, full_pdf_path):
                    print("Kibbe guide email sent successfully!")
                    return jsonify({'success': True})
                else:
                    print("Error sending Kibbe guide email!")
                    return jsonify({'error': 'Failed to send Kibbe guide email'}), 500
            else:
                # Если не удалось — письмо с извинением
                send_guide_email_apology(email)
                return jsonify({'error': 'Kibbe PDF not created, apology email sent'}), 500
        except Exception as e:
            print(f"Error generating Kibbe PDF: {str(e)}")
            send_guide_email_apology(email)
            return jsonify({'error': f'Error generating Kibbe PDF: {str(e)}'}), 500
            
    except Exception as e:
        print(f"Error in send_kibbe_guide: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Функция для отправки письма с извинением
def send_guide_email_apology(email):
    smtp_host = 'smtp.go2.unisender.ru'
    smtp_port = 587
    smtp_user = '7632090'
    smtp_pass = UNISENDER_GO_API_KEY
    from_email = 'info@stylebox.live'
    to_email = email

    msg = MIMEMultipart()
    msg['Subject'] = 'Извинения: не удалось сформировать гайд'
    msg['From'] = from_email
    msg['To'] = to_email

    body = f"""Здравствуйте!

К сожалению, возникла техническая ошибка при формировании вашего PDF-отчёта.
Пожалуйста, попробуйте повторить попытку или свяжитесь с поддержкой.
Style Box AI
"""
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, [to_email], msg.as_string())
    print("Письмо с извинением отправлено!")

@app.route('/get_guide_pdf')
def get_guide_pdf():
    email = request.args.get('email')
    # Можно искать PDF по email или по сессии (как сейчас делается для анализа)
    if 'last_analysis' in session and 'last_image_path' in session:
        analysis = session['last_analysis']
        image_path = session['last_image_path']
        filename_wo_ext = os.path.splitext(os.path.basename(image_path))[0].lower()
        pdf_path = os.path.join('static/reports', f'report_{filename_wo_ext}.pdf')
        # Генерируем PDF, если его нет
        full_pdf_path = generate_pdf_report(analysis, image_path, output_path=pdf_path)
        if os.path.exists(full_pdf_path):
            return jsonify({'download_url': '/' + full_pdf_path})
        else:
            return jsonify({'error': 'PDF not found'}), 404
    return jsonify({'error': 'No analysis found'}), 400

@app.route('/paid_callback', methods=['POST'])
def paid_callback():
    # Получаем данные из form-data или JSON
    print("[paid_callback] Request method:", request.method)
    print("[paid_callback] Request headers:", dict(request.headers))
    print("[paid_callback] Request form data:", dict(request.form))
    print("[paid_callback] Request JSON:", request.get_json())
    
    data = request.form if request.form else request.get_json()
    print("[paid_callback] Webhook data:", dict(data))
    print("[paid_callback] after webhook data print")
    status = str(data.get('Status', '')).lower()
    print("[paid_callback] after status extraction")
    email = data.get('Email')
    print("[paid_callback] after email extraction")
    
    # Получаем Data и парсим его как JSON
    data_json = {}
    if data.get('Data'):
        try:
            data_json = json.loads(data.get('Data'))
        except:
            data_json = {}
    
    analysis_id = (
        data_json.get('analysis_id') or
        data.get('analysis_id') or
        data.get('AnalysisId') or
        data.get('analysisId')
    )
    print("[paid_callback] after analysis_id extraction, value:", analysis_id)
    custom_fields = data.get('CustomFields')
    print("[paid_callback] after custom_fields extraction")
    custom_fields_dict = {}  # всегда определяем заранее
    if not analysis_id and custom_fields:
        print("[paid_callback] inside custom_fields block")
        # Если custom_fields — строка, распарсить как JSON
        if isinstance(custom_fields, str) and custom_fields:
            try:
                import json as _json
                custom_fields_dict = _json.loads(custom_fields)
            except Exception:
                custom_fields_dict = {}
        elif isinstance(custom_fields, dict):
            custom_fields_dict = custom_fields
        else:
            custom_fields_dict = {}
        analysis_id = (
            custom_fields_dict.get('analysis_id') or
            custom_fields_dict.get('AnalysisId') or
            custom_fields_dict.get('analysisId')
        )
        print("[paid_callback] after custom_fields_dict extraction, value:", analysis_id)
    print("[paid_callback] Email:", email)
    print("[paid_callback] Analysis ID:", analysis_id)
    print("[paid_callback] Description:", description)
    print("[paid_callback] Custom fields:", custom_fields)
    print("[paid_callback] Guide type:", guide_type)
    
    # Определяем тип покупки по описанию и дополнительным данным
    description = data.get('Description', '').lower()
    custom_fields = data.get('Data', {})
    guide_type = custom_fields.get('guideType', '')
    
    is_kibbe_guide = ('стиль' in description or 'типаж' in description or 'kibbe' in description or 
                     guide_type == 'kibbe')
    
    if is_kibbe_guide:
        # Для гайдов по Кибби используем данные из сессии
        analysis_path = None
        image_path = None
        pdf_path = None
        print("[paid_callback] Kibbe guide purchase detected")
    else:
        # Для цветотипов используем старую логику
        analysis_path = f'static/reports/last_analysis_{analysis_id}.json'
        image_path = f'static/reports/last_image_{analysis_id}.jpg'
        pdf_path = f'static/reports/report_{normalize_email(email)}_{analysis_id}.pdf'
        print("[paid_callback] Color guide purchase detected")
    
    print("[paid_callback] Analysis path:", analysis_path, "Exists:", os.path.exists(analysis_path) if analysis_path else "N/A")
    print("[paid_callback] Image path:", image_path, "Exists:", os.path.exists(image_path) if image_path else "N/A")
    print("[paid_callback] PDF path:", pdf_path)
    
    if status == 'completed':
        # Получаем email и analysis_id из данных
        if not email:
            print("Missing required data: email")
            return jsonify({'code': 10, 'message': 'No email'}), 400

        if is_kibbe_guide:
            # Обработка покупки гайда по Кибби
            try:
                # Генерируем PDF для Кибби и отправляем email
                if 'last_kibbe_analysis' in session and 'last_kibbe_image_path' in session:
                    analysis = session['last_kibbe_analysis']
                    image_path = session['last_kibbe_image_path']
                    kibbe_type = analysis.get('kibbe_type', 'romantic')
                    
                    # Проверяем, что файл с фото существует
                    if not os.path.exists(image_path):
                        print(f"[paid_callback] Image file not found: {image_path}")
                        return jsonify({'code': 11, 'message': 'Image file not found'}), 404
                    
                    # Генерируем PDF для Кибби
                    full_pdf_path = generate_kibbe_pdf(
                        user_photo_path=image_path,
                        kibbe_type=kibbe_type,
                        email=email
                    )
                    print(f"[paid_callback] Kibbe PDF generated: {full_pdf_path}")
                    
                    if os.path.exists(full_pdf_path) and os.path.getsize(full_pdf_path) > 10*1024:
                        # Отправляем email с гайдом по Кибби
                        if send_kibbe_guide_email(email, full_pdf_path):
                            print("[paid_callback] Kibbe guide email sent successfully!")
                            return jsonify({'code': 0, 'message': 'Kibbe guide sent successfully'}), 200
                        else:
                            print("[paid_callback] Error sending Kibbe guide email!")
                            return jsonify({'code': 12, 'message': 'Failed to send Kibbe guide email'}), 500
                    else:
                        print("[paid_callback] Kibbe PDF not created or too small")
                        return jsonify({'code': 11, 'message': 'Kibbe PDF not created'}), 500
                else:
                    print("[paid_callback] No Kibbe analysis found in session")
                    return jsonify({'code': 11, 'message': 'No Kibbe analysis found'}), 404
            except Exception as e:
                print(f"[paid_callback] Error processing Kibbe guide purchase: {str(e)}")
                return jsonify({'code': 14, 'message': f'Kibbe processing error: {str(e)}'}), 500
        else:
            # Обработка покупки гайда по цветотипу (старая логика)
            if not analysis_id:
                print("Missing required data: analysis_id for color guide")
                return jsonify({'code': 10, 'message': 'No analysis_id for color guide'}), 400

            # Проверяем наличие файлов анализа и изображения
            if os.path.exists(analysis_path) and os.path.exists(image_path):
                try:
                    # Загружаем данные анализа
                    with open(analysis_path) as f:
                        analysis = json.load(f)
                    
                    # Генерируем PDF для цветотипа
                    full_pdf_path = generate_pdf_report(
                        user_photo_path=image_path,
                        analysis=analysis
                    )
                    print(f"[paid_callback] Color PDF generated: {full_pdf_path}")
                    
                    if os.path.exists(full_pdf_path) and os.path.getsize(full_pdf_path) > 10*1024:
                        # Отправляем email с гайдом по цветотипу
                        if send_guide_email(email, full_pdf_path):
                            print("[paid_callback] Color guide email sent successfully!")
                            return jsonify({'code': 0, 'message': 'Color guide sent successfully'}), 200
                        else:
                            print("[paid_callback] Error sending color guide email!")
                            return jsonify({'code': 12, 'message': 'Failed to send color guide email'}), 500
                    else:
                        print("[paid_callback] Color PDF not created or too small")
                        return jsonify({'code': 11, 'message': 'Color PDF not created'}), 500
                except Exception as e:
                    print(f"Error processing color guide payment: {str(e)}")
                    return jsonify({'code': 14, 'message': f'Processing error: {str(e)}'}), 500
            else:
                print(f"Files not found:\n- Analysis exists: {os.path.exists(analysis_path)}\n- Image exists: {os.path.exists(image_path)}")
                return jsonify({'code': 11, 'message': 'Analysis or image not found'}), 404
    else:
        print(f"Payment not completed, status: {status}")
        return jsonify({'code': 13, 'message': 'Payment not completed'}), 200

def normalize_email(email):
    return ''.join(c for c in email if c.isalnum())

# Отладочная информация
print(f"[DEBUG] GOOGLE_SHEET_WORKSHEET: {GOOGLE_SHEET_WORKSHEET}")
print(f"[DEBUG] GOOGLE_SHEET_KIBBE_WORKSHEET: {GOOGLE_SHEET_KIBBE_WORKSHEET}")

@app.route('/check_email_in_sheet', methods=['POST'])
def check_email_in_sheet():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    print(f"[check_email_in_sheet] Запрошен email: {email}")
    print(f"GOOGLE_SHEET_ID: {GOOGLE_SHEET_ID}")
    print(f"GOOGLE_SERVICE_ACCOUNT_FILE: {GOOGLE_SERVICE_ACCOUNT_FILE}")
    print(f"GOOGLE_SHEET_WORKSHEET: {GOOGLE_SHEET_WORKSHEET}")
    try:
        creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=[
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly',
        ])
        print("creds OK")
        gc = gspread.authorize(creds)
        print("gspread OK")
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        print("open_by_key OK")
        worksheet = sh.worksheet(GOOGLE_SHEET_WORKSHEET)
        print("worksheet OK")
        emails = worksheet.col_values(1)
        print("col_values OK")
        emails = [e.strip().lower() for e in emails if e.strip()]
        print(f"emails: {emails}")
        found = email in emails
        print(f"found: {found}")
        return jsonify({'found': found})
    except Exception as e:
        print(f"[check_email_in_sheet] Ошибка: {str(e)}")
        traceback.print_exc()
        logger.error(f"Ошибка при проверке email в Google Sheets: {str(e)}")
        return jsonify({'found': False, 'error': str(e)}), 500

@app.route('/check_email_in_sheet_kibbe', methods=['POST'])
def check_email_in_kibbe_sheet_endpoint():
    """Endpoint для проверки email в листе 'kibbe'"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        found = check_email_in_kibbe_sheet(email)
        return jsonify({'found': found})
    except Exception as e:
        print(f"[check_email_in_kibbe_sheet_endpoint] Ошибка: {str(e)}")
        return jsonify({'found': False, 'error': str(e)}), 500

def check_email_in_kibbe_sheet(email):
    """Проверяет, есть ли email в листе 'kibbe' в колонке A"""
    email = email.strip().lower()
    print(f"[check_email_in_kibbe_sheet] Проверяем email: {email}")
    print(f"[check_email_in_kibbe_sheet] GOOGLE_SHEET_KIBBE_WORKSHEET: {GOOGLE_SHEET_KIBBE_WORKSHEET}")
    print(f"[check_email_in_kibbe_sheet] GOOGLE_SHEET_ID: {GOOGLE_SHEET_ID}")
    print(f"[check_email_in_kibbe_sheet] Функция вызвана!")
    
    try:
        creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=[
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly',
        ])
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        
        # Пытаемся открыть лист для Кибби
        try:
            worksheet = sh.worksheet(GOOGLE_SHEET_KIBBE_WORKSHEET)
        except:
            print(f"[check_email_in_kibbe_sheet] Лист '{GOOGLE_SHEET_KIBBE_WORKSHEET}' не найден")
            return False
        
        emails = worksheet.col_values(1)
        emails = [e.strip().lower() for e in emails if e.strip()]
        print(f"[check_email_in_kibbe_sheet] Найдено {len(emails)} email в листе kibbe")
        
        found = email in emails
        print(f"[check_email_in_kibbe_sheet] Email найден: {found}")
        return found
        
    except Exception as e:
        print(f"[check_email_in_kibbe_sheet] Ошибка: {str(e)}")
        traceback.print_exc()
        logger.error(f"Ошибка при проверке email в листе kibbe: {str(e)}")
        return False

@app.route('/oto')
def oto_offer():
    return render_template('oto.html', config={'CLOUDPAYMENTS_PUBLIC_ID': CLOUDPAYMENTS_PUBLIC_ID})

@app.route('/kibbe')
def kibbe_page():
    return render_template('kibbe.html')

@app.route('/analyze_kibbe', methods=['POST'])
def analyze_kibbe():
    if 'image' not in request.files:
        return jsonify({'error': 'Нет файла'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    if not (file.filename.lower().endswith('.jpg') or file.filename.lower().endswith('.jpeg') or file.filename.lower().endswith('.png') or file.filename.lower().endswith('.avif') or file.filename.lower().endswith('.heic') or file.filename.lower().endswith('.heif')):
        return jsonify({'error': 'Поддерживаются только JPG, PNG, AVIF, HEIC'}), 400

    # Получаем рост пользователя (ожидается строка: 'до 160', '161-165', ...)
    user_height_str = request.form.get('height')
    user_height = None
    if user_height_str:
        # Преобразуем в среднее значение диапазона для удобства сравнения
        if user_height_str == 'до 160':
            user_height = 158  # среднее для <160
        elif user_height_str == '161-165':
            user_height = 163
        elif user_height_str == '166-170':
            user_height = 168
        elif user_height_str == '171-175':
            user_height = 173
        elif user_height_str == '176+':
            user_height = 178

    # Email больше не получаем из формы - он будет запрашиваться только при оплате
    user_email = None  # Email будет запрашиваться только при оплате
    print(f"[analyze_kibbe] Анализ без email - гайд будет отправлен только после оплаты")

    # Проверяем название файла на соответствие типажам
    filename_without_ext = os.path.splitext(file.filename)[0].lower()
    
    # Словарь соответствия названий файлов типажам
    type_by_filename = {
        'romantic': 'Романтик',
        'dramatic': 'Драматик',
        'classic': 'Классик',
        'natural': 'Натурал',
        'gamin': 'Гамин'
    }
    
    # Если название файла соответствует типу, возвращаем готовые результаты
    if filename_without_ext in type_by_filename:
        kibbe_type = type_by_filename[filename_without_ext]
        
        # Создаем базовую структуру данных как в реальном анализе
        data = {
            'kibbe_type': kibbe_type,
            'vertical_lines': '',
            'horizontal_lines': '',
            'face_features': '',
            'body_features': '',
            'description': '',
            'style_recommendations': ''  # Сначала очищаем, как в реальном анализе
        }
        
        # Готовые данные для каждого типажа
        type_data = {
            'Романтик': {
                'vertical_lines': 'умеренные',
                'horizontal_lines': 'мягкие, округлые',
                'face_features': 'губы полные, глаза большие, мягкие черты лица',
                'body_features': 'мягкие, округлые линии, выраженная талия',
                'description': 'мягкая, женственная внешность с округлыми чертами',
                'style_recommendations': 'Фасоны одежды\n- Мягкие, облегающие силуэты\n- Округлые вырезы\n- Платья с оборками и рюшами\n\nТкани\n- Шелк, сатин, бархат\n- Мягкие, струящиеся материалы\n- Ткани с блеском\n\nПринты\n- Цветочные узоры\n- Мягкие, округлые мотивы\n- Пастельные тона\n\nАксессуары\n- Округлые формы\n- Жемчуг, стразы\n- Мягкие, женственные детали'
            },
            'Драматик': {
                'vertical_lines': 'длинные, прямые',
                'horizontal_lines': 'широкие, угловатые',
                'face_features': 'губы средние, глаза средние, угловатые черты',
                'body_features': 'длинные линии, угловатые формы',
                'description': 'высокая, угловатая фигура с выразительными чертами',
                'style_recommendations': 'Фасоны одежды\n- Длинные, прямые силуэты\n- Острые углы и линии\n- Минималистичные формы\n\nТкани\n- Плотные, структурированные материалы\n- Кожа, деним\n- Ткани с четкой фактурой\n\nПринты\n- Геометрические узоры\n- Полоски, клетка\n- Контрастные сочетания\n\nАксессуары\n- Угловатые формы\n- Металл, пластик\n- Минималистичные детали'
            },
            'Классик': {
                'vertical_lines': 'сбалансированные',
                'horizontal_lines': 'пропорциональные',
                'face_features': 'губы средние, глаза средние, сбалансированные черты лица',
                'body_features': 'пропорциональная фигура, сбалансированные линии',
                'description': 'сбалансированная, пропорциональная внешность',
                'style_recommendations': 'Фасоны одежды\n- Классические силуэты\n- Сбалансированные пропорции\n- Традиционные формы\n\nТкани\n- Качественные натуральные материалы\n- Шерсть, хлопок, шелк\n- Ткани средней плотности\n\nПринты\n- Классические узоры\n- Полоска, горошек\n- Сдержанные цвета\n\nАксессуары\n- Классические формы\n- Натуральные материалы\n- Сдержанные детали'
            },
            'Натурал': {
                'vertical_lines': 'естественные',
                'horizontal_lines': 'широкие, расслабленные',
                'face_features': 'губы средние, глаза средние, естественные черты',
                'body_features': 'широкие плечи, естественные линии',
                'description': 'естественная, расслабленная внешность',
                'style_recommendations': 'Фасоны одежды\n- Свободные, расслабленные силуэты\n- Естественные линии\n- Комфортные формы\n\nТкани\n- Натуральные материалы\n- Лен, хлопок, шерсть\n- Ткани с естественной фактурой\n\nПринты\n- Природные мотивы\n- Абстрактные узоры\n- Земляные тона\n\nАксессуары\n- Натуральные материалы\n- Дерево, камень, кожа\n- Простые формы'
            },
            'Гамин': {
                'vertical_lines': 'короткие, динамичные',
                'horizontal_lines': 'узкие, игривые',
                'face_features': 'губы средние, глаза большие, выразительные черты',
                'body_features': 'компактная фигура, динамичные линии',
                'description': 'компактная, динамичная внешность с выразительными чертами',
                'style_recommendations': 'Фасоны одежды\n- Короткие, динамичные силуэты\n- Асимметричные линии\n- Игривые формы\n\nТкани\n- Легкие, текстурированные материалы\n- Деним, трикотаж\n- Ткани с интересной фактурой\n\nПринты\n- Геометрические узоры\n- Полоски, клетка\n- Яркие цвета\n\nАксессуары\n- Необычные формы\n- Яркие детали\n- Игривые элементы'
            }
        }
        
        # Заполняем данные для выбранного типажа
        data.update(type_data[kibbe_type])
        
        # --- УЧЁТ РОСТА ---
        # Диапазоны роста для типажей
        height_refs = {
            'Гамин':    (0, 165),
            'Классик':  (163, 172),
            'Натурал':  (168, 183),
            'Драматик': (170, 250),
            'Романтик': (160, 168)
        }
        # Баллы по внешности
        scores = {k: 0 for k in height_refs}
        if kibbe_type in scores:
            scores[kibbe_type] += 0.7  # 70% вес внешности
        # Баллы по росту
        if user_height:
            for t, (h_min, h_max) in height_refs.items():
                if h_min <= user_height <= h_max:
                    scores[t] += 0.3  # 30% вес роста
        # Итоговый типаж — максимальный балл
        final_type = max(scores, key=lambda k: scores[k])
        data["kibbe_type"] = final_type
        # --- END УЧЁТ РОСТА ---

        # Третий запрос: рекомендации по стилю для определённого типажа
        style_recommendations_prompt = f"""
Ты — эксперт по стилю и типажам Кибби. Дай конкретные рекомендации по стилю для типажа {final_type}.

ТИПАЖ: {final_type}

Дай рекомендации по:
1. Фасонам одежды (силуэты, крои)
2. Тканям и фактурам
3. Принтам и узорам
4. Аксессуарам

ВАЖНО:
- НЕ используй фразы типа "Конечно!", "Вот рекомендации:" и т.п.
- Начинай сразу с рекомендаций
- Используй чёткие подзаголовки: "Фасоны одежды", "Ткани", "Принты", "Аксессуары"
- Пиши простым языком, без технических терминов
- Делай рекомендации практичными и конкретными
"""

        try:
            style_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Ты — эксперт по стилю. Дай практичные рекомендации без лишних вступлений."},
                    {"role": "user", "content": style_recommendations_prompt}
                ],
                max_tokens=600,
                temperature=0.7
            )
            style_recommendations = style_response.choices[0].message.content.strip()
            
            # Проверяем, не обрезался ли ответ (если заканчивается на середине предложения)
            if style_recommendations and not style_recommendations.endswith(('.', '!', ':', ';')):
                print("[DEBUG] Рекомендации обрезались, пытаемся получить полный ответ...")
                # Пробуем ещё раз с большим лимитом
                try:
                    style_response_full = openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "Ты — эксперт по стилю. Дай практичные рекомендации без лишних вступлений."},
                            {"role": "user", "content": style_recommendations_prompt}
                        ],
                        max_tokens=800,
                        temperature=0.7
                    )
                    style_recommendations = style_response_full.choices[0].message.content.strip()
                except Exception as e2:
                    print(f"[DEBUG] Вторая попытка получения рекомендаций не удалась: {str(e2)}")
            
            # Очищаем от лишних фраз в начале
            unwanted_starters = [
                "Конечно!",
                "Вот рекомендации:",
                "Конечно! Вот практичные рекомендации",
                "Вот практичные рекомендации",
                "Рекомендации по стилю:",
                "Для типажа",
                "Типаж"
            ]
            
            for starter in unwanted_starters:
                if style_recommendations.startswith(starter):
                    style_recommendations = style_recommendations[len(starter):].strip()
                    break
            
            # Убираем лишние пробелы и переносы в начале
            style_recommendations = style_recommendations.lstrip()
            
            data["style_recommendations"] = style_recommendations
        except Exception as e:
            print("[DEBUG] Ошибка при генерации рекомендаций:", str(e))
            data["style_recommendations"] = "Рекомендации временно недоступны"
        
        # Создаем путь для PDF (для готовых результатов используем заглушку)
        photo_path_for_pdf = os.path.join('uploads', f"kibbe_ready_{int(time.time())}.jpg")
        
        # Сохраняем данные в сессии для последующей отправки гайда
        session['last_kibbe_analysis'] = data
        session['last_kibbe_image_path'] = photo_path_for_pdf
        
        # Проверяем, есть ли email в листе "kibbe"
        if user_email and check_email_in_kibbe_sheet(user_email):
            print(f"[analyze_kibbe] Email {user_email} найден в листе kibbe, отправляем гайд автоматически")
            
            # Генерируем PDF и отправляем email
            try:
                full_pdf_path = generate_kibbe_pdf(
                    user_photo_path=photo_path_for_pdf,
                    kibbe_type=data.get('kibbe_type', 'Кибби'),
                    email=user_email
                )
                print(f"[analyze_kibbe] PDF сгенерирован: {full_pdf_path}")
                
                if os.path.exists(full_pdf_path) and os.path.getsize(full_pdf_path) > 10*1024:
                    if send_kibbe_guide_email(user_email, full_pdf_path):
                        print(f"[analyze_kibbe] Гайд отправлен на {user_email}")
                        data['guide_sent'] = True
                        data['message'] = 'Гайд отправлен на ваш email!'
                    else:
                        print(f"[analyze_kibbe] Ошибка отправки гайда на {user_email}")
                        data['guide_sent'] = False
                        data['message'] = 'Ошибка отправки гайда'
                else:
                    print(f"[analyze_kibbe] PDF не создан или слишком мал")
                    data['guide_sent'] = False
                    data['message'] = 'Ошибка создания PDF'
            except Exception as e:
                print(f"[analyze_kibbe] Ошибка при автоматической отправке гайда: {str(e)}")
                data['guide_sent'] = False
                data['message'] = f'Ошибка: {str(e)}'
        else:
            print(f"[analyze_kibbe] Email {user_email} не найден в листе kibbe или email не указан")
            data['guide_sent'] = False
            data['message'] = 'Для получения гайда необходимо оплатить'
        
        return jsonify(data)

    # Сохраняем файл во временную папку
    ext = os.path.splitext(file.filename)[1].lower()
    temp_path = os.path.join('uploads', f"kibbe_{int(time.time())}{ext}")
    os.makedirs('uploads', exist_ok=True)
    file.save(temp_path)

    # Конвертация AVIF в JPG, если нужно
    if ext == '.avif':
        try:
            with Image.open(temp_path) as img:
                rgb_img = img.convert('RGB')
                jpg_path = temp_path.rsplit('.', 1)[0] + '.jpg'
                rgb_img.save(jpg_path, 'JPEG', quality=95)
            os.remove(temp_path)
            temp_path = jpg_path
        except Exception as e:
            os.remove(temp_path)
            return jsonify({'error': f'Ошибка конвертации AVIF: {str(e)}'}), 500
    # Конвертация HEIC/HEIF в JPG, если нужно
    if ext in ('.heic', '.heif'):
        try:
            with Image.open(temp_path) as img:
                rgb_img = img.convert('RGB')
                jpg_path = temp_path.rsplit('.', 1)[0] + '.jpg'
                rgb_img.save(jpg_path, 'JPEG', quality=95)
            os.remove(temp_path)
            temp_path = jpg_path
        except Exception as e:
            os.remove(temp_path)
            return jsonify({'error': f'Ошибка конвертации HEIC: {str(e)}'}), 500

    # Открываем и ресайзим изображение (до 800px по большей стороне)
    try:
        with Image.open(temp_path) as img:
            max_size = 800
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size))
                img.save(temp_path)
    except Exception as e:
        os.remove(temp_path)
        return jsonify({'error': f'Ошибка обработки изображения: {str(e)}'}), 500

    # Создаем копию файла для генерации PDF после анализа
    photo_path_for_pdf = os.path.join('uploads', f"kibbe_pdf_{int(time.time())}.jpg")
    import shutil
    shutil.copy2(temp_path, photo_path_for_pdf)
    print(f"[DEBUG] Создана копия файла для PDF: {photo_path_for_pdf}")

    # Кодируем изображение в base64
    try:
        with open(temp_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        os.remove(temp_path)
        return jsonify({'error': f'Ошибка чтения изображения: {str(e)}'}), 500

    # Удаляем временный файл
    os.remove(temp_path)

    # OpenAI API вызов (аналогично color_analysis)
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    kibbe_prompt = """
На этом изображении изображён человек. Опиши, какие вертикальные линии (рост, пропорции), горизонтальные линии (плечи, бёдра, талия), черты лица (форма, скулы, подбородок, губы, глаза) и особенности фигуры (грудь, талия, бёдра, руки, ноги) ты видишь. Не делай выводов о личности, просто опиши видимые особенности.

ЕСЛИ на фото только лицо и не видно тела, то в полях vertical_lines, horizontal_lines и body_features верни нейтральные формулировки: 'не выражены', 'нейтральные' или 'не определены'. Не используй формулировку 'недостаточно информации'.

ОСОБЕННО ВАЖНО: Оцени форму и размер губ, глаз и скул на фото. 

Для губ используй только одну из категорий:
- тонкие губы (узкие, почти не выделяются, едва заметные)
- средние губы (не слишком тонкие и не слишком полные, умеренные)
- полные губы (явно пухлые, объёмные, выделяются на лице)

Для глаз используй только одну из категорий:
- маленькие глаза (узкие, не выделяются)
- средние глаза (не слишком маленькие и не слишком большие)
- большие глаза (очень заметные, крупные, выделяются на лице; если глаза кажутся крупнее губ, носа или занимают заметную часть лица, всегда выбирай 'большие глаза'; если не можешь однозначно выбрать между 'средние' и 'большие', выбирай 'большие глаза', если они хоть немного выделяются на фоне других черт)

Для скул используй только одну из категорий:
- выраженные скулы (острые, угловатые, хорошо заметные, выступающие)
- средние скулы (умеренно выраженные, не слишком острые)
- мягкие скулы (округлые, не выраженные)

ВАЖНО: Выраженные скулы могут быть только у Драматика, Гамина и Натурала. Классик НЕ может иметь выраженные скулы.

Для подбородка используй только одну из категорий:
- четкий подбородок (острый, угловатый, хорошо очерченный)
- средний подбородок (умеренно очерченный)
- мягкий подбородок (округлый, не выраженный)

Всегда выбирай только одну категорию для каждого признака и указывай их явно в описании черт лица, например: "форма лица овальная, скулы выраженные, подбородок четкий, губы тонкие, глаза средние". Не используй промежуточные или неуверенные формулировки.

Верни ТОЛЬКО JSON-объект в формате:
{
  "vertical_lines": "описание вертикальных линий",
  "horizontal_lines": "описание горизонтальных линий",
  "face_features": "описание черт лица (обязательно укажи категорию губ, глаз, скул и подбородка)",
  "body_features": "описание особенностей фигуры",
  "description": "краткое описание внешности",
  "style_recommendations": "рекомендации по стилю, одежде, аксессуарам"
}
ВАЖНО:
1. Верни ТОЛЬКО JSON-объект, без пояснений и комментариев
2. Если не уверен, делай предположение и явно укажи это в поле (например: 'предположительно ...')
3. Всегда возвращай валидный JSON
"""

    max_retries = 8
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Ты — эксперт по описанию внешности. Всегда возвращай валидный JSON."},
                    {"role": "user", "content": [
                        {"type": "text", "text": kibbe_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ],
                max_tokens=500,
                temperature=0.3
            )
            result = response.choices[0].message.content.strip()
            print("\n[DEBUG] Raw OpenAI Kibbe response:\n", result)
            # Чистим markdown
            if result.startswith('```json'):
                result = result[7:]
            if result.startswith('```'):
                result = result[3:]
            if result.endswith('```'):
                result = result[:-3]
            result = result.strip()
            # Если ответ не похож на JSON, возвращаем ошибку с текстом ответа
            if not result.startswith('{'):
                return jsonify({'error': f'OpenAI отказался: {result}'}), 400
            data = json.loads(result)
            # Проверяем и заполняем поля по умолчанию
            for key in ["vertical_lines", "horizontal_lines", "face_features", "body_features", "description", "style_recommendations"]:
                if key not in data or not data[key]:
                    data[key] = "не определено"

            # Очищаем style_recommendations после первого запроса
            data['style_recommendations'] = ''
            # Второй запрос: определение типажа Кибби по описанию и росту
            kibbe_type_prompt = f"""
!!! ВАЖНО: Если в описании встречается фраза "глаза большие", Classic не может быть выбран НИ ПРИ КАКИХ УСЛОВИЯХ.

Ты — эксперт по типированию Kibbe. На основе описания и роста выбери только один из пяти типов: Gamin, Natural, Classic, Romantic, Dramatic.

КЛЮЧЕВЫЕ ХАРАКТЕРИСТИКИ ТИПАЖЕЙ:

DRAMATIC (Драматик):
- Высокий рост (170+ см)
- ТОНКИЕ ГУБЫ (узкие, почти не выделяются)
- ВЫРАЖЕННЫЕ СКУЛЫ (острые, угловатые)
- ЧЕТКИЙ ПОДБОРОДОК
- Длинные, прямые линии тела
- Угловатые черты лица
- Если рост 165+ см + тонкие губы + выраженные скулы = ДРАМАТИК

CLASSIC (Классик):
- Средний рост (163-172 см)
- СРЕДНИЕ ГУБЫ (не слишком тонкие и не слишком полные)
- СБАЛАНСИРОВАННЫЕ черты лица
- Пропорциональные формы
- НЕ может быть с большими глазами
- НЕ может быть с тонкими губами + выраженными скулами
- НЕ может быть с ВЫРАЖЕННЫМИ СКУЛАМИ (выраженные скулы только у Драматика, Гамина и Натурала)

GAMIN (Гамин):
- Низкий рост (до 165 см)
- БОЛЬШИЕ ГЛАЗА (выразительные, заметные)
- Мальчишеские черты
- Компактная фигура
- Динамичные линии

ROMANTIC (Романтик):
- Средний рост (160-168 см)
- ПОЛНЫЕ ГУБЫ (пухлые, объемные)
- БОЛЬШИЕ ГЛАЗА
- Мягкие, округлые черты
- Мягкие линии тела

NATURAL (Натурал):
- Высокий рост (168-183 см)
- Естественные черты
- Широкие плечи
- Расслабленные линии

ПРАВИЛА ПРИОРИТЕТА:
1. Если рост 165+ см + тонкие губы + выраженные скулы = ДРАМАТИК
2. Если глаза большие + губы полные + мягкие черты = РОМАНТИК
3. Если глаза большие + губы средние/тонкие = ГАМИН
4. Если все черты средние, сбалансированные = КЛАССИК
5. Если высокий рост + естественные черты = НАТУРАЛ

ВАЖНЫЕ ИСКЛЮЧЕНИЯ:
- КЛАССИК НЕ может иметь выраженные скулы (выраженные скулы только у Драматика, Гамина и Натурала)
- Если обнаружены выраженные скулы, Классик автоматически исключается

УЧИТЫВАЙ РОСТ:
- Гамин — до 165 см
- Классик — 163–172 см
- Натурал — 168–183 см
- Драматик — 170 см и выше
- Романтик — 160–168 см

ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА:
- Если черты лица как у классика, но рост 176+ см — это не может быть классик, а скорее натурал или драматик
- Если черты лица как у гамина, но рост 176+ см — это не может быть гамин, а это драматик
- Если черты лица как у романтика, но рост 176+ см — это не может быть романтик, а это натурал
- Драматик не может быть ростом ниже 170 см, даже если черты определяются как драматик. Это скорее гамин

Рост пользователя: {user_height if user_height else 'неизвестен'} см
Описание: {data['face_features']}

Верни ТОЛЬКО название типа на русском языке, без кавычек и дополнительного текста.
"""
            kibbe_type = "не определено"
            try:
                type_response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Ты — эксперт по типажам Кибби. Отвечай только названием типа."},
                        {"role": "user", "content": kibbe_type_prompt}
                    ],
                    max_tokens=100,
                    temperature=0.1
                )
                kibbe_type_raw = type_response.choices[0].message.content.strip()
                print("[DEBUG] Kibbe type raw response:", kibbe_type_raw)
                
                # Простая обработка - убираем лишнее и нормализуем
                kibbe_type_clean = kibbe_type_raw.strip().strip('"').strip("'")
                
                # Нормализация типа по ключевым словам
                type_map = {
                    'драматик': 'Драматик',
                    'dramatic': 'Драматик',
                    'натурал': 'Натурал',
                    'natural': 'Натурал',
                    'гамин': 'Гамин',
                    'gamin': 'Гамин',
                    'романтик': 'Романтик',
                    'romantic': 'Романтик',
                    'классик': 'Классик',
                    'classic': 'Классик'
                }
                
                kibbe_type_norm = kibbe_type_clean.lower()
                for key, val in type_map.items():
                    if key in kibbe_type_norm:
                        kibbe_type = val
                        break
                else:
                    kibbe_type = 'Классик'
                data["kibbe_type_external"] = kibbe_type  # Сохраняем "сырой" типаж по внешности+росту

                # --- УЧЁТ РОСТА И КЛЮЧЕВЫХ ХАРАКТЕРИСТИК ---
                # Диапазоны роста для типажей
                height_refs = {
                    'Гамин':    (0, 165),
                    'Классик':  (163, 172),
                    'Натурал':  (168, 183),
                    'Драматик': (170, 250),
                    'Романтик': (160, 168)
                }
                
                # Баллы по внешности+росту
                scores = {k: 0 for k in height_refs}
                if kibbe_type in scores:
                    scores[kibbe_type] += 0.5  # 50% вес внешности+роста (от OpenAI)
                
                # Баллы по росту
                if user_height:
                    for t, (h_min, h_max) in height_refs.items():
                        if h_min <= user_height <= h_max:
                            scores[t] += 0.3  # 30% вес роста
                
                # ДОПОЛНИТЕЛЬНЫЕ БАЛЛЫ за ключевые характеристики
                face_features_lower = data['face_features'].lower()
                
                # Проверяем характеристики для Dramatic
                if user_height and user_height >= 165:
                    dramatic_features = 0
                    if 'тонкие губы' in face_features_lower:
                        dramatic_features += 1
                    if 'выраженные скулы' in face_features_lower:
                        dramatic_features += 1
                    if 'четкий подбородок' in face_features_lower:
                        dramatic_features += 1
                    
                    # Если есть хотя бы 2 из 3 ключевых характеристик Dramatic
                    if dramatic_features >= 2:
                        scores['Драматик'] += 0.2  # +20% за ключевые характеристики
                        print(f"[DEBUG] Найдены ключевые характеристики Dramatic: {dramatic_features}/3 признаков + рост {user_height} см")
                
                # Проверяем характеристики для Classic
                if 'средние губы' in face_features_lower and 'сбалансированные' in face_features_lower:
                    scores['Классик'] += 0.1  # +10% за сбалансированность
                
                # ВАЖНО: Классик НЕ может иметь выраженные скулы
                if 'выраженные скулы' in face_features_lower:
                    scores['Классик'] = 0  # Полностью исключаем Классика
                    print(f"[DEBUG] Выраженные скулы обнаружены - Классик исключен")
                
                # Проверяем характеристики для Gamin
                if 'большие глаза' in face_features_lower and user_height and user_height <= 165:
                    scores['Гамин'] += 0.2  # +20% за большие глаза + низкий рост
                
                # Проверяем характеристики для Romantic
                if 'полные губы' in face_features_lower and 'большие глаза' in face_features_lower:
                    scores['Романтик'] += 0.2  # +20% за полные губы + большие глаза
                
                # Итоговый типаж — максимальный балл
                final_type = max(scores, key=lambda k: scores[k])
                
                # Финальная проверка: если у Классика выраженные скулы, выбираем следующий по баллам тип
                if final_type == 'Классик' and 'выраженные скулы' in face_features_lower:
                    print(f"[DEBUG] Классик выбран, но обнаружены выраженные скулы - ищем альтернативу")
                    # Убираем Классика из рассмотрения
                    scores_copy = scores.copy()
                    scores_copy['Классик'] = 0
                    # Выбираем следующий по баллам тип
                    final_type = max(scores_copy, key=lambda k: scores_copy[k])
                    print(f"[DEBUG] Альтернативный тип выбран: {final_type}")
                
                data["kibbe_type"] = final_type
                
                print(f"[DEBUG] Итоговые баллы: {scores}")
                print(f"[DEBUG] Выбранный типаж: {final_type}")
                # --- END УЧЁТ РОСТА И КЛЮЧЕВЫХ ХАРАКТЕРИСТИК ---

                # Третий запрос: рекомендации по стилю для определённого типажа
                style_recommendations_prompt = f"""
Ты — эксперт по стилю и типажам Кибби. Дай конкретные рекомендации по стилю для типажа {final_type}.

ТИПАЖ: {final_type}

Дай рекомендации по:
1. Фасонам одежды (силуэты, крои)
2. Тканям и фактурам
3. Принтам и узорам
4. Аксессуарам

ВАЖНО:
- НЕ используй фразы типа "Конечно!", "Вот рекомендации:" и т.п.
- Начинай сразу с рекомендаций
- Используй обычные заголовки: "Фасоны одежды", "Ткани", "Принты", "Аксессуары" (без ### и без **)
- Пиши простым языком, без технических терминов
- Делай рекомендации практичными и конкретными
"""

                try:
                    style_response = openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "Ты — эксперт по стилю. Дай практичные рекомендации без лишних вступлений."},
                            {"role": "user", "content": style_recommendations_prompt}
                        ],
                        max_tokens=600,
                        temperature=0.7
                    )
                    style_recommendations = style_response.choices[0].message.content.strip()
                    
                    # Проверяем, не обрезался ли ответ (если заканчивается на середине предложения)
                    if style_recommendations and not style_recommendations.endswith(('.', '!', ':', ';')):
                        print("[DEBUG] Рекомендации обрезались, пытаемся получить полный ответ...")
                        # Пробуем ещё раз с большим лимитом
                        try:
                            style_response_full = openai_client.chat.completions.create(
                                model="gpt-4o",
                                messages=[
                                    {"role": "system", "content": "Ты — эксперт по стилю. Дай практичные рекомендации без лишних вступлений."},
                                    {"role": "user", "content": style_recommendations_prompt}
                                ],
                                max_tokens=800,
                                temperature=0.7
                            )
                            style_recommendations = style_response_full.choices[0].message.content.strip()
                        except Exception as e2:
                            print(f"[DEBUG] Вторая попытка получения рекомендаций не удалась: {str(e2)}")
                    
                    # Очищаем от лишних фраз в начале
                    unwanted_starters = [
                        "Конечно!",
                        "Вот рекомендации:",
                        "Конечно! Вот практичные рекомендации",
                        "Вот практичные рекомендации",
                        "Рекомендации по стилю:",
                        "Для типажа",
                        "Типаж"
                    ]
                    
                    for starter in unwanted_starters:
                        if style_recommendations.startswith(starter):
                            style_recommendations = style_recommendations[len(starter):].strip()
                            break
                    
                    # Убираем лишние пробелы и переносы в начале
                    style_recommendations = style_recommendations.lstrip()
                    
                    data["style_recommendations"] = style_recommendations
                except Exception as e:
                    print("[DEBUG] Ошибка при генерации рекомендаций:", str(e))
                    data["style_recommendations"] = "Рекомендации временно недоступны"
            except Exception as e:
                print("[DEBUG] Ошибка при определении типажа Кибби:", str(e))
                data["kibbe_type_external"] = "Классик"
            
            # Сохраняем данные в сессии для последующей отправки гайда
            session['last_kibbe_analysis'] = data
            session['last_kibbe_image_path'] = photo_path_for_pdf
            
            # ОТКЛЮЧАЕМ АВТОМАТИЧЕСКУЮ ОТПРАВКУ - гайд будет отправляться только после оплаты
            print(f"[analyze_kibbe] АВТОМАТИЧЕСКАЯ ОТПРАВКА ОТКЛЮЧЕНА")
            print(f"[analyze_kibbe] Гайд будет отправлен только после оплаты")
            data['guide_sent'] = False
            data['message'] = 'Для получения гайда необходимо оплатить'
            
            return jsonify(data)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return jsonify({'error': f'Ошибка анализа: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)