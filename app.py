from flask import Flask, request, jsonify, render_template, send_file, session, redirect
from flask_session import Session
import os
from werkzeug.utils import secure_filename
from color_analysis import ColorAnalyzer
from pdf_report import generate_pdf_report, generate_kibbe_pdf
import cv2
import json
from config import CLOUDPAYMENTS_PUBLIC_ID, UNISENDER_API_KEY, UNISENDER_LIST_ID, UNISENDER_GO_API_KEY, OPENAI_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SHEET_RANGE, GOOGLE_SHEET_WORKSHEET, GOOGLE_SHEET_KIBBE_WORKSHEET, GOOGLE_SHEET_SUBSCRIPTION_WORKSHEET, GOOGLE_SERVICE_ACCOUNT_FILE, SUBSCRIPTION_PRICE, SUBSCRIPTION_PRICE_SPECIAL, COLOR_GUIDE_PRICE, KIBBE_GUIDE_PRICE
import requests
import random
import string
from datetime import datetime, timedelta
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
from auth import (
    check_subscription, 
    login_required, 
    subscription_required, 
    rate_limit_check, 
    record_login_attempt,
    normalize_email
)
from user_auth import user_auth
from pymongo import MongoClient
import mongo_config

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
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25MB max-limit
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key')

# Настройки для session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SECURE'] = False  # Временно False для отладки
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_DOMAIN'] = None  # Для всех доменов
app.config['SESSION_COOKIE_PATH'] = '/'

# Инициализация Flask-Session
Session(app)

# Добавляем заголовки для предотвращения кэширования
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

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

# Создаем директорию для сессий Flask
session_dir = 'flask_session'
os.makedirs(session_dir, exist_ok=True)

# Подключаемся к MongoDB при запуске приложения
logger.info("Подключение к MongoDB...")
if user_auth.connect():
    logger.info("✅ MongoDB подключена успешно")
else:
    logger.warning("⚠️ Не удалось подключиться к MongoDB")

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
    return render_template('index.html', config={
        'CLOUDPAYMENTS_PUBLIC_ID': CLOUDPAYMENTS_PUBLIC_ID,
        'SUBSCRIPTION_PRICE': SUBSCRIPTION_PRICE,
        'COLOR_GUIDE_PRICE': COLOR_GUIDE_PRICE,
        'KIBBE_GUIDE_PRICE': KIBBE_GUIDE_PRICE
    })

@app.route('/payment-success')
def payment_success():
    # Получаем тип покупки и email из параметров URL
    purchase_type = request.args.get('type', '')
    user_email = request.args.get('email', '')
    return render_template('payment_success.html', purchase_type=purchase_type, user_email=user_email)

@app.route('/analyze', methods=['POST', 'GET'])
def analyze():
    print("=== DEBUG: Запрос получен ===")
    logger.info("=== НАЧАЛО ЗАПРОСА /analyze ===")
    
    # Убеждаемся, что подключение к MongoDB активно
    if not user_auth.db or not user_auth.pre_subscriptions_collection:
        logger.warning("MongoDB не подключена, пытаемся переподключиться...")
        if not user_auth.connect():
            logger.error("Не удалось подключиться к MongoDB")
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
    logger.info(f"Метод запроса: {request.method}")
    logger.info(f"Заголовки запроса: {dict(request.headers)}")
    logger.info(f"Форма запроса: {request.form}")
    logger.info(f"Файлы в запросе: {request.files}")
    logger.info(f"Content-Length заголовок: {request.headers.get('Content-Length', 'НЕ УСТАНОВЛЕН')}")
    logger.info(f"Content-Type заголовок: {request.headers.get('Content-Type', 'НЕ УСТАНОВЛЕН')}")
    logger.info(f"FLASK_MAX_CONTENT_LENGTH из окружения: {os.environ.get('FLASK_MAX_CONTENT_LENGTH', 'НЕ УСТАНОВЛЕН')}")
    logger.info(f"app.config['MAX_CONTENT_LENGTH']: {app.config.get('MAX_CONTENT_LENGTH', 'НЕ УСТАНОВЛЕН')}")
    
    if 'image' not in request.files:
        logger.warning("Файл изображения не найден в запросе")
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['image']
    if file.filename == '':
        logger.warning("Имя файла пустое")
        return jsonify({'error': 'No selected file'}), 400
    
    logger.info(f"Получен файл: {file.filename}")
    logger.info(f"Тип файла: {file.content_type}")
    
    # Проверяем размер файла
    file_content = file.read()
    file_size = len(file_content)
    logger.info(f"Размер файла: {file_size} байт")
    file.seek(0)  # Возвращаем указатель в начало файла
    
    # Проверяем, является ли файл HEIC
    is_heic = file.filename.lower().endswith(('.heic', '.heif'))
    logger.info(f"Файл HEIC/HEIF: {is_heic}")
    
    # Проверяем размер файла (максимум 20MB)
    max_file_size = 20 * 1024 * 1024  # 20MB
    logger.info(f"Размер файла: {file_size} байт ({file_size/1024/1024:.2f} MB)")
    logger.info(f"Максимальный размер файла: {max_file_size} байт ({max_file_size/1024/1024:.2f} MB)")
    logger.info(f"Файл превышает лимит: {file_size > max_file_size}")
    logger.info(f"FLASK_MAX_CONTENT_LENGTH из окружения: {os.environ.get('FLASK_MAX_CONTENT_LENGTH', 'НЕ УСТАНОВЛЕН')}")
    logger.info(f"app.config['MAX_CONTENT_LENGTH']: {app.config.get('MAX_CONTENT_LENGTH', 'НЕ УСТАНОВЛЕН')}")
    
    if file_size > max_file_size:
        logger.warning(f"Файл слишком большой: {file_size} байт ({file_size/1024/1024:.2f} MB)")
        logger.warning(f"Максимальный размер: {max_file_size} байт ({max_file_size/1024/1024:.2f} MB)")
        return jsonify({'error': 'Файл слишком большой. Максимальный размер: 20MB. Попробуйте уменьшить размер изображения.'}), 413
    
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
        logger.info(f"Размер файла: {file_size} байт")
        
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
    # Убеждаемся, что подключение к MongoDB активно
    if not user_auth.db or not user_auth.pre_subscriptions_collection:
        logger.warning("MongoDB не подключена, пытаемся переподключиться...")
        if not user_auth.connect():
            logger.error("Не удалось подключиться к MongoDB")
            return False
    
    # Проверяем, купил ли пользователь гайд
    if not user_auth.can_send_guide(email, "color_guide"):
        print(f"❌ Попытка отправить цветовой гайд без покупки: {email}")
        return False
    
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
                    "Вы также можете оформить <b><a href=\"https://ai.stylebox.live/oto?utm_source=emai_guide\" style=\"color:#bb279b;\">подписку на ИИ-стилиста</a></b> с дополнительной скидкой 500 руб., т.к. вы купили персональный гайд.<br>"
                    "Итого, для вас ИИ-стилист на целый год будет стоить <b>4490 руб.<br><br>"
                    "С уважением,<br>"
                    "Style Box AI<br><br>"
                    "<a href=\"https://noreply.stylebox.live/ru/go2_unsubscribe\" style=\"color:#7C3AED;\">Отписаться от рассылки</a>"
                    "</p></body></html>"
                ),
                "plaintext": "Здравствуйте! Спасибо за приобретение персонального цветового гайда. Ссылка на ваш гайд: {pdf_url}\n\nВы также можете оформить подписку на ИИ-стилиста со скидкой 500 руб. по ссылке: https://ai.stylebox.live/oto?utm_source=emai_guide\nИтого, для вас ИИ-стилист на целый год будет стоить 4490 руб.".format(pdf_url=pdf_url)
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
            # Помечаем гайд как отправленный
            user_auth.mark_guide_sent(email, "color_guide", pdf_path)
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
    # Убеждаемся, что подключение к MongoDB активно
    if not user_auth.db or not user_auth.pre_subscriptions_collection:
        logger.warning("MongoDB не подключена, пытаемся переподключиться...")
        if not user_auth.connect():
            logger.error("Не удалось подключиться к MongoDB")
            return False
    
    # Проверяем, купил ли пользователь гайд
    if not user_auth.can_send_guide(email, "kibbe_guide"):
        print(f"❌ Попытка отправить гайд по типажу без покупки: {email}")
        return False
    
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
                    "Вы также можете оформить <b><a href=\"https://ai.stylebox.live/oto?utm_source=emai_guide\" style=\"color:#bb279b;\">подписку на ИИ-стилиста</a></b> с дополнительной скидкой 500 руб., т.к. вы купили персональный гайд.<br>"
                    "Итого, для вас ИИ-стилист на целый год будет стоить <b>4490 руб.<br><br>"
                    "С уважением,<br>"
                    "Style Box AI<br><br>"
                    "<a href=\"https://noreply.stylebox.live/ru/go2_unsubscribe\" style=\"color:#7C3AED;\">Отписаться от рассылки</a>"
                    "</p></body></html>"
                ),
                "plaintext": "Здравствуйте! Спасибо за приобретение персонального гайда по стилю. Ссылка на ваш гайд: {pdf_url}\n\nВы также можете оформить подписку на ИИ-стилиста со скидкой 500 руб. по ссылке: https://ai.stylebox.live/oto?utm_source=emai_guide\nИтого, для вас ИИ-стилист на целый год будет стоить 4490 руб.".format(pdf_url=pdf_url)
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
            # Помечаем гайд как отправленный
            user_auth.mark_guide_sent(email, "kibbe_guide", pdf_path)
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

def send_password_reset_email(email, reset_url):
    """Отправляет email для восстановления пароля через Unisender Go"""
    api_key = UNISENDER_GO_API_KEY
    api_url = "https://go2.unisender.ru/ru/transactional/api/v1/email/send.json"
    from_email = 'info@stylebox.live'
    to_email = email

    payload = {
        "api_key": api_key,
        "message": {
            "recipients": [
                {"email": to_email}
            ],
            "from_email": from_email,
            "from_name": "Style Box AI",
            "subject": "Восстановление пароля",
            "body": {
                "html": (
                    "<html><body>"
                    "<p>Здравствуйте!<br><br>"
                    "Вы запросили восстановление пароля для вашего аккаунта в Style Box AI.<br><br>"
                    "Для восстановления пароля перейдите по ссылке:<br>"
                    f"<a href=\"{reset_url}\" style=\"background-color: #bb279b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; margin: 20px 0;\">Восстановить пароль</a><br><br>"
                    "Ссылка действительна в течение 24 часов.<br><br>"
                    "Если вы не запрашивали восстановление пароля, просто проигнорируйте это письмо.<br><br>"
                    "С уважением,<br>"
                    "Style Box AI<br><br>"
                    "<a href=\"https://noreply.stylebox.live/ru/go2_unsubscribe\" style=\"color:#7C3AED;\">Отписаться от рассылки</a>"
                    "</p></body></html>"
                ),
                "plaintext": f"Здравствуйте! Вы запросили восстановление пароля для вашего аккаунта в Style Box AI. Для восстановления пароля перейдите по ссылке: {reset_url} Ссылка действительна в течение 24 часов. Если вы не запрашивали восстановление пароля, просто проигнорируйте это письмо. С уважением, Style Box AI"
            }
        }
    }

    print("Отправка письма для восстановления пароля через Unisender Go Transactional API...")
    print(f"API URL: {api_url}")
    print(f"From: {from_email}")
    print(f"To: {to_email}")
    print(f"Reset URL: {reset_url}")

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
            print("Письмо для восстановления пароля отправлено через Unisender Go Transactional API!")
            return True
        else:
            print(f"Ошибка отправки письма для восстановления пароля: {response.text}")
            return False
    except requests.exceptions.SSLError as e:
        print(f"SSL ошибка: {str(e)}")
        return False
    except Exception as e:
        print(f"Ошибка при отправке письма для восстановления пароля: {str(e)}")
        return False

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
    print("[DEBUG] ===== WEBHOOK RECEIVED =====")
    print("[DEBUG] Request method:", request.method)
    print("[DEBUG] Request URL:", request.url)
    print("[DEBUG] Request headers:", dict(request.headers))
    print("[DEBUG] Request form data:", dict(request.form))
    print("[DEBUG] Content-Type:", request.headers.get('Content-Type'))
    
    # Безопасно получаем JSON данные
    try:
        json_data = request.get_json()
        print("[DEBUG] Request JSON:", json_data)
    except Exception as e:
        print("[DEBUG] Error getting JSON data:", str(e))
        print("[DEBUG] Request JSON: None (form-data only)")
    print("[DEBUG] ==============================")
    
    data = request.form if request.form else request.get_json()
    print("[DEBUG] ===== DATA PROCESSING =====")
    print("[DEBUG] Data type: form" if request.form else "Data type: JSON")
    print("[DEBUG] Raw data:", dict(data))
    print("[DEBUG] =========================")
    
    print("[DEBUG] Step 1: Starting data processing...")
    try:
        print("[DEBUG] Step 2: Extracting status and email...")
        status = str(data.get('Status', '')).lower()
        email = data.get('Email')
        print("[DEBUG] Status:", status)
        print("[DEBUG] Email:", email)
        
        print("[DEBUG] Step 3: Parsing Data field...")
        # Получаем Data и парсим его как JSON
        data_json = {}
        if data.get('Data'):
            try:
                data_json = json.loads(data.get('Data'))
                print("[DEBUG] Parsed Data JSON:", data_json)
            except Exception as e:
                print("[DEBUG] Error parsing Data JSON:", e)
                data_json = {}
        else:
            print("[DEBUG] No Data field found")
        
        print("[DEBUG] Step 4: Analyzing purchase type...")
        print("[DEBUG] ===== PURCHASE TYPE ANALYSIS =====")
        description = data.get('Description', '').lower()
        print("[DEBUG] Description:", description)
        
        # Определяем тип покупки
        payment_type = data_json.get('type', '')
        print("[DEBUG] Payment type:", payment_type)
        
        # Проверяем, является ли это подпиской
        is_subscription = (
            'подписка' in description or 
            'предзаказ' in description or
            payment_type == 'subscription'
        )
        
        # Проверяем, является ли это гайдом
        is_color_guide = (
            'цветовой' in description or 
            'color' in description or
            payment_type == 'color_guide'
        )
        
        is_kibbe_guide = (
            'типаж' in description or 
            'kibbe' in description or
            payment_type == 'kibbe_guide'
        )
        
        print("[DEBUG] Is subscription:", is_subscription)
        print("[DEBUG] Is color guide:", is_color_guide)
        print("[DEBUG] Is kibbe guide:", is_kibbe_guide)
        print("[DEBUG] =================================")
        
        print("[DEBUG] Step 5: Checking payment status...")
        if status == 'completed' and email:
            print("[DEBUG] ===== PROCESSING PAYMENT =====")
            print("[DEBUG] Email:", email)
            
            # Подключаемся к MongoDB
            if not user_auth.connect():
                print("[DEBUG] Failed to connect to MongoDB")
                return jsonify({'code': 15, 'message': 'Database connection failed'}), 500
            print("[DEBUG] MongoDB connected successfully")
            
            if is_subscription:
                print("[DEBUG] Step 6: Processing subscription...")
                try:
                    print("[DEBUG] Step 6.1: Setting up subscription end date...")
                    # Добавляем подписку на 1 год
                    from datetime import datetime, timedelta
                    subscription_end = datetime.utcnow() + timedelta(days=365)
                    print("[DEBUG] Subscription end date:", subscription_end)
                    
                    print("[DEBUG] Step 6.2: Adding subscription to database...")
                    result = user_auth.add_pre_subscription(
                        email=email,
                        subscription_end=subscription_end,
                        source="payment",
                        notes=f"CloudPayments payment - {data.get('TransactionId', 'N/A')}",
                        product_type="subscription"
                    )
                    print("[DEBUG] ✅ Subscription added successfully for", email)
                    return jsonify({"code": 0, "message": "Subscription added successfully"})
                except Exception as e:
                    print("[DEBUG] ❌ Error adding subscription:", str(e))
                    return jsonify({"code": 16, "message": f"Failed to add subscription: {str(e)}"})
            
            elif is_color_guide:
                print("[DEBUG] Step 6: Processing color guide purchase...")
                try:
                    print("[DEBUG] Step 6.1: Adding color guide purchase to database...")
                    amount = float(data.get('Amount', COLOR_GUIDE_PRICE))
                    transaction_id = data.get('TransactionId', 'N/A')
                    
                    result = user_auth.add_guide_purchase(
                        email=email,
                        product_type="color_guide",
                        amount=amount,
                        transaction_id=transaction_id,
                        source="cloudpayments",
                        notes=f"CloudPayments payment - {transaction_id}"
                    )
                    print("[DEBUG] ✅ Color guide purchase added successfully for", email)
                    return jsonify({"code": 0, "message": "Color guide purchase added successfully"})
                except Exception as e:
                    print("[DEBUG] ❌ Error adding color guide purchase:", str(e))
                    return jsonify({"code": 17, "message": f"Failed to add color guide purchase: {str(e)}"})
            
            elif is_kibbe_guide:
                print("[DEBUG] Step 6: Processing kibbe guide purchase...")
                try:
                    print("[DEBUG] Step 6.1: Adding kibbe guide purchase to database...")
                    amount = float(data.get('Amount', KIBBE_GUIDE_PRICE))
                    transaction_id = data.get('TransactionId', 'N/A')
                    
                    result = user_auth.add_guide_purchase(
                        email=email,
                        product_type="kibbe_guide",
                        amount=amount,
                        transaction_id=transaction_id,
                        source="cloudpayments",
                        notes=f"CloudPayments payment - {transaction_id}"
                    )
                    print("[DEBUG] ✅ Kibbe guide purchase added successfully for", email)
                    return jsonify({"code": 0, "message": "Kibbe guide purchase added successfully"})
                except Exception as e:
                    print("[DEBUG] ❌ Error adding kibbe guide purchase:", str(e))
                    return jsonify({"code": 18, "message": f"Failed to add kibbe guide purchase: {str(e)}"})
            
            else:
                print("[DEBUG] Not a recognized payment type")
                return jsonify({"code": 0, "message": "Payment processed successfully"})
        else:
            print("[DEBUG] Invalid status or email")
            return jsonify({"code": 1, "message": "Invalid payment data"})
            
    except Exception as e:
        print("[DEBUG] ❌ CRITICAL ERROR in data processing:", str(e))
        import traceback
        print("[DEBUG] Traceback:", traceback.format_exc())
        return jsonify({"code": 99, "message": f"Internal error: {str(e)}"})

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
    return render_template('oto.html', config={
        'CLOUDPAYMENTS_PUBLIC_ID': CLOUDPAYMENTS_PUBLIC_ID,
        'SUBSCRIPTION_PRICE_SPECIAL': SUBSCRIPTION_PRICE_SPECIAL,
        'COLOR_GUIDE_PRICE': COLOR_GUIDE_PRICE,
        'KIBBE_GUIDE_PRICE': KIBBE_GUIDE_PRICE
    })

@app.route('/kibbe')
def kibbe_page():
    return render_template('kibbe.html')

# Маршруты для авторизации
@app.route('/check_auth', methods=['GET'])
def check_auth():
    """Проверка статуса авторизации"""
    print("[DEBUG] ===== CHECK AUTH =====")
    print("[DEBUG] Session keys:", list(session.keys()))
    print("[DEBUG] Session ID from session:", session.get('session_id'))
    print("[DEBUG] Session permanent:", session.permanent)
    
    session_id = session.get('session_id')
    if session_id:
        print("[DEBUG] Session ID found, checking user...")
        user = user_auth.get_user_by_session(session_id)
        if user:
            print("[DEBUG] User found:", user.get('email'))
            subscription_active = user_auth.check_subscription(str(user['_id']))
            print("[DEBUG] Subscription active:", subscription_active)
            return jsonify({
                'authenticated': True,
                'email': user['email'],
                'username': user['username'],
                'subscription_active': subscription_active,
                'profile': user.get('profile', {})
            })
        else:
            print("[DEBUG] User not found for session_id:", session_id)
    else:
        print("[DEBUG] No session_id in session")
    
    print("[DEBUG] Returning unauthenticated response")
    return jsonify({
        'authenticated': False,
        'subscription_active': False
    })

@app.route('/register', methods=['POST'])
def register():
    """Регистрация нового пользователя"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        username = data.get('username', '').strip()
        
        if not email or not password:
            return jsonify({'error': 'Email и пароль обязательны'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Пароль должен содержать минимум 6 символов'}), 400
        
        # Если username не предоставлен, генерируем его из email
        if not username:
            username = email.split('@')[0]  # Берем часть до @
        
        # Подключаемся к MongoDB
        if not user_auth.connect():
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
        
        # Регистрируем пользователя
        result = user_auth.register_user(email, password, username)
        
        if result['success']:
            logger.info(f"Новый пользователь зарегистрирован: {email}")
            return jsonify({
                'success': True,
                'message': 'Регистрация успешна! Теперь вы можете войти в систему.'
            })
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        logger.error(f"Ошибка регистрации: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/login', methods=['GET'])
def login_page():
    """Страница входа - перенаправляем на главную"""
    return redirect('/')

@app.route('/login', methods=['POST'])
def login():
    """Авторизация пользователя по email и паролю"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return jsonify({'error': 'Email и пароль обязательны'}), 400
        
        # Проверяем rate limiting (временно отключено)
        # rate_ok, rate_message = rate_limit_check()
        # if not rate_ok:
        #     return jsonify({'error': rate_message}), 429
        
        # Подключаемся к MongoDB
        if not user_auth.connect():
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
        
        # Аутентифицируем пользователя
        result = user_auth.authenticate_user(email, password)
        
        if result['success']:
            # Сохраняем session_id в сессии Flask
            session['session_id'] = result['session_id']
            session.permanent = True  # Делаем сессию постоянной
            logger.info(f"🔑 Session ID сохранен в Flask session: {result['session_id']}")
            logger.info(f"🔑 Session permanent: {session.permanent}")
            logger.info(f"🔑 Session keys: {list(session.keys())}")
            logger.info(f"🔑 Session ID после сохранения: {session.get('session_id')}")
            logger.info(f"🔑 Session modified: {session.modified}")
            # record_login_attempt(success=True)  # Временно отключено
            
            logger.info(f"Успешная авторизация: {email}")
            return jsonify({
                'success': True,
                'message': 'Авторизация успешна',
                'user': result['user']
            })
        else:
            # record_login_attempt(success=False)  # Временно отключено
            return jsonify({'error': result['error']}), 401
            
    except Exception as e:
        logger.error(f"Ошибка авторизации: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/logout', methods=['POST'])
def logout():
    """Выход пользователя"""
    try:
        session_id = session.get('session_id')
        if session_id:
            user_auth.logout_user(session_id)
        
        session.pop('session_id', None)
        return jsonify({'success': True, 'message': 'Выход выполнен'})
        
    except Exception as e:
        logger.error(f"Ошибка выхода: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    """Запрос на восстановление пароля"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        
        if not email:
            return jsonify({'error': 'Email обязателен'}), 400
        
        # Подключаемся к MongoDB
        if not user_auth.connect():
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
        
        # Создаем токен для сброса пароля
        result = user_auth.create_password_reset_token(email)
        
        if result['success']:
            # Формируем URL для сброса пароля
            reset_url = request.host_url.rstrip('/') + f'/reset_password?token={result["token"]}'
            
            # Отправляем email
            if send_password_reset_email(email, reset_url):
                logger.info(f"Email для восстановления пароля отправлен: {email}")
                return jsonify({
                    'success': True,
                    'message': 'Инструкции по восстановлению пароля отправлены на ваш email'
                })
            else:
                return jsonify({'error': 'Ошибка отправки email'}), 500
        else:
            return jsonify({'error': result['error']}), 400
        
    except Exception as e:
        logger.error(f"Ошибка запроса восстановления пароля: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    """Страница сброса пароля"""
    if request.method == 'GET':
        token = request.args.get('token')
        if not token:
            return jsonify({'error': 'Токен не указан'}), 400
        
        # Проверяем токен
        if not user_auth.connect():
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
        
        token_result = user_auth.verify_password_reset_token(token)
        if not token_result['success']:
            return jsonify({'error': token_result['error']}), 400
        
        # Возвращаем HTML страницу для сброса пароля
        return render_template('reset_password.html', token=token)
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            token = data.get('token')
            new_password = data.get('password')
            
            if not token or not new_password:
                return jsonify({'error': 'Токен и новый пароль обязательны'}), 400
            
            if len(new_password) < 6:
                return jsonify({'error': 'Пароль должен содержать минимум 6 символов'}), 400
            
            # Подключаемся к MongoDB
            if not user_auth.connect():
                return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
            
            # Сбрасываем пароль
            result = user_auth.reset_password(token, new_password)
            
            if result['success']:
                logger.info(f"Пароль успешно сброшен")
                return jsonify({
                    'success': True,
                    'message': 'Пароль успешно изменен. Теперь вы можете войти в систему.'
                })
            else:
                return jsonify({'error': result['error']}), 400
                
        except Exception as e:
            logger.error(f"Ошибка сброса пароля: {str(e)}")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/profile')
@login_required
def profile():
    """Страница профиля пользователя"""
    try:
        session_id = session.get('session_id')
        user = user_auth.get_user_by_session(session_id)
        
        if not user:
            return redirect('/')
        
        # Получаем данные анкеты из профиля
        profile_data = user.get('profile', {})
        survey_data = profile_data.get('survey_data', {})
        
        # Проверяем подписку через pre_subscriptions
        subscription_active = user_auth.check_subscription(str(user['_id']))
        
        # Получаем информацию о подписке
        subscription_info = None
        if subscription_active:
            pre_sub_result = user_auth.get_pre_subscription(user.get('email', ''))
            if pre_sub_result['success']:
                subscription_info = pre_sub_result['subscription']
        
        from datetime import datetime
        
        return render_template('profile.html', 
                             user=user, 
                             survey_data=survey_data,
                             subscription_active=subscription_active,
                             subscription_info=subscription_info,
                             now=datetime.utcnow())
        
    except Exception as e:
        logger.error(f"Ошибка загрузки профиля: {str(e)}")
        return redirect('/')

@app.route('/save_profile_survey', methods=['POST'])
@login_required
def save_profile_survey():
    """Сохраняет анкету в профиле пользователя"""
    try:
        session_id = session.get('session_id')
        user = user_auth.get_user_by_session(session_id)
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        user_id = str(user['_id'])
        data = request.get_json()
        
        if not data or 'survey_data' not in data:
            return jsonify({'success': False, 'error': 'Данные анкеты не предоставлены'}), 400
        
        survey_data = data['survey_data']
        
        # Сохраняем в профиле пользователя
        profile_data = {
            'survey_data': survey_data,
            'survey_completed_at': datetime.utcnow().isoformat(),
            'survey_version': '1.0'
        }
        
        success = user_auth.update_user_profile(user_id, profile_data)
        
        if success:
            logger.info(f"Анкета сохранена в профиле пользователя {user_id}")
            return jsonify({'success': True, 'message': 'Анкета успешно сохранена в профиле'})
        else:
            return jsonify({'success': False, 'error': 'Ошибка сохранения анкеты'}), 500
        
    except Exception as e:
        logger.error(f"Ошибка сохранения анкеты в профиле: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_profile_survey')
@login_required
def get_profile_survey():
    """Получает данные анкеты из профиля пользователя"""
    try:
        session_id = session.get('session_id')
        user = user_auth.get_user_by_session(session_id)
        
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        profile_data = user.get('profile', {})
        survey_data = profile_data.get('survey_data', {})
        
        return jsonify({
            'success': True,
            'survey_data': survey_data,
            'has_survey': bool(survey_data),
            'completed_at': profile_data.get('survey_completed_at')
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения анкеты из профиля: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/profile', methods=['PUT'])
@login_required
def update_profile():
    """Обновление профиля пользователя"""
    try:
        data = request.get_json()
        user = request.current_user
        
        # Обновляем профиль
        success = user_auth.update_user_profile(user['_id'], data)
        
        if success:
            return jsonify({'success': True, 'message': 'Профиль обновлен'})
        else:
            return jsonify({'error': 'Ошибка обновления профиля'}), 500
            
    except Exception as e:
        logger.error(f"Ошибка обновления профиля: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/analyze_kibbe', methods=['POST'])
def analyze_kibbe():
    # Убеждаемся, что подключение к MongoDB активно
    if not user_auth.db or not user_auth.pre_subscriptions_collection:
        logger.warning("MongoDB не подключена, пытаемся переподключиться...")
        if not user_auth.connect():
            logger.error("Не удалось подключиться к MongoDB")
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
    
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

@app.route('/save_survey', methods=['POST'])
def save_survey():
    """Сохраняет анкету пользователя в JSON файл"""
    try:
        # Получаем данные из запроса
        data = request.get_json()
        
        if not data or 'filename' not in data or 'data' not in data:
            return jsonify({'success': False, 'error': 'Неверные данные запроса'}), 400
        
        filename = data['filename']
        survey_data = data['data']
        
        # Проверяем, что имя файла безопасное
        if not filename.endswith('.json') or '/' in filename or '\\' in filename:
            return jsonify({'success': False, 'error': 'Неверное имя файла'}), 400
        
        # Создаем папку для анкет, если её нет
        survey_folder = 'survey_responses'
        os.makedirs(survey_folder, exist_ok=True)
        
        # Полный путь к файлу
        filepath = os.path.join(survey_folder, filename)
        
        # Сохраняем данные в JSON файл
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(survey_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Анкета сохранена: {filepath}")
        
        return jsonify({
            'success': True,
            'filepath': filepath,
            'filename': filename
        })
        
    except Exception as e:
        logger.error(f"Ошибка сохранения анкеты: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_recommendations', methods=['POST'])
@subscription_required
def get_recommendations():
    """Получает рекомендации вещей на основе анкеты пользователя"""
    try:
        # Получаем полную анкету из профиля пользователя (как в start_recommendations)
        session_id = session.get('session_id')
        if not session_id:
            print("❌ DEBUG: No session_id")
            return jsonify({'success': False, 'error': 'Не авторизован'})
        
        user = user_auth.get_user_by_session(session_id)
        if not user:
            print("❌ DEBUG: User not found")
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        survey_data = user.get('profile', {}).get('survey_data', {})
        if not survey_data:
            print("❌ DEBUG: No survey data")
            return jsonify({'success': False, 'error': 'Анкета не заполнена'})
        
        print(f"🔍 DEBUG: Found survey data with keys: {list(survey_data.keys())}")
        print(f"🔍 DEBUG: survey_data = {survey_data}")
        if 'top_clothing' in survey_data:
            print(f"🔍 DEBUG: top_clothing = {survey_data['top_clothing']}")
        if 'bottom_clothing' in survey_data:
            print(f"🔍 DEBUG: bottom_clothing = {survey_data['bottom_clothing']}")
        if 'body_type' in survey_data:
            print(f"🔍 DEBUG: body_type = {survey_data['body_type']}")
        
        # Получаем вещи из базы данных используя новую функцию
        filtered_products = get_filtered_products(survey_data)
        
        if not filtered_products:
            return jsonify({
                'success': False,
                'error': 'Не найдено подходящих вещей'
            }), 404
        
        # Исключаем уже показанные товары
        shown_products = session.get('shown_products', [])
        if shown_products:
            # Создаем множество ID уже показанных товаров для быстрого поиска
            shown_ids = set(str(p.get('_id', '')) for p in shown_products)
            # Фильтруем товары, исключая уже показанные
            available_products = [p for p in filtered_products if str(p.get('_id', '')) not in shown_ids]
            print(f"🔍 DEBUG: Excluded {len(filtered_products) - len(available_products)} already shown products")
            print(f"🔍 DEBUG: Available products after filtering: {len(available_products)}")
            
            # Если доступных товаров мало, сбрасываем историю
            if len(available_products) < 10:
                print(f"🔍 DEBUG: Too few available products, resetting history")
                session.pop('shown_products', None)
                available_products = filtered_products
        else:
            available_products = filtered_products
        
        # Используем новую логику генерации рекомендаций
        result = generate_ranked_recommendations(survey_data, available_products)
        
        # Если результат содержит товары, возвращаем их
        if result['type'] == 'products':
            return jsonify({
                'success': True,
                'recommendations': result['products'],
                'generations_used': result['generations_used'],
                'generations_remaining': result['generations_remaining']
            })
        else:
            # Если результат содержит сообщение
            return jsonify({
                'success': True,
                'recommendations': [],
                'message': result['message']
            })
        
    except Exception as e:
        logger.error(f"Ошибка получения рекомендаций: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

def rank_all_products_with_llm(products, survey_data):
    """Ранжирует ВСЕ продукты с помощью LLM и возвращает полный отсортированный список"""
    try:
        logger.info(f"🤖 Начинаем полное LLM ранжирование для {len(products)} товаров")
        
        # Ограничиваем количество товаров для LLM до 50, чтобы избежать проблем с размером промпта
        products_for_llm = products[:50] if len(products) > 50 else products
        logger.info(f"🤖 LLM будет обрабатывать {len(products_for_llm)} товаров из {len(products)}")
        
        # Создаем промпт для LLM с просьбой ранжировать товары
        prompt = create_full_ranking_prompt(products_for_llm, survey_data)
        
        # Отправляем запрос к OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        
        logger.info("📡 Отправляем запрос к OpenAI для полного ранжирования...")
        
        # Добавляем небольшую задержку между запросами
        import time
        time.sleep(1)  # 1 секунда задержки
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты - эксперт по стилю и подбору одежды. Ранжируй ВСЕ товары по приоритету для клиента."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000,  # Увеличиваем токены для большего ответа
            temperature=0.7
        )
        
        # Парсим ответ LLM
        llm_response = response.choices[0].message.content.strip()
        logger.info(f"✅ Получен ответ от OpenAI: {len(llm_response)} символов")
        
        # Проверяем, что ответ не слишком короткий
        if len(llm_response) < 10:
            logger.warning(f"⚠️ LLM вернул слишком короткий ответ: '{llm_response}'")
            logger.warning("🔄 Используем fallback механизм")
            return get_fallback_products(products)
        
        # Извлекаем ранжированные продукты
        ranked_products = parse_full_ranking_response(llm_response, products)
        logger.info(f"📦 LLM ранжировал {len(ranked_products)} товаров")
        
        # Анализируем ранжированные товары по категориям
        ranked_categories = {}
        for product in ranked_products[:20]:  # Анализируем первые 20
            category = product.get('category', 'Другое')
            if category not in ranked_categories:
                ranked_categories[category] = 0
            ranked_categories[category] += 1
        
        logger.info(f"📦 Первые 20 товаров по категориям: {ranked_categories}")
        
        logger.info(f"✅ Полное LLM ранжирование завершено успешно")
        
        return ranked_products  # Возвращаем ВСЕ ранжированные товары
        
    except Exception as e:
        logger.error(f"❌ Ошибка полного LLM ранжирования: {str(e)}")
        logger.warning("🔄 Используем fallback из-за ошибки LLM")
        return get_fallback_products(products)

def rank_products_with_llm(products, survey_data):
    """Ранжирует продукты с помощью LLM (старая функция для совместимости)"""
    try:
        logger.info(f"🤖 Начинаем LLM ранжирование для {len(products)} товаров")
        
        # Создаем промпт для LLM
        prompt = create_recommendation_prompt(products, survey_data)
        
        # Отправляем запрос к OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        
        logger.info("📡 Отправляем запрос к OpenAI...")
        
        # Добавляем небольшую задержку между запросами
        import time
        time.sleep(1)  # 1 секунда задержки
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты - эксперт по стилю и подбору одежды. Выбирай вещи, которые идеально подходят клиенту."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )
        
        # Парсим ответ LLM
        llm_response = response.choices[0].message.content.strip()
        logger.info(f"✅ Получен ответ от OpenAI: {len(llm_response)} символов")
        
        # Проверяем, что ответ не слишком короткий
        if len(llm_response) < 10:
            logger.warning(f"⚠️ LLM вернул слишком короткий ответ: '{llm_response}'")
            logger.warning("🔄 Используем fallback механизм")
            return get_fallback_products(products)
        
        # Извлекаем выбранные продукты (используем переданный список products, который уже отфильтрован)
        selected_products = parse_llm_recommendations(llm_response, products)
        
        # Дополнительная проверка: убеждаемся, что выбранные товары действительно из переданного списка
        valid_products = []
        products_ids = {str(p.get('_id', '')) for p in products}
        
        for product in selected_products:
            product_id = str(product.get('_id', ''))
            if product_id in products_ids:
                valid_products.append(product)
            else:
                print(f"🔍 DEBUG: Исключен товар {product_id} - не найден в переданном списке")
        
        selected_products = valid_products
        logger.info(f"📦 LLM выбрал {len(selected_products)} товаров")
        
        # Анализируем выбранные LLM товары по категориям
        llm_categories = {}
        for product in selected_products:
            category = product.get('category', 'Другое')
            if category not in llm_categories:
                llm_categories[category] = 0
            llm_categories[category] += 1
        
        logger.info(f"📦 LLM выбрал категории: {llm_categories}")
        
        # Проверяем, есть ли все необходимые категории
        required_categories = ['блузы и рубашки', 'брюки', 'джинсы', 'платья и сарафаны', 'юбки']
        missing_categories = [cat for cat in required_categories if cat not in llm_categories]
        if missing_categories:
            logger.warning(f"⚠️ LLM НЕ ВЫБРАЛ категории: {missing_categories}")
        else:
            logger.info(f"✅ LLM выбрал все необходимые категории")
        
        # Если LLM не выбрал товары или выбрал мало, возвращаем все доступные
        if len(selected_products) < 10 and len(products) > 0:
            logger.warning(f"⚠️ LLM выбрал мало товаров ({len(selected_products)}), используем fallback")
            return get_fallback_products(products)
        
        logger.info(f"✅ LLM ранжирование завершено успешно")
        
        # Возвращаем выбранные товары без ограничения по категориям
        # LLM может выбирать те же категории, главное чтобы товары не повторялись
        return selected_products[:20]  # Возвращаем до 20 лучших товаров
        
    except Exception as e:
        logger.error(f"❌ Ошибка LLM ранжирования: {str(e)}")
        logger.warning("🔄 Используем fallback из-за ошибки LLM")
        return get_fallback_products(products)

def get_fallback_products(products):
    """Возвращает fallback товары при ошибке LLM"""
    try:
        # Убираем дубликаты перед случайной выборкой
        unique_products = []
        used_ids = set()
        used_names = set()
        
        for product in products:
            product_id = product.get('_id')
            product_name = product.get('name')
            
            if product_id not in used_ids and product_name not in used_names:
                unique_products.append(product)
                used_ids.add(product_id)
                used_names.add(product_name)
        
        # Возвращаем первые 20 уникальных товаров без ограничения по категориям
        fallback_products = unique_products[:20]
        
        logger.info(f"📦 Fallback: выбрано {len(fallback_products)} товаров")
        return fallback_products
        
    except Exception as e:
        logger.error(f"❌ Ошибка fallback механизма: {str(e)}")
        return products[:20] if len(products) > 0 else []

def create_full_ranking_prompt(products, survey_data):
    """Создает промпт для полного ранжирования ВСЕХ товаров"""
    
    # Дополнительная отладка для понимания структуры данных
    print(f"🔍 DEBUG: Survey data keys: {list(survey_data.keys())}")
    print(f"🔍 DEBUG: Survey data: {survey_data}")
    
    # Получаем данные из анкеты
    color_type = None
    kibbe_type = None
    body_type = survey_data.get('body_type')
    
    # Дополнительная отладка для понимания структуры данных
    print(f"🔍 DEBUG: Raw body_type from survey: {body_type}")
    print(f"🔍 DEBUG: body_type type: {type(body_type)}")
    
    # Проверяем другие возможные места для типа фигуры
    if not body_type or body_type == 'Не указан':
        # Проверяем другие возможные ключи
        for key in ['body_type', 'bodyType', 'figure_type', 'figureType']:
            if key in survey_data:
                alt_body_type = survey_data[key]
                print(f"🔍 DEBUG: Found alternative body type in {key}: {alt_body_type}")
                if isinstance(alt_body_type, dict):
                    body_type = alt_body_type.get('value', alt_body_type.get('label', body_type))
                elif isinstance(alt_body_type, str):
                    body_type = alt_body_type
                break
    
    style_prefs = survey_data.get('style_preferences', [])
    color_prefs = survey_data.get('color_preferences', [])
    top_size = survey_data.get('top_size')
    bottom_size = survey_data.get('bottom_size')
    foot_size = survey_data.get('foot_size')
    
    # Получаем данные анализа фото
    if 'photo_analysis' in survey_data:
        photo_analysis = survey_data['photo_analysis']
        if 'color_analysis' in photo_analysis:
            color_type = photo_analysis['color_analysis'].get('color_type')
        if 'kibbe_analysis' in photo_analysis:
            kibbe_type = photo_analysis['kibbe_analysis'].get('kibbe_type')
    
    # Правильно извлекаем тип фигуры
    body_type_value = None
    if isinstance(body_type, dict):
        body_type_value = body_type.get('value', body_type.get('label', 'Не указан'))
    elif isinstance(body_type, str):
        body_type_value = body_type
    else:
        body_type_value = 'Не указан'
    
    # Создаем JSON с продуктами для LLM (очищаем от datetime объектов)
    def clean_product_for_llm(product):
        """Очищает продукт от несериализуемых объектов для LLM"""
        cleaned = {}
        for key, value in product.items():
            if key in ['_id', 'name', 'brand', 'price', 'currency', 'url', 'imageUrl', 'category', 'subcategory', 'sizes', 'description', 'colorTypes', 'kibbeTypes', 'bodyTypes', 'heights']:
                if isinstance(value, dict):
                    # Рекурсивно очищаем вложенные объекты
                    cleaned[key] = clean_product_for_llm(value)
                elif hasattr(value, '__class__') and value.__class__.__name__ == 'ObjectId':
                    # Преобразуем ObjectId в строку
                    cleaned[key] = str(value)
                else:
                    cleaned[key] = value
        return cleaned
    
    cleaned_products = [clean_product_for_llm(product) for product in products]
    products_json = json.dumps(cleaned_products, ensure_ascii=False, indent=2)
    
    # Маппинг типов фигуры из анкеты в базу данных
    body_type_mapping = {
        # Английские названия
        'pear': ['Груша', 'груша'],
        'apple': ['Яблоко', 'яблоко'],
        'hourglass': ['Песочные часы', 'песочные часы'],
        'rectangle': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)', 'Прямоугольник', 'прямоугольник'],
        'inverted_triangle': ['Перевернутый треугольник', 'перевернутый треугольник'],
        
        # Русские названия
        'груша': ['Груша', 'груша'],
        'яблоко': ['Яблоко', 'яблоко'],
        'песочные часы': ['Песочные часы', 'песочные часы'],
        'прямоугольник': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)', 'Прямоугольник', 'прямоугольник'],
        'перевернутый треугольник': ['Перевернутый треугольник', 'перевернутый треугольник'],
        
        # Альтернативные варианты
        'triangle': ['Перевернутый треугольник', 'перевернутый треугольник'],
        'triangle_inverted': ['Перевернутый треугольник', 'перевернутый треугольник'],
        'rectangle_small': ['Прямоугольник (до 46)', 'Прямоугольник', 'прямоугольник'],
        'rectangle_large': ['Прямоугольник (от 48)', 'Прямоугольник', 'прямоугольник'],
        
        # Варианты с разным регистром
        'Pear': ['Груша', 'груша'],
        'Apple': ['Яблоко', 'яблоко'],
        'Hourglass': ['Песочные часы', 'песочные часы'],
        'Rectangle': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)', 'Прямоугольник', 'прямоугольник'],
        'Inverted_triangle': ['Перевернутый треугольник', 'перевернутый треугольник']
    }
    
    # Получаем соответствующие типы фигуры из базы данных
    mapped_body_types = body_type_mapping.get(body_type_value.lower(), [body_type_value])
    print(f"🔍 DEBUG: Маппинг типа фигуры '{body_type_value}' -> {mapped_body_types}")
    
    # Анализируем доступные товары для типа фигуры пользователя
    available_for_body_type = []
    for product in products:
        body_types = product.get('bodyTypes', [])
        if isinstance(body_types, str):
            body_types = [body_types]
        elif not isinstance(body_types, list):
            body_types = []
        
        # Проверяем, подходит ли товар для типа фигуры пользователя
        if any(mapped_type.lower() in [bt.lower() for bt in body_types] for mapped_type in mapped_body_types):
            available_for_body_type.append(product)
    
    print(f"🔍 DEBUG: Товары подходящие для типа фигуры '{body_type_value}': {len(available_for_body_type)} из {len(products)}")
    
    # Группируем подходящие товары по категориям
    suitable_by_category = {}
    for product in available_for_body_type:
        category = product.get('category', 'Другое')
        if category not in suitable_by_category:
            suitable_by_category[category] = []
        suitable_by_category[category].append(product)
    
    print(f"🔍 DEBUG: Подходящие товары по категориям: {suitable_by_category}")
    
    # Создаем промпт для полного ранжирования
    prompt = f"""
    ЗАДАЧА: РАНЖИРУЙ ВСЕ {len(products)} ТОВАРОВ ПО ПРИОРИТЕТУ ДЛЯ КЛИЕНТА
    
    ДАННЫЕ КЛИЕНТА:
    - Тип фигуры: {body_type_value}
    - Цветотип: {color_type or 'Не указан'}
    - Типаж Кибби: {kibbe_type or 'Не указан'}
    - Стиль: {', '.join(style_prefs) if style_prefs else 'Не указан'}
    - Цветовые предпочтения: {', '.join(color_prefs) if color_prefs else 'Не указан'}
    - Размеры: верх {top_size}, низ {bottom_size}, ноги {foot_size}
    
    ДОСТУПНЫЕ ВЕЩИ:
    {products_json}
    
    ДОСТУПНЫЕ КАТЕГОРИИ В СПИСКЕ:
    {suitable_by_category}
    
    ВАЖНО: В списке есть товары из следующих категорий: {list(suitable_by_category.keys())}
    
         ЗАДАЧА:
     1. ПРИОРИТЕТ 1: Тип фигуры - это самый важный критерий!
        - Выбирай ТОЛЬКО вещи, которые подходят для типа фигуры "{body_type_value}"
        - Если в поле bodyTypes указан другой тип фигуры - НЕ ВЫБИРАЙ эту вещь
        - Тип фигуры должен точно совпадать
     
     2. ПРИОРИТЕТ 2: ОБЯЗАТЕЛЬНО ОБЕСПЕЧЬ РАЗНООБРАЗИЕ КАТЕГОРИЙ!
        - В списке есть товары разных категорий: платья, блузы, джинсы, брюки, юбки, шорты
        - ОБЯЗАТЕЛЬНО включи товары из КАЖДОЙ доступной категории
        - НЕ ВЫБИРАЙ ТОЛЬКО ОДНУ КАТЕГОРИЮ - обеспечь разнообразие!
        - МАКСИМУМ 4 товара из каждой категории!
        - МИНИМУМ 2-3 товара из каждой категории!
        - ОБЯЗАТЕЛЬНО включи блузы/рубашки, брюки, джинсы!
        - РАСПРЕДЕЛИ ТОВАРЫ ПО ВСЕМ КАТЕГОРИЯМ равномерно!
        - Если в какой-то категории мало товаров - все равно включи их!
     
     3. ПРИОРИТЕТ 3: Дополнительные критерии (в порядке важности):
        - Соответствие цветотипу
        - Соответствие типажу Кибби  
        - Соответствие стилю
        - Соответствие размерам
        - Качество и цена
     
     4. РАНЖИРУЙ ВСЕ {len(products)} ТОВАРОВ от лучшего к худшему
     
     5. Верни ТОЛЬКО JSON массив с ВСЕМИ товарами в порядке приоритета, используя только поля: _id, name, brand
    
    ПРИМЕР ОТВЕТА:
    [
      {{"_id": "123", "name": "Название товара", "brand": "Бренд"}},
      {{"_id": "456", "name": "Другой товар", "brand": "Другой бренд"}},
      ...
    ]
    
         ВАЖНО: 
     - Верни ТОЛЬКО JSON массив
     - Используй ТОЛЬКО поля _id, name, brand
     - Не добавляй никакого текста до или после JSON
     - Убедись, что JSON синтаксически корректен
     - ПРИОРИТЕТ 1: тип фигуры должен точно совпадать!
     - ПРИОРИТЕТ 2: ОБЯЗАТЕЛЬНО ОБЕСПЕЧЬ РАЗНООБРАЗИЕ КАТЕГОРИЙ!
     - НЕ ВЫБИРАЙ ОДИН И ТОТ ЖЕ ТОВАР ДВАЖДЫ - каждый товар должен быть уникальным!
     - НЕ ВЫБИРАЙ ТОЛЬКО ОДНУ КАТЕГОРИЮ - обеспечь разнообразие!
     - МАКСИМУМ 4 товара из каждой категории!
     - МИНИМУМ 2-3 товара из каждой категории!
     - ОБЯЗАТЕЛЬНО включи блузы/рубашки, брюки, джинсы!
     - РАСПРЕДЕЛИ ТОВАРЫ ПО ВСЕМ КАТЕГОРИЯМ равномерно!
     - РАНЖИРУЙ ВСЕ {len(products)} ТОВАРОВ!
    """
    
    logger.info(f"🔍 Создан промпт для полного ранжирования длиной {len(prompt)} символов")
    logger.info(f"🔍 Тип фигуры в промпте: '{body_type_value}'")
    logger.info(f"🔍 Количество товаров в промпте: {len(cleaned_products)}")
    
    return prompt

def create_recommendation_prompt(products, survey_data):
    """Создает промпт для LLM"""
    
    # Получаем данные из анкеты
    color_type = None
    kibbe_type = None
    body_type = survey_data.get('body_type')
    style_prefs = survey_data.get('style_preferences', [])
    color_prefs = survey_data.get('color_preferences', [])
    top_size = survey_data.get('top_size')
    bottom_size = survey_data.get('bottom_size')
    foot_size = survey_data.get('foot_size')
    
    # Получаем данные анализа фото
    if 'photo_analysis' in survey_data:
        photo_analysis = survey_data['photo_analysis']
        if 'color_analysis' in photo_analysis:
            color_type = photo_analysis['color_analysis'].get('color_type')
        if 'kibbe_analysis' in photo_analysis:
            kibbe_type = photo_analysis['kibbe_analysis'].get('kibbe_type')
    
    # Правильно извлекаем тип фигуры
    body_type_value = None
    if isinstance(body_type, dict):
        body_type_value = body_type.get('value', body_type.get('label', 'Не указан'))
    elif isinstance(body_type, str):
        body_type_value = body_type
    else:
        body_type_value = 'Не указан'
    
    # Создаем JSON с продуктами для LLM (очищаем от datetime объектов)
    def clean_product_for_llm(product):
        """Очищает продукт от несериализуемых объектов для LLM"""
        cleaned = {}
        for key, value in product.items():
            if key in ['_id', 'name', 'brand', 'price', 'currency', 'url', 'imageUrl', 'category', 'subcategory', 'sizes', 'description', 'colorTypes', 'kibbeTypes', 'bodyTypes', 'heights']:
                if isinstance(value, dict):
                    # Рекурсивно очищаем вложенные объекты
                    cleaned[key] = clean_product_for_llm(value)
                elif hasattr(value, '__class__') and value.__class__.__name__ == 'ObjectId':
                    # Преобразуем ObjectId в строку
                    cleaned[key] = str(value)
                else:
                    cleaned[key] = value
        return cleaned
    
    cleaned_products = [clean_product_for_llm(product) for product in products]
    products_json = json.dumps(cleaned_products, ensure_ascii=False, indent=2)
    
    # Маппинг типов фигуры из анкеты в базу данных
    body_type_mapping = {
        # Английские названия
        'pear': ['Груша', 'груша'],
        'apple': ['Яблоко', 'яблоко'],
        'hourglass': ['Песочные часы', 'песочные часы'],
        'rectangle': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)', 'Прямоугольник', 'прямоугольник'],
        'inverted_triangle': ['Перевернутый треугольник', 'перевернутый треугольник'],
        
        # Русские названия
        'груша': ['Груша', 'груша'],
        'яблоко': ['Яблоко', 'яблоко'],
        'песочные часы': ['Песочные часы', 'песочные часы'],
        'прямоугольник': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)', 'Прямоугольник', 'прямоугольник'],
        'перевернутый треугольник': ['Перевернутый треугольник', 'перевернутый треугольник'],
        
        # Альтернативные варианты
        'triangle': ['Перевернутый треугольник', 'перевернутый треугольник'],
        'triangle_inverted': ['Перевернутый треугольник', 'перевернутый треугольник'],
        'rectangle_small': ['Прямоугольник (до 46)', 'Прямоугольник', 'прямоугольник'],
        'rectangle_large': ['Прямоугольник (от 48)', 'Прямоугольник', 'прямоугольник'],
        
        # Варианты с разным регистром
        'Pear': ['Груша', 'груша'],
        'Apple': ['Яблоко', 'яблоко'],
        'Hourglass': ['Песочные часы', 'песочные часы'],
        'Rectangle': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)', 'Прямоугольник', 'прямоугольник'],
        'Inverted_triangle': ['Перевернутый треугольник', 'перевернутый треугольник']
    }
    
    # Получаем соответствующие типы фигуры из базы данных
    mapped_body_types = body_type_mapping.get(body_type_value.lower(), [body_type_value])
    print(f"🔍 DEBUG: Маппинг типа фигуры '{body_type_value}' -> {mapped_body_types}")
    
    # Анализируем доступные товары для типа фигуры пользователя
    available_for_body_type = []
    for product in products:
        body_types = product.get('bodyTypes', [])
        if isinstance(body_types, str):
            body_types = [body_types]
        elif not isinstance(body_types, list):
            body_types = []
        
        # Проверяем, подходит ли товар для типа фигуры пользователя
        if any(mapped_type.lower() in [bt.lower() for bt in body_types] for mapped_type in mapped_body_types):
            available_for_body_type.append(product)
    
    print(f"🔍 DEBUG: Товары подходящие для типа фигуры '{body_type_value}': {len(available_for_body_type)} из {len(products)}")
    
    # Группируем подходящие товары по категориям
    suitable_by_category = {}
    for product in available_for_body_type:
        category = product.get('category', 'Другое')
        if category not in suitable_by_category:
            suitable_by_category[category] = 0
        suitable_by_category[category] += 1
    
    print(f"🔍 DEBUG: Подходящие товары по категориям: {suitable_by_category}")
    
    prompt = f"""
Ты - эксперт по стилю. Подбери 20 лучших вещей для клиента.

ДАННЫЕ КЛИЕНТА:
- Цветотип: {color_type or 'Не определен'}
- Типаж Кибби: {kibbe_type or 'Не определен'}
- Тип фигуры: {body_type_value} (КРИТИЧЕСКИ ВАЖНО!)
- Предпочтения стиля: {', '.join(style_prefs)}
- Цветовая гамма: {', '.join(color_prefs)}
- Размеры: верх {top_size}, низ {bottom_size}, ноги {foot_size}

ДОСТУПНЫЕ ВЕЩИ:
{products_json}

ДОСТУПНЫЕ КАТЕГОРИИ В СПИСКЕ:
{suitable_by_category}

ВАЖНО: В списке есть товары из следующих категорий: {list(suitable_by_category.keys())}
ОБЯЗАТЕЛЬНО ВКЛЮЧИ ТОВАРЫ ИЗ КАЖДОЙ КАТЕГОРИИ!

ЗАДАЧА:
1. ПРИОРИТЕТ 1: Тип фигуры - это самый важный критерий!
   - Выбирай ТОЛЬКО вещи, которые подходят для типа фигуры "{body_type_value}"
   - Если в поле bodyTypes указан другой тип фигуры - НЕ ВЫБИРАЙ эту вещь
   - Тип фигуры должен точно совпадать

2. ПРИОРИТЕТ 2: ОБЯЗАТЕЛЬНО ВЫБЕРИ ТОВАРЫ ИЗ ВСЕХ КАТЕГОРИЙ!
   - В списке есть товары разных категорий: платья, блузы, джинсы, брюки, юбки, шорты
   - ОБЯЗАТЕЛЬНО включи товары из КАЖДОЙ доступной категории
   - НЕ ВЫБИРАЙ ТОЛЬКО ПЛАТЬЯ И ЮБКИ - включи джинсы, брюки, блузы
   - Обеспечь разнообразие категорий в рекомендациях
   - Если в какой-то категории мало товаров - все равно включи их!
   - РАСПРЕДЕЛИ 20 товаров ПО ВСЕМ КАТЕГОРИЯМ равномерно
   - МИНИМУМ 2-3 товара из каждой категории!
   - ОБЯЗАТЕЛЬНО включи блузы/рубашки, брюки, джинсы!

3. Дополнительные критерии (в порядке важности):
   - Соответствие цветотипу
   - Соответствие типажу Кибби  
   - Соответствие стилю
   - Соответствие размерам
   - Качество и цена

4. Выбери 20 лучших вещей, строго соблюдая приоритет типа фигуры И разнообразие категорий

5. Верни ТОЛЬКО JSON массив с выбранными вещами, используя только поля: _id, name, brand

ПРИМЕР ОТВЕТА:
[
  {{"_id": "123", "name": "Название товара", "brand": "Бренд"}},
  {{"_id": "456", "name": "Другой товар", "brand": "Другой бренд"}}
]

ВАЖНО: 
- Верни ТОЛЬКО JSON массив
- Используй ТОЛЬКО поля _id, name, brand
- Не добавляй никакого текста до или после JSON
- Убедись, что JSON синтаксически корректен
- ПРИОРИТЕТ 1: тип фигуры должен точно совпадать!
- ПРИОРИТЕТ 2: ОБЯЗАТЕЛЬНО включи товары из ВСЕХ категорий!
- НЕ ВЫБИРАЙ ОДИН И ТОТ ЖЕ ТОВАР ДВАЖДЫ - каждый товар должен быть уникальным!
- НЕ ВЫБИРАЙ ТОЛЬКО ПЛАТЬЯ И ЮБКИ - включи джинсы, брюки, блузы!
- МИНИМУМ 2-3 товара из каждой категории!
- ОБЯЗАТЕЛЬНО включи блузы/рубашки, брюки, джинсы!
- ВЫБИРАЙ ТОЛЬКО НОВЫЕ ТОВАРЫ - не повторяй товары, которые уже были показаны!
"""
    
    logger.info(f"🔍 Создан промпт для LLM длиной {len(prompt)} символов")
    logger.info(f"🔍 Тип фигуры в промпте: '{body_type_value}'")
    logger.info(f"🔍 Количество товаров в промпте: {len(cleaned_products)}")
    
    return prompt

def parse_full_ranking_response(llm_response, original_products):
    """Парсит полное ранжирование LLM и возвращает ВСЕ товары в порядке приоритета"""
    try:
        logger.info(f"🔍 Парсинг полного ранжирования LLM...")
        
        # Ищем JSON в ответе
        json_start = llm_response.find('[')
        json_end = llm_response.rfind(']') + 1
        
        if json_start == -1 or json_end == 0:
            logger.warning("⚠️ JSON массив не найден в ответе LLM")
            logger.warning(f"🔍 Ответ LLM: {llm_response[:200]}...")
            return original_products
        
        json_str = llm_response[json_start:json_end]
        
        try:
            ranked_data = json.loads(json_str)
            logger.info(f"✅ Успешно распарсен JSON с {len(ranked_data)} элементами")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            logger.error(f"🔍 Проблемный JSON: {json_str[:200]}...")
            return original_products
        
        # Создаем словарь для быстрого поиска товаров по ID
        products_by_id = {}
        for product in original_products:
            product_id = str(product.get('_id', ''))
            if product_id:
                products_by_id[product_id] = product
        
        # Восстанавливаем полные данные товаров в порядке ранжирования
        ranked_products = []
        for item in ranked_data:
            if isinstance(item, dict):
                product_id = str(item.get('_id', ''))
                if product_id in products_by_id:
                    ranked_products.append(products_by_id[product_id])
                else:
                    logger.warning(f"⚠️ Товар с ID {product_id} не найден в исходном списке")
        
        logger.info(f"✅ Восстановлено {len(ranked_products)} товаров из {len(ranked_data)} ранжированных")
        
        # Если LLM вернул меньше товаров, чем есть в исходном списке, добавляем оставшиеся
        if len(ranked_products) < len(original_products):
            ranked_ids = {str(p.get('_id', '')) for p in ranked_products}
            remaining_products = [p for p in original_products if str(p.get('_id', '')) not in ranked_ids]
            ranked_products.extend(remaining_products)
            logger.info(f"✅ Добавлено {len(remaining_products)} оставшихся товаров")
        
        return ranked_products
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга полного ранжирования: {str(e)}")
        return original_products

def parse_llm_recommendations(llm_response, original_products):
    """Парсит ответ LLM и возвращает выбранные продукты"""
    try:
        logger.info(f"🔍 Парсим ответ LLM: {len(llm_response)} символов")
        logger.info(f"🔍 Содержимое ответа LLM: '{llm_response[:200]}...'")  # Показываем первые 200 символов
        
        # Ищем JSON в ответе LLM
        import re
        json_match = re.search(r'\[.*\]', llm_response, re.DOTALL)
        
        if json_match:
            logger.info(f"🔍 Найден JSON match: '{json_match.group()[:200]}...'")
            try:
                selected_data = json.loads(json_match.group())
                logger.info(f"✅ Найден JSON с {len(selected_data)} товарами")
                
                # Сопоставляем с оригинальными продуктами
                selected_products = []
                used_ids = set()  # Для отслеживания уже использованных ID
                used_names = set()  # Для отслеживания уже использованных названий
                
                print(f"🔍 DEBUG: parse_llm_recommendations: ищем {len(selected_data)} товаров в списке из {len(original_products)} товаров")
                print(f"🔍 DEBUG: original_products IDs (первые 5): {[str(p.get('_id', '')) for p in original_products[:5]]}")
                
                for item in selected_data:
                    # Ищем соответствующий продукт по ID или названию
                    found = False
                    for product in original_products:
                        product_id = product.get('_id')
                        product_name = product.get('name')
                        
                        # Проверяем, не использовали ли мы уже этот товар
                        if (product_id in used_ids or product_name in used_names):
                            continue
                            
                        if (product_id == item.get('_id') or 
                            product_name == item.get('name')):
                            selected_products.append(product)
                            used_ids.add(product_id)
                            used_names.add(product_name)
                            found = True
                            print(f"🔍 DEBUG: Найден товар {product_id} в original_products")
                            break
                    
                    if not found:
                        print(f"🔍 DEBUG: Товар {item.get('_id')} НЕ найден в original_products")
                
                logger.info(f"📦 Сопоставлено {len(selected_products)} товаров")
                return selected_products
                
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ Ошибка парсинга JSON: {e}")
                logger.warning(f"⚠️ Проблемный JSON: '{json_match.group()}'")
                # Пытаемся исправить JSON
                try:
                    # Удаляем лишние запятые и исправляем синтаксис
                    fixed_json = re.sub(r',\s*}', '}', json_match.group())
                    fixed_json = re.sub(r',\s*]', ']', fixed_json)
                    selected_data = json.loads(fixed_json)
                    
                    logger.info(f"✅ Исправлен JSON с {len(selected_data)} товарами")
                    
                    # Сопоставляем с оригинальными продуктами
                    selected_products = []
                    used_ids = set()  # Для отслеживания уже использованных ID
                    used_names = set()  # Для отслеживания уже использованных названий
                    
                    for item in selected_data:
                        for product in original_products:
                            product_id = product.get('_id')
                            product_name = product.get('name')
                            
                            # Проверяем, не использовали ли мы уже этот товар
                            if (product_id in used_ids or product_name in used_names):
                                continue
                                
                            if (product_id == item.get('_id') or 
                                product_name == item.get('name')):
                                selected_products.append(product)
                                used_ids.add(product_id)
                                used_names.add(product_name)
                                break
                    
                    logger.info(f"📦 Сопоставлено {len(selected_products)} товаров после исправления")
                    return selected_products
                    
                except Exception as fix_error:
                    logger.warning(f"⚠️ Не удалось исправить JSON: {fix_error}")
        else:
            logger.warning(f"⚠️ JSON не найден в ответе LLM")
        
        # Если не удалось распарсить JSON, возвращаем случайные
        logger.warning("⚠️ Не удалось найти JSON в ответе LLM, используем случайные товары")
        import random
        
        # Убираем дубликаты перед случайной выборкой
        unique_products = []
        used_ids = set()
        used_names = set()
        
        for product in original_products:
            product_id = product.get('_id')
            product_name = product.get('name')
            
            if product_id not in used_ids and product_name not in used_names:
                unique_products.append(product)
                used_ids.add(product_id)
                used_names.add(product_name)
        
        return random.sample(unique_products, min(20, len(unique_products)))
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга LLM ответа: {str(e)}")
        # Возвращаем случайные продукты в случае ошибки
        import random
        return random.sample(original_products, min(20, len(original_products)))

@app.route('/check_survey_status')
def check_survey_status():
    """Проверка статуса анкеты пользователя"""
    session_id = session.get('session_id')
    
    if not session_id:
        return jsonify({'authenticated': False, 'has_survey': False, 'subscription_active': False})
    
    user = user_auth.get_user_by_session(session_id)
    
    if not user:
        return jsonify({'authenticated': False, 'has_survey': False, 'subscription_active': False})
    
    # Проверяем, есть ли данные анкеты
    survey_data = user.get('profile', {}).get('survey_data', {})
    has_survey = len(survey_data) > 0
    
    # Проверяем статус подписки через предварительные подписки
    subscription_active = user_auth.check_subscription(str(user['_id']))
    
    # Добавляем логирование для отладки
    logger.info(f"🔍 check_survey_status - User: {user.get('email')}, Subscription: {subscription_active}")
    
    return jsonify({
        'authenticated': True,
        'has_survey': has_survey,
        'subscription_active': subscription_active,
        'survey_data': survey_data
    })

@app.route('/start_recommendations', methods=['POST'])
def start_recommendations():
    """Запуск подбора вещей на основе анкеты"""
    print("🔍 DEBUG: start_recommendations called")
    
    session_id = session.get('session_id')
    if not session_id:
        print("❌ DEBUG: No session_id")
        return jsonify({'success': False, 'error': 'Не авторизован'})
    
    user = user_auth.get_user_by_session(session_id)
    if not user:
        print("❌ DEBUG: User not found")
        return jsonify({'success': False, 'error': 'Пользователь не найден'})
    
    survey_data = user.get('profile', {}).get('survey_data', {})
    if not survey_data:
        print("❌ DEBUG: No survey data")
        return jsonify({'success': False, 'error': 'Анкета не заполнена'})
    
    print(f"🔍 DEBUG: Found survey data with keys: {list(survey_data.keys())}")
    
    try:
        # Получаем отфильтрованные товары на основе анкеты
        # Определяем количество товаров для выборки (100 + 20 * номер генерации)
        generation_number = session.get('daily_generations', 0)
        products_to_select = 100 + (generation_number * 20)
        
        print("🔍 DEBUG: Calling get_filtered_products...")
        filtered_products = get_filtered_products(survey_data, limit=products_to_select)
        print(f"🔍 DEBUG: get_filtered_products returned {len(filtered_products)} products (запрошено {products_to_select})")
        
        # Исключаем уже показанные товары
        shown_products = session.get('shown_products', [])
        if shown_products:
            # Создаем множество ID уже показанных товаров для быстрого поиска
            shown_ids = set(shown_products)
            # Фильтруем товары, исключая уже показанные
            available_products = [p for p in filtered_products if str(p.get('_id')) not in shown_ids]
            print(f"🔍 DEBUG: Excluded {len(filtered_products) - len(available_products)} already shown products")
            print(f"🔍 DEBUG: Available products after filtering: {len(available_products)}")
            
            # Если доступных товаров мало, сбрасываем историю
            if len(available_products) < 10:
                print(f"🔍 DEBUG: Too few available products, resetting history")
                shown_products = []
                available_products = filtered_products
        else:
            available_products = filtered_products
        
        # Генерируем рекомендации из ранжированного списка
        print("🔍 DEBUG: Calling generate_ranked_recommendations...")
        
        # Получаем текущий индекс из сессии
        current_index = session.get('recommendations_index', 0)
        print(f"🔍 DEBUG: Current recommendations index: {current_index}")
        
        recommendations = generate_ranked_recommendations(survey_data, available_products, start_index=current_index, batch_size=20)
        print(f"🔍 DEBUG: generate_ranked_recommendations returned: {type(recommendations)}")
        
        # Обновляем индекс для следующего запроса
        if recommendations.get('type') == 'products' and 'products' in recommendations:
            new_index = current_index + 20
            session['recommendations_index'] = new_index
            print(f"🔍 DEBUG: Updated recommendations index: {current_index} -> {new_index}")
        else:
            print(f"🔍 DEBUG: No products returned, keeping index at {current_index}")
        
        response = {
            'success': True,
            'recommendations': recommendations,
            'products_count': len(available_products),
            'total_available': len(filtered_products),
            'current_index': current_index,
            'next_index': session.get('recommendations_index', 0)
        }
        
        print(f"🔍 DEBUG: Returning response with recommendations type: {recommendations.get('type', 'unknown')}")
        return jsonify(response)
    except Exception as e:
        print(f"❌ DEBUG: Exception in start_recommendations: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/reset_recommendations_history', methods=['POST'])
def reset_recommendations_history():
    """Сбрасывает историю показанных товаров и счетчики генераций"""
    try:
        session.pop('shown_products', None)
        session.pop('ranked_products', None)
        session.pop('recommendations_index', None)
        session.pop('total_ranked', None)
        session.pop('daily_generations', None)
        session.pop('last_generation_date', None)
        print("🔍 DEBUG: Reset recommendations history, ranking, and daily counters")
        return jsonify({'success': True, 'message': 'История рекомендаций и счетчики сброшены. Теперь вы можете получить до 5 новых подборов в день.'})
    except Exception as e:
        print(f"❌ DEBUG: Exception in reset_recommendations_history: {e}")
        return jsonify({'success': False, 'error': str(e)})

def get_filtered_products(survey_data, limit=100):
    """Фильтрация товаров на основе данных анкеты с двумя отдельными запросами"""
    try:
        # Подключение к MongoDB
        client = MongoClient(mongo_config.mongo_config.mongo_uri)
        db = client[mongo_config.mongo_config.database_name]
        products_collection = db["products_enhanced"]
        
        def extract_values(data):
            values = []
            if isinstance(data, dict) and data.get('values'):
                for item in data['values']:
                    if isinstance(item, dict) and 'value' in item:
                        values.append(item['value'])
                    elif isinstance(item, str):
                        values.append(item)
            elif isinstance(data, dict) and 'value' in data:
                # Одиночный выбор
                values.append(data['value'])
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and 'value' in item:
                        values.append(item['value'])
                    elif isinstance(item, str):
                        values.append(item)
            elif isinstance(data, str):
                values.append(data)
            return values
        
        # Получаем категории из survey_data
        clothing_types = []
        
        # Добавляем верхнюю одежду
        if survey_data.get('top_clothing'):
            top_clothing_values = extract_values(survey_data['top_clothing'])
            clothing_types.extend(top_clothing_values)
            print(f"🔍 DEBUG: top_clothing values = {top_clothing_values}")
        
        # Добавляем нижнюю одежду
        if survey_data.get('bottom_clothing'):
            bottom_clothing_values = extract_values(survey_data['bottom_clothing'])
            clothing_types.extend(bottom_clothing_values)
            print(f"🔍 DEBUG: bottom_clothing values = {bottom_clothing_values}")
        
        # Добавляем дополнительные предметы
        if survey_data.get('additional_items'):
            additional_items_values = extract_values(survey_data['additional_items'])
            clothing_types.extend(additional_items_values)
            print(f"🔍 DEBUG: additional_items values = {additional_items_values}")
        
        print(f"🔍 DEBUG: all clothing_types = {clothing_types}")
        
        # Маппинг категорий
        category_mapping = {
            # Английские варианты
            'dresses': ['Платья и сарафаны', 'платья и сарафаны'],
            'blouses': ['Блузы и рубашки', 'блузы и рубашки'],
            'shirts': ['Блузы и рубашки', 'блузы и рубашки'],
            'tshirts': ['Футболки', 'футболки'],
            'jackets': ['Пиджаки', 'пиджаки'],
            'hoodies': ['Худи', 'худи'],
            'pants': ['Брюки', 'брюки'],
            'jeans': ['Джинсы', 'джинсы'],
            'skirts': ['Юбки', 'юбки'],
            'shorts': ['Шорты', 'шорты'],
            'shoes': ['ботинки', 'сандалии', 'сапоги', 'туфли', 'балетки', 'сабо и мюли', 'кроссовки и кеды', 'босоножки', 'ботильоны'],
            'bags': ['сумки'],
            'jewelry': ['украшения'],
            'accessories': ['ремни и пояса', 'платки и шарфы', 'шарфы и платки', 'перчатки и варежки', 'головные уборы', 'очки'],
            
            # Русские варианты
            'платья': ['Платья и сарафаны', 'платья и сарафаны'],
            'блузки': ['Блузы и рубашки', 'блузы и рубашки'],
            'рубашки': ['Блузы и рубашки', 'блузы и рубашки'],
            'футболки': ['Футболки', 'футболки'],
            'пиджаки': ['Пиджаки', 'пиджаки'],
            'худи': ['Худи', 'худи'],
            'брюки': ['Брюки', 'брюки'],
            'джинсы': ['Джинсы', 'джинсы'],
            'юбки': ['Юбки', 'юбки'],
            'шорты': ['Шорты', 'шорты'],
            'обувь': ['ботинки', 'сандалии', 'сапоги', 'туфли', 'балетки', 'сабо и мюли', 'кроссовки и кеды', 'босоножки', 'ботильоны'],
            'сумки': ['сумки'],
            'украшения': ['украшения'],
            'аксессуары': ['ремни и пояса', 'платки и шарфы', 'шарфы и платки', 'перчатки и варежки', 'головные уборы', 'очки'],
            
            # Варианты с заглавными буквами
            'Dresses': ['Платья и сарафаны', 'платья и сарафаны'],
            'Blouses': ['Блузы и рубашки', 'блузы и рубашки'],
            'Shirts': ['Блузы и рубашки', 'блузы и рубашки'],
            'Tshirts': ['Футболки', 'футболки'],
            'Jackets': ['Пиджаки', 'пиджаки'],
            'Hoodies': ['Худи', 'худи'],
            'Pants': ['Брюки', 'брюки'],
            'Jeans': ['Джинсы', 'джинсы'],
            'Skirts': ['Юбки', 'юбки'],
            'Shorts': ['Шорты', 'шорты'],
            'Shoes': ['ботинки', 'сандалии', 'сапоги', 'туфли', 'балетки', 'сабо и мюли', 'кроссовки и кеды', 'босоножки', 'ботильоны'],
            'Bags': ['сумки'],
            'Jewelry': ['украшения'],
            'Accessories': ['ремни и пояса', 'платки и шарфы', 'шарфы и платки', 'перчатки и варежки', 'головные уборы', 'очки']
        }
        
        # Собираем все целевые категории
        target_categories = []
        for clothing_type in clothing_types:
            print(f"🔍 DEBUG: checking clothing_type = '{clothing_type}'")
            if clothing_type in category_mapping:
                mapped_categories = category_mapping[clothing_type]
                target_categories.extend(mapped_categories)
                print(f"🔍 DEBUG: mapped '{clothing_type}' to {mapped_categories}")
            else:
                print(f"🔍 DEBUG: no mapping found for '{clothing_type}'")
        
        print(f"🔍 DEBUG: final target_categories = {target_categories}")
        if not target_categories:
            print("🔍 DEBUG: No valid categories found!")
            return []
        
        # Разделяем категории на одежду и аксессуары
        clothing_categories = []
        accessory_categories = []
        
        for cat in target_categories:
            if cat.lower() in ['ботинки', 'сандалии', 'сапоги', 'туфли', 'балетки', 'сабо и мюли', 'кроссовки и кеды', 'босоножки', 'ботильоны', 'сумки', 'украшения', 'ремни и пояса', 'платки и шарфы', 'шарфы и платки', 'перчатки и варежки', 'головные уборы', 'очки']:
                accessory_categories.append(cat)
            else:
                clothing_categories.append(cat)
        
        print(f"🔍 DEBUG: clothing_categories = {clothing_categories}")
        print(f"🔍 DEBUG: accessory_categories = {accessory_categories}")
        
        all_products = []
        
        # ЗАПРОС 1: Одежда (с фильтрами по размеру и типу фигуры)
        if clothing_categories:
            print("🔍 DEBUG: Выполняем запрос для одежды...")
            
            # Строим фильтр для одежды
            clothing_filter = {'category': {'$in': clothing_categories}}
            
            # Добавляем фильтр по размеру
            if survey_data.get('top_size') or survey_data.get('bottom_size'):
                size_conditions = []
                
                # Размеры верхней одежды
                if survey_data.get('top_size'):
                    top_sizes = extract_values(survey_data['top_size'])
                    for size in top_sizes:
                        size_conditions.append({'sizes.Российский': {'$regex': str(size), '$options': 'i'}})
                        size_conditions.append({'sizes.Производителя': {'$regex': str(size), '$options': 'i'}})
                
                # Размеры нижней одежды
                if survey_data.get('bottom_size'):
                    bottom_sizes = extract_values(survey_data['bottom_size'])
                    for size in bottom_sizes:
                        size_conditions.append({'sizes.Российский': {'$regex': str(size), '$options': 'i'}})
                        size_conditions.append({'sizes.Производителя': {'$regex': str(size), '$options': 'i'}})
                
                if size_conditions:
                    clothing_filter['$or'] = size_conditions
            
            # Добавляем фильтр по типу фигуры
            body_type = survey_data.get('body_type')
            if body_type and body_type != 'Не указан':
                if isinstance(body_type, dict):
                    body_type_value = body_type.get('value', body_type.get('label', ''))
            else:
                body_type_value = str(body_type)
                
            if body_type_value:
                # Маппинг типов фигуры
                body_type_mapping = {
                    'груша': ['Груша'],
                    'pear': ['Груша'],
                    'Груша': ['Груша'],
                    'Pear': ['Груша'],
                    'яблоко': ['Яблоко'],
                    'apple': ['Яблоко'],
                    'Яблоко': ['Яблоко'],
                    'Apple': ['Яблоко'],
                    'песочные часы': ['Песочные часы'],
                    'hourglass': ['Песочные часы'],
                    'Песочные часы': ['Песочные часы'],
                    'Hourglass': ['Песочные часы'],
                    'прямоугольник': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)'],
                    'rectangle': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)'],
                    'Прямоугольник': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)'],
                    'Rectangle': ['Прямоугольник (до 46)', 'Прямоугольник (от 48)'],
                    'перевернутый треугольник': ['Перевернутый треугольник'],
                    'inverted triangle': ['Перевернутый треугольник'],
                    'Перевернутый треугольник': ['Перевернутый треугольник'],
                    'Inverted Triangle': ['Перевернутый треугольник']
                }
                
                mapped_body_types = body_type_mapping.get(body_type_value.lower(), [body_type_value])
                clothing_filter['bodyTypes'] = {'$in': mapped_body_types}
                print(f"🔍 DEBUG: added body type filter = {mapped_body_types}")
        
            print(f"🔍 DEBUG: clothing_filter = {clothing_filter}")
            
            # Выполняем запрос для одежды
            clothing_products = list(products_collection.find(clothing_filter).limit(limit))
            print(f"🔍 DEBUG: Найдено товаров одежды: {len(clothing_products)}")
            all_products.extend(clothing_products)
        
        # ЗАПРОС 2: Аксессуары и обувь (БЕЗ фильтров по размеру и типу фигуры)
        if accessory_categories:
            print("🔍 DEBUG: Выполняем запрос для аксессуаров...")
            
            # Простой фильтр только по категориям
            accessory_filter = {'category': {'$in': accessory_categories}}
            
            # Для обуви добавляем фильтр по размеру, если указан
            foot_size = survey_data.get('foot_size')
            if foot_size:
                foot_size_value = None
                if isinstance(foot_size, dict):
                    foot_size_value = foot_size.get('value', foot_size.get('label', ''))
                elif isinstance(foot_size, str):
                    foot_size_value = foot_size
                
                if foot_size_value:
                    print(f"🔍 DEBUG: Добавляем фильтр по размеру обуви: {foot_size_value}")
                    # Разделяем категории на обувь и сумки
                    shoe_categories = ['ботинки', 'сандалии', 'сапоги', 'туфли', 'балетки', 'сабо и мюли', 'кроссовки и кеды', 'босоножки', 'ботильоны']
                    bag_categories = ['сумки']
                    
                    # Создаем отдельные фильтры для обуви и сумок
                    shoe_filter = {
                        'category': {'$in': shoe_categories},
                        '$or': [
                            {'sizes.Российский': {'$regex': str(foot_size_value), '$options': 'i'}},
                            {'sizes.Производителя': {'$regex': str(foot_size_value), '$options': 'i'}}
                        ]
                    }
                    
                    bag_filter = {'category': {'$in': bag_categories}}
                    
                    # Выполняем два отдельных запроса
                    shoe_products = list(products_collection.find(shoe_filter).limit(limit))
                    bag_products = list(products_collection.find(bag_filter).limit(limit))
                    
                    print(f"🔍 DEBUG: Найдено обуви с размером {foot_size_value}: {len(shoe_products)}")
                    print(f"🔍 DEBUG: Найдено сумок: {len(bag_products)}")
                    
                    all_products.extend(shoe_products)
                    all_products.extend(bag_products)
                    return all_products
            else:
                print("🔍 DEBUG: Размер обуви не указан - показываем всю обувь и сумки")
            
            print(f"🔍 DEBUG: accessory_filter = {accessory_filter}")
        
            # Выполняем запрос для аксессуаров
            accessory_products = list(products_collection.find(accessory_filter).limit(limit))
            print(f"🔍 DEBUG: Найдено товаров аксессуаров: {len(accessory_products)}")
            all_products.extend(accessory_products)
        
        # Анализ результатов
        if all_products:
            category_counts = {}
            for product in all_products:
                category = product.get('category', 'Неизвестно')
                category_counts[category] = category_counts.get(category, 0) + 1
        
            print(f"🔍 Найденные категории товаров: {category_counts}")
        
            # Получаем все категории в базе данных для отладки
            all_categories = products_collection.distinct('category')
            print(f"🔍 Все категории в базе данных: {all_categories}")
        
        print(f"🔍 DEBUG: get_filtered_products returned {len(all_products)} products (запрошено {limit})")
        return all_products
        
    except Exception as e:
        print(f"❌ Ошибка при фильтрации товаров: {e}")
        return []

def generate_recommendations(survey_data, products):
    """Генерация рекомендаций с помощью гибридной модели (фильтрация + LLM)"""
    try:
        print(f"🔍 DEBUG: generate_recommendations called with {len(products)} products")
        
        # Если товары найдены, используем LLM для анализа и ранжирования
        if products:
            print(f"🔍 DEBUG: Found {len(products)} products, sending to LLM for analysis...")
            
            # Используем гибридную модель: фильтрация + LLM анализ
            llm_ranked_products = rank_products_with_llm(products, survey_data)
            
            if llm_ranked_products and len(llm_ranked_products) > 0:
                print(f"🔍 DEBUG: LLM analysis successful, returning {len(llm_ranked_products)} ranked products")
                
                # Преобразуем товары в формат для отображения
                formatted_products = []
                for i, product in enumerate(llm_ranked_products):
                    formatted_product = {
                        'name': product.get('name', 'Название не указано'),
                        'brand': product.get('brand', 'Бренд не указан'),
                        'price': product.get('price', 0),
                        'description': product.get('description', ''),
                        'imageUrl': product.get('imageUrl', ''),
                        'url': product.get('url', ''),
                        'category': product.get('category', ''),
                        'sizes': product.get('sizes', {})
                    }
                    formatted_products.append(formatted_product)
                
                return {
                    'type': 'products',
                    'products': formatted_products,
                    'count': len(formatted_products),
                    'total_available': len(products)
                }
            else:
                print(f"🔍 DEBUG: LLM analysis failed, returning basic products")
                # Если LLM не сработал, возвращаем базовые товары с ограничением по категориям
                limited_products = limit_products_by_category(products[:20], max_per_category=3, target_total=20)
                formatted_products = []
                for i, product in enumerate(limited_products):
                    formatted_product = {
                        'name': product.get('name', 'Название не указано'),
                        'brand': product.get('brand', 'Бренд не указан'),
                        'price': product.get('price', 0),
                        'description': product.get('description', ''),
                        'imageUrl': product.get('imageUrl', ''),
                        'url': product.get('url', ''),
                        'category': product.get('category', ''),
                        'sizes': product.get('sizes', {})
                    }
                    formatted_products.append(formatted_product)
                
                return {
                    'type': 'products',
                    'products': formatted_products,
                    'count': len(formatted_products),
                    'total_available': len(products)
                }
        else:
            print("🔍 DEBUG: No products found, returning message")
            # Если товары не найдены, возвращаем текстовое сообщение
            return {
                'type': 'message',
                'message': f"""
🎯 **Персональные рекомендации на основе вашей анкеты**

К сожалению, не найдено товаров, соответствующих вашим критериям.

**Возможные причины:**
- Слишком узкие критерии поиска
- Товары с указанными размерами отсутствуют в базе
- Несоответствие категорий товаров

**Рекомендации:**
1. Попробуйте изменить размеры в анкете
2. Выберите другие категории одежды
3. Обратитесь к нашему стилисту для персональной консультации
"""
            }
        
    except Exception as e:
        print(f"❌ Ошибка при генерации рекомендаций: {e}")
        return {
            'type': 'message',
            'message': "❌ Произошла ошибка при генерации рекомендаций."
        }

def generate_ranked_recommendations(survey_data, products, start_index=0, batch_size=20):
    """Генерация рекомендаций с новой логикой: LLM анализирует 100 товаров и выбирает топ-20"""
    try:
        print(f"🔍 DEBUG: generate_ranked_recommendations called with {len(products)} products")
        
        # Проверяем лимит генераций в сутки
        daily_generations = session.get('daily_generations', 0)
        last_generation_date = session.get('last_generation_date', '')
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Сбрасываем счетчик если новый день
        if last_generation_date != current_date:
            daily_generations = 0
            session['last_generation_date'] = current_date
        
        # Проверяем лимит (5 генераций в сутки)
        if daily_generations >= 5:
            # Вычисляем время до следующего дня
            now = datetime.now()
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            time_remaining = tomorrow - now
            
            hours = int(time_remaining.total_seconds() // 3600)
            minutes = int((time_remaining.total_seconds() % 3600) // 60)
            
            return {
                'type': 'limit_reached',
                'message': f'Достигнут дневной лимит генераций (5 раз). Следующий подбор будет доступен через {hours}ч {minutes}м.',
                'time_remaining': {
                    'hours': hours,
                    'minutes': minutes,
                    'total_seconds': int(time_remaining.total_seconds())
                }
            }
        
        # Получаем уже показанные товары (только ID)
        shown_product_ids = session.get('shown_product_ids', [])
        shown_ids_set = set(shown_product_ids)
        
        print(f"🔍 DEBUG: В сессии показано товаров: {len(shown_product_ids)}")
        print(f"🔍 DEBUG: ID показанных товаров в сессии: {shown_product_ids[:5]}...")
            
        # Фильтруем товары, исключая уже показанные
        available_products = [p for p in products if str(p.get('_id', '')) not in shown_ids_set]
            
        print(f"🔍 DEBUG: Доступных товаров после фильтрации: {len(available_products)}")
        print(f"🔍 DEBUG: Показанные ID (первые 5): {list(shown_ids_set)[:5]}")
        
        # Проверяем на повторения
        available_ids = [str(p.get('_id', '')) for p in available_products]
        duplicates = set(available_ids) & shown_ids_set
        if duplicates:
            print(f"🔍 DEBUG: НАЙДЕНЫ ПОВТОРЫ! Дубликаты: {list(duplicates)[:5]}")
        else:
            print(f"🔍 DEBUG: Повторов не найдено")
        
        # Проверяем категории в доступных товарах
        available_categories = {}
        for product in available_products:
            category = product.get('category', 'Другое').lower()
            if category not in available_categories:
                available_categories[category] = 0
            available_categories[category] += 1
        print(f"🔍 DEBUG: Категории в доступных товарах: {available_categories}")
        
        if len(available_products) < 20:
            return {
                'type': 'message',
                'message': 'Больше нет доступных товаров. Нажмите "Сбросить историю" для получения новых рекомендаций.'
            }
        
        # Берем первые 100 доступных товаров (уже отфильтрованных от показанных)
        products_for_llm = available_products[:100]
        
        print(f"🔍 DEBUG: LLM будет анализировать {len(products_for_llm)} новых товаров")
        
        # Проверяем, что в products_for_llm нет повторений
        llm_ids = [str(p.get('_id', '')) for p in products_for_llm]
        llm_duplicates = set(llm_ids) & shown_ids_set
        if llm_duplicates:
            print(f"🔍 DEBUG: ОШИБКА! В products_for_llm есть повторения: {list(llm_duplicates)[:5]}")
        else:
            print(f"🔍 DEBUG: products_for_llm не содержит повторений")
        
        # Проверяем, что все товары в products_for_llm действительно новые
        print(f"🔍 DEBUG: products_for_llm содержит {len(products_for_llm)} товаров")
        print(f"🔍 DEBUG: Первые 5 ID в products_for_llm: {llm_ids[:5]}")
        
        # LLM анализирует и выбирает топ-20 из НОВЫХ товаров
        # Определяем количество товаров для выборки (100 + 20 * номер генерации)
        generation_number = session.get('daily_generations', 0)
        products_to_select = 100 + (generation_number * 20)
        print(f"🔍 DEBUG: Генерация #{generation_number}, выбираем {products_to_select} товаров")
        
        # Исключаем показанные товары из исходного списка products
        available_for_llm = [p for p in products if str(p.get('_id', '')) not in shown_ids_set]
        print(f"🔍 DEBUG: После исключения {len(shown_ids_set)} показанных товаров осталось для LLM: {len(available_for_llm)} из {len(products)}")
        
        # Проверяем, что в available_for_llm нет показанных товаров
        available_ids = [str(p.get('_id', '')) for p in available_for_llm]
        duplicates = set(available_ids) & shown_ids_set
        if duplicates:
            print(f"🔍 DEBUG: ОШИБКА! В available_for_llm есть показанные товары: {list(duplicates)[:5]}")
        else:
            print(f"🔍 DEBUG: available_for_llm не содержит показанных товаров")
        
        if len(available_for_llm) < 10:
            print(f"🔍 DEBUG: Слишком мало товаров для LLM ({len(available_for_llm)}), используем fallback")
            return get_fallback_products(products)
        
        # Берем нужное количество товаров для LLM
        products_for_llm = available_for_llm[:products_to_select]
        print(f"🔍 DEBUG: Отправляем в LLM {len(products_for_llm)} товаров (из {len(available_for_llm)} доступных)")
        
        selected_products = rank_products_with_llm(products_for_llm, survey_data)
        
        # Отладка: проверяем ID товаров, которые выбрал LLM
        llm_selected_ids = [str(p.get('_id', '')) for p in selected_products]
        print(f"🔍 DEBUG: LLM выбрал товары с ID: {llm_selected_ids[:5]}...")
        
        # Проверяем, есть ли среди выбранных LLM товаров уже показанные
        llm_duplicates = set(llm_selected_ids) & shown_ids_set
        if llm_duplicates:
            print(f"🔍 DEBUG: LLM ВЫБРАЛ ПОВТОРНЫЕ ТОВАРЫ: {list(llm_duplicates)[:5]}")
            print(f"🔍 DEBUG: Показанные ID в сессии: {list(shown_ids_set)[:10]}")
        else:
            print(f"🔍 DEBUG: LLM не выбрал повторные товары")
        
        # Проверяем, все ли выбранные товары действительно из products_for_llm
        products_for_llm_ids = {str(p.get('_id', '')) for p in products_for_llm}
        invalid_selections = set(llm_selected_ids) - products_for_llm_ids
        if invalid_selections:
            print(f"🔍 DEBUG: LLM выбрал товары НЕ из products_for_llm: {list(invalid_selections)[:5]}")
        else:
            print(f"🔍 DEBUG: Все выбранные товары из products_for_llm")
        
        if not selected_products or len(selected_products) == 0:
            # Если LLM не выбрал товары, берем первые 20 доступных новых
            selected_products = products_for_llm[:20]
            print(f"🔍 DEBUG: LLM не выбрал товары, используем первые 20 доступных новых")
        
        # Ограничиваем до 20 товаров
        selected_products = selected_products[:20]
        
        # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Исключаем товары, которые уже были показаны
        final_products = []
        for product in selected_products:
            product_id = str(product.get('_id', ''))
            if product_id not in shown_ids_set:
                final_products.append(product)
            else:
                print(f"🔍 DEBUG: Исключен повторный товар: {product_id}")
        
        print(f"🔍 DEBUG: После исключения повторений осталось товаров: {len(final_products)}")
        
        # Если после исключения повторений товаров меньше 20, добавляем из доступных
        if len(final_products) < 20:
            remaining_needed = 20 - len(final_products)
            for product in products_for_llm:
                if len(final_products) >= 20:
                    break
                product_id = str(product.get('_id', ''))
                if product_id not in shown_ids_set and product not in final_products:
                    final_products.append(product)
            
            print(f"🔍 DEBUG: Добавлено товаров из доступных: {len(final_products)}")
        
        selected_products = final_products
        
        # Гарантируем минимум 1 товар из каждой категории пользователя
        selected_products = ensure_minimum_per_category(selected_products, survey_data, 20)
        
        print(f"🔍 DEBUG: LLM выбрал {len(selected_products)} новых товаров")
        
        # Добавляем только ID выбранных товаров в список показанных (для экономии места в сессии)
        shown_product_ids = session.get('shown_product_ids', [])
        print(f"🔍 DEBUG: До добавления в сессии товаров: {len(shown_product_ids)}")
        
        for product in selected_products:
            product_id = str(product.get('_id', ''))
            if product_id not in shown_product_ids:
                shown_product_ids.append(product_id)
                print(f"🔍 DEBUG: Добавлен в сессию: {product_id}")
            else:
                print(f"🔍 DEBUG: УЖЕ В СЕССИИ: {product_id}")
        
        session['shown_product_ids'] = shown_product_ids
        print(f"🔍 DEBUG: После добавления в сессии товаров: {len(session['shown_product_ids'])}")
        
        # Увеличиваем счетчик генераций
        daily_generations += 1
        session['daily_generations'] = daily_generations
        
        # Принудительно сохраняем сессию
        session.modified = True
        
        print(f"🔍 DEBUG: Выбрано {len(selected_products)} новых товаров, генерация #{daily_generations}/5")
        print(f"🔍 DEBUG: Сохранено в сессии ID товаров: {len(session.get('shown_product_ids', []))}")
        print(f"🔍 DEBUG: ID сохраненных товаров: {session.get('shown_product_ids', [])[:3]}...")
        
        # Преобразуем товары в формат для отображения
        formatted_products = []
        for product in selected_products:
            formatted_product = {
                'name': product.get('name', 'Название не указано'),
                'brand': product.get('brand', 'Бренд не указан'),
                'price': product.get('price', 0),
                'description': product.get('description', ''),
                'imageUrl': product.get('imageUrl', ''),
                'url': product.get('url', ''),
                'category': product.get('category', ''),
                'sizes': product.get('sizes', {})
            }
            formatted_products.append(formatted_product)
        
        # Группируем товары по категориям
        grouped_products = group_products_by_category(formatted_products)
        
        return {
            'type': 'products',
            'products': grouped_products,  # Теперь это группы, а не простой список
            'count': len(formatted_products),
            'generations_used': daily_generations,
            'generations_remaining': 5 - daily_generations
        }
        
    except Exception as e:
        print(f"❌ Ошибка при генерации ранжированных рекомендаций: {str(e)}")
        return {
            'type': 'message',
            'message': 'Произошла ошибка при подборе рекомендаций. Попробуйте позже.'
        }

def format_survey_context(survey_data):
    """Форматирование данных анкеты для контекста"""
    context_parts = []
    
    if survey_data.get('style_preferences'):
        if isinstance(survey_data['style_preferences'], dict) and survey_data['style_preferences'].get('values'):
            styles = [item['label'] for item in survey_data['style_preferences']['values']]
            context_parts.append(f"Стиль: {', '.join(styles)}")
        elif isinstance(survey_data['style_preferences'], list):
            context_parts.append(f"Стиль: {', '.join(survey_data['style_preferences'])}")
    
    if survey_data.get('color_preferences'):
        if isinstance(survey_data['color_preferences'], dict) and survey_data['color_preferences'].get('values'):
            colors = [item['label'] for item in survey_data['color_preferences']['values']]
            context_parts.append(f"Цвета: {', '.join(colors)}")
        elif isinstance(survey_data['color_preferences'], list):
            context_parts.append(f"Цвета: {', '.join(survey_data['color_preferences'])}")
    
    if survey_data.get('body_type'):
        if isinstance(survey_data['body_type'], dict):
            context_parts.append(f"Тип фигуры: {survey_data['body_type'].get('label', 'Не указан')}")
        else:
            context_parts.append(f"Тип фигуры: {survey_data['body_type']}")
    
    if survey_data.get('top_size'):
        context_parts.append(f"Размер верха: {survey_data['top_size']}")
    
    if survey_data.get('bottom_size'):
        context_parts.append(f"Размер низа: {survey_data['bottom_size']}")
    
    if survey_data.get('height'):
        if isinstance(survey_data['height'], dict):
            context_parts.append(f"Рост: {survey_data['height'].get('value', 'Не указан')} см")
        else:
            context_parts.append(f"Рост: {survey_data['height']} см")
    
    return "\n".join(context_parts) if context_parts else "Данные анкеты неполные"

def format_products_info(products):
    """Форматирование информации о товарах"""
    if not products:
        return "Товары не найдены"
    
    products_info = []
    for i, product in enumerate(products[:10], 1):  # Показываем первые 10
        name = product.get('name', 'Без названия')
        category = product.get('category', 'Не указана')
        price = product.get('price', 'Цена не указана')
        products_info.append(f"{i}. {name} ({category}) - {price}")
    
    return "\n".join(products_info)

def limit_products_by_category(products, max_per_category=4, target_total=20):
    """
    Ограничивает количество товаров в каждой категории и возвращает ровно target_total товаров
    для обеспечения разнообразия в рекомендациях
    """
    try:
        # Группируем товары по категориям
        categories = {}
        for product in products:
            category = product.get('category', 'Другое')
            if category not in categories:
                categories[category] = []
            categories[category].append(product)
        
        print(f"🔍 DEBUG: Found categories in products: {list(categories.keys())}")
        print(f"🔍 DEBUG: Products per category: {[(cat, len(prods)) for cat, prods in categories.items()]}")
        
        # Ограничиваем количество товаров в каждой категории
        limited_products = []
        for category, category_products in categories.items():
            # Берем максимум max_per_category товаров из каждой категории
            limited_products.extend(category_products[:max_per_category])
            print(f"🔍 DEBUG: Category '{category}': {len(category_products)} -> {min(len(category_products), max_per_category)}")
        
        # Если получилось больше target_total товаров, берем первые target_total
        if len(limited_products) > target_total:
            limited_products = limited_products[:target_total]
            print(f"🔍 DEBUG: Ограничили до {target_total} товаров")
        
        print(f"🔍 DEBUG: Ограничение по категориям - было {len(products)} товаров, стало {len(limited_products)}")
        print(f"🔍 DEBUG: Категории: {list(categories.keys())}")
        
        return limited_products
        
    except Exception as e:
        print(f"❌ Ошибка при ограничении товаров по категориям: {e}")
        return products[:target_total] if len(products) > target_total else products

def ensure_minimum_per_category(products, survey_data, target_total=20):
    """Гарантирует минимум 1 товар из каждой категории, указанной пользователем"""
    try:
        # Получаем категории из анкеты пользователя
        user_categories = set()
        
        # Функция для извлечения значений (копируем из get_filtered_products)
        def extract_values(data):
            values = []
            if isinstance(data, dict):
                if 'values' in data:
                    for item in data['values']:
                        if isinstance(item, dict) and 'value' in item:
                            values.append(item['value'])
                        elif isinstance(item, str):
                            values.append(item)
                elif 'value' in data:
                    values.append(data['value'])
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and 'value' in item:
                        values.append(item['value'])
                    elif isinstance(item, str):
                        values.append(item)
            return values
        
        # Извлекаем категории из анкеты
        for field in ['top_clothing', 'bottom_clothing', 'additional_items']:
            if survey_data.get(field):
                values = extract_values(survey_data[field])
                user_categories.update(values)
                print(f"🔍 DEBUG: Извлечено из {field}: {values}")
        
        print(f"🔍 DEBUG: Категории пользователя: {user_categories}")
        
        # Маппинг категорий
        category_mapping = {
            'dresses': ['платья и сарафаны'],
            'blouses': ['блузы и рубашки'],
            'shirts': ['блузы и рубашки'],
            'sweaters': ['свитеры'],
            'sweatshirts': ['свитшоты'],
            'longsleeves': ['лонгсливы'],
            'tshirts': ['футболки'],
            'jackets': ['пиджаки'],
            'hoodies': ['худи'],
            'cardigans': ['кардиганы'],
            'turtlenecks': ['водолазки'],
            'pants': ['брюки'],
            'jeans': ['джинсы'],
            'skirts': ['юбки'],
            'shorts': ['шорты'],
            'shoes': ['ботинки', 'сандалии', 'сапоги', 'туфли', 'балетки', 'сабо и мюли', 'кроссовки и кеды', 'босоножки', 'ботильоны'],
            'bags': ['сумки'],
            'jewelry': ['украшения'],
            'accessories': ['аксессуары']
        }
        
        # Определяем целевые категории в базе данных
        target_db_categories = set()
        for user_cat in user_categories:
            if user_cat in category_mapping:
                target_db_categories.update(category_mapping[user_cat])
        
        print(f"🔍 DEBUG: Целевые категории в БД: {target_db_categories}")
        
        # Группируем товары по категориям
        categories = {}
        for product in products:
            category = product.get('category', 'Другое').lower()
            if category not in categories:
                categories[category] = []
            categories[category].append(product)
        
        # Выбираем товары, гарантируя минимум 1 из каждой категории
        selected_products = []
        remaining_slots = target_total
        
        # Сначала выбираем по 1 товару из каждой категории пользователя
        for db_category in target_db_categories:
            if db_category in categories and categories[db_category]:
                selected_products.append(categories[db_category][0])
                remaining_slots -= 1
                print(f"🔍 DEBUG: Добавлен товар из категории '{db_category}'")
        
        # Затем заполняем оставшиеся слоты
        all_remaining_products = []
        for category_products in categories.values():
            all_remaining_products.extend(category_products[1:])  # Пропускаем первый, уже выбранный
        
        # Сортируем по релевантности (можно добавить дополнительную логику)
        import random
        random.shuffle(all_remaining_products)
        
        # Добавляем оставшиеся товары
        selected_products.extend(all_remaining_products[:remaining_slots])
        
        print(f"🔍 DEBUG: Выбрано товаров: {len(selected_products)}")
        print(f"🔍 DEBUG: Категории в результате: {set(p.get('category', 'Другое').lower() for p in selected_products)}")
        
        return selected_products
        
    except Exception as e:
        print(f"❌ Ошибка при обеспечении минимума по категориям: {e}")
        return products[:target_total] if len(products) > target_total else products

@app.route('/check_categories', methods=['GET'])
def check_categories():
    """Проверяет доступные категории в базе данных"""
    try:
        # Подключение к MongoDB
        client = MongoClient(mongo_config.mongo_config.mongo_uri)
        db = client[mongo_config.mongo_config.database_name]
        products_collection = db["products_enhanced"]
        
        # Получаем все уникальные категории
        categories = products_collection.distinct("category")
        
        # Подсчитываем количество товаров в каждой категории
        category_counts = {}
        for category in categories:
            count = products_collection.count_documents({"category": category})
            category_counts[category] = count
        
        client.close()
        
        return jsonify({
            'success': True,
            'categories': categories,
            'category_counts': category_counts,
            'total_categories': len(categories)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/check_body_types', methods=['GET'])
def check_body_types():
    """Проверяет доступные типы фигуры в базе данных"""
    try:
        # Подключение к MongoDB
        client = MongoClient(mongo_config.mongo_config.mongo_uri)
        db = client[mongo_config.mongo_config.database_name]
        products_collection = db["products_enhanced"]
        
        # Получаем все товары
        products = list(products_collection.find({}, {"bodyTypes": 1}))
        
        # Анализируем типы фигуры
        body_types = {}
        for product in products:
            product_body_types = product.get('bodyTypes', [])
            if isinstance(product_body_types, str):
                product_body_types = [product_body_types]
            elif not isinstance(product_body_types, list):
                product_body_types = []
            
            for body_type in product_body_types:
                if body_type not in body_types:
                    body_types[body_type] = 0
                body_types[body_type] += 1
        
        client.close()
        
        return jsonify({
            'success': True,
            'body_types': body_types,
            'total_body_types': len(body_types)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/check_body_types_by_category', methods=['GET'])
def check_body_types_by_category():
    """Проверяет доступные типы фигуры по категориям в базе данных"""
    try:
        # Подключение к MongoDB
        client = MongoClient(mongo_config.mongo_config.mongo_uri)
        db = client[mongo_config.mongo_config.database_name]
        products_collection = db["products_enhanced"]
        
        # Получаем все товары
        products = list(products_collection.find({}, {"bodyTypes": 1, "category": 1}))
        
        # Анализируем типы фигуры по категориям
        category_body_types = {}
        for product in products:
            category = product.get('category', 'Другое')
            product_body_types = product.get('bodyTypes', [])
            if isinstance(product_body_types, str):
                product_body_types = [product_body_types]
            elif not isinstance(product_body_types, list):
                product_body_types = []
            
            if category not in category_body_types:
                category_body_types[category] = {}
            
            for body_type in product_body_types:
                if body_type not in category_body_types[category]:
                    category_body_types[category][body_type] = 0
                category_body_types[category][body_type] += 1
        
        client.close()
        
        return jsonify({
            'success': True,
            'category_body_types': category_body_types
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/check_sizes_for_body_type', methods=['GET'])
def check_sizes_for_body_type():
    """Проверяет доступные размеры для конкретного типа фигуры"""
    try:
        body_type = request.args.get('body_type', 'Груша')
        
        # Подключение к MongoDB
        client = MongoClient(mongo_config.mongo_config.mongo_uri)
        db = client[mongo_config.mongo_config.database_name]
        products_collection = db["products_enhanced"]
        
        # Получаем товары для конкретного типа фигуры
        products = list(products_collection.find(
            {"bodyTypes": {"$in": [body_type]}}, 
            {"sizes": 1, "category": 1, "name": 1}
        ))
        
        print(f"🔍 DEBUG: Найдено товаров для типа '{body_type}': {len(products)}")
        
        # Анализируем размеры
        sizes_analysis = {}
        for product in products:
            category = product.get('category', 'Другое')
            sizes = product.get('sizes', {})
            
            if category not in sizes_analysis:
                sizes_analysis[category] = {'products': 0, 'sizes': {}}
            
            sizes_analysis[category]['products'] += 1
            
            # Анализируем российские размеры
            russian_sizes = sizes.get('Российский', [])
            if isinstance(russian_sizes, str):
                russian_sizes = [russian_sizes]
            elif not isinstance(russian_sizes, list):
                russian_sizes = []
            
            for size in russian_sizes:
                if size not in sizes_analysis[category]['sizes']:
                    sizes_analysis[category]['sizes'][size] = 0
                sizes_analysis[category]['sizes'][size] += 1
        
        client.close()
        
        return jsonify({
            'success': True,
            'body_type': body_type,
            'sizes_analysis': sizes_analysis,
            'total_products': len(products)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/debug_product_structure', methods=['GET'])
def debug_product_structure():
    """Отладочная функция для проверки структуры данных"""
    try:
        # Подключение к MongoDB
        client = MongoClient(mongo_config.mongo_config.mongo_uri)
        db = client[mongo_config.mongo_config.database_name]
        products_collection = db["products_enhanced"]
        
        # Получаем несколько товаров для анализа
        products = list(products_collection.find({}, {"bodyTypes": 1, "sizes": 1, "category": 1, "name": 1}).limit(5))
        
        # Анализируем структуру
        analysis = []
        for product in products:
            analysis.append({
                'name': product.get('name', 'N/A'),
                'category': product.get('category', 'N/A'),
                'bodyTypes': product.get('bodyTypes', 'N/A'),
                'bodyTypes_type': type(product.get('bodyTypes')).__name__,
                'sizes': product.get('sizes', 'N/A'),
                'sizes_type': type(product.get('sizes')).__name__
            })
        
        client.close()
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/debug_pear_products', methods=['GET'])
def debug_pear_products():
    """Отладочная функция для проверки товаров типа 'Груша'"""
    try:
        # Подключение к MongoDB
        client = MongoClient(mongo_config.mongo_config.mongo_uri)
        db = client[mongo_config.mongo_config.database_name]
        products_collection = db["products_enhanced"]
        
        # Проверяем разные способы поиска
        total_products = products_collection.count_documents({})
        pear_products_exact = list(products_collection.find({"bodyTypes": "Груша"}, {"name": 1, "category": 1, "bodyTypes": 1}).limit(3))
        pear_products_in = list(products_collection.find({"bodyTypes": {"$in": ["Груша"]}}, {"name": 1, "category": 1, "bodyTypes": 1}).limit(3))
        pear_products_regex = list(products_collection.find({"bodyTypes": {"$regex": "Груша"}}, {"name": 1, "category": 1, "bodyTypes": 1}).limit(3))
        
        # Получаем несколько товаров с типом "Груша" для анализа
        sample_pear_products = list(products_collection.find({"bodyTypes": "Груша"}, {"name": 1, "category": 1, "bodyTypes": 1, "sizes": 1}).limit(3))
        
        # Анализируем размеры для товаров типа "Груша"
        pear_sizes_analysis = {}
        pear_products_with_sizes = list(products_collection.find({"bodyTypes": "Груша"}, {"sizes": 1, "category": 1}))
        
        for product in pear_products_with_sizes:
            category = product.get('category', 'Другое')
            sizes = product.get('sizes', {})
            
            if category not in pear_sizes_analysis:
                pear_sizes_analysis[category] = {'products': 0, 'sizes': {}}
            
            pear_sizes_analysis[category]['products'] += 1
            
            # Анализируем российские размеры
            russian_sizes = sizes.get('Российский', [])
            if isinstance(russian_sizes, str):
                russian_sizes = [russian_sizes]
            elif not isinstance(russian_sizes, list):
                russian_sizes = []
            
            for size in russian_sizes:
                if size not in pear_sizes_analysis[category]['sizes']:
                    pear_sizes_analysis[category]['sizes'][size] = 0
                pear_sizes_analysis[category]['sizes'][size] += 1
        
        client.close()
        
        # Очищаем данные от ObjectId
        def clean_for_json(obj):
            if isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items() if k != '_id'}
            elif isinstance(obj, list):
                return [clean_for_json(item) for item in obj]
            else:
                return obj
        
        return jsonify({
            'success': True,
            'total_products_in_db': total_products,
            'pear_products_exact_count': len(pear_products_exact),
            'pear_products_in_count': len(pear_products_in),
            'pear_products_regex_count': len(pear_products_regex),
            'sample_pear_products': clean_for_json(sample_pear_products),
            'pear_sizes_analysis': pear_sizes_analysis
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def group_products_by_category(products):
    """Группирует товары по категориям с заголовками и описаниями"""
    groups = {
        'dresses': {
            'title': '👗 Платья',
            'description': 'Элегантные платья для любого случая',
            'products': []
        },
        'tops': {
            'title': '👚 Блузки, рубашки, футболки',
            'description': 'Блузки, рубашки, футболки и другие верхи',
            'products': []
        },
        'bottoms': {
            'title': '👖 Юбки, джинсы, брюки и шорты',
            'description': 'Юбки, джинсы, брюки и шорты',
            'products': []
        },
        'shoes_and_bags': {
            'title': '👠 Обувь и сумки',
            'description': 'Туфли, ботинки, сумки и другие аксессуары',
            'products': []
        },
        'accessories': {
            'title': '👜 Аксессуары',
            'description': 'Украшения и другие аксессуары',
            'products': []
        }
    }
    
    # Маппинг категорий базы данных к группам
    category_mapping = {
        # Платья
        'платья и сарафаны': 'dresses',
        
        # Верхняя одежда
        'блузы и рубашки': 'tops',
        'футболки': 'tops',
        'пиджаки': 'tops',
        'худи': 'tops',
        
        # Нижняя одежда
        'юбки': 'bottoms',
        'джинсы': 'bottoms',
        'брюки': 'bottoms',
        'шорты': 'bottoms',
        
        # Обувь и сумки
        'ботинки': 'shoes_and_bags',
        'сандалии': 'shoes_and_bags',
        'сапоги': 'shoes_and_bags',
        'туфли': 'shoes_and_bags',
        'балетки': 'shoes_and_bags',
        'сабо и мюли': 'shoes_and_bags',
        'кроссовки и кеды': 'shoes_and_bags',
        'босоножки': 'shoes_and_bags',
        'ботильоны': 'shoes_and_bags',
        'сумки': 'shoes_and_bags',
        
        # Аксессуары
        'украшения': 'accessories'
    }
    
    # Группируем товары
    for product in products:
        category = product.get('category', '').lower()
        group = category_mapping.get(category, 'tops')  # По умолчанию в верхи
        groups[group]['products'].append(product)
    
    # Убираем пустые группы и устанавливаем порядок отображения
    result = []
    # Фиксированный порядок: платья → верха → низы → обувь и сумки → аксессуары
    order = ['dresses', 'tops', 'bottoms', 'shoes_and_bags', 'accessories']
    
    for group_key in order:
        if group_key in groups and groups[group_key]['products']:
            result.append(groups[group_key])
    
    return result

# API для управления предварительными подписками
@app.route('/admin/pre_subscriptions', methods=['POST'])
def add_pre_subscription():
    """Добавляет предварительную подписку (только для админов)"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        subscription_end_str = data.get('subscription_end', '').strip()
        source = data.get('source', 'manual')
        notes = data.get('notes')
        
        if not email or not subscription_end_str:
            return jsonify({'error': 'Email и дата окончания подписки обязательны'}), 400
        
        # Парсим дату окончания подписки
        try:
            subscription_end = datetime.strptime(subscription_end_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Неверный формат даты. Используйте YYYY-MM-DD'}), 400
        
        # Подключаемся к MongoDB
        if not user_auth.connect():
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
        
        # Добавляем предварительную подписку
        result = user_auth.add_pre_subscription(email, subscription_end, source, notes)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Предварительная подписка добавлена',
                'subscription_id': result['subscription_id']
            })
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        logger.error(f"Ошибка добавления предварительной подписки: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/admin/pre_subscriptions', methods=['GET'])
def list_pre_subscriptions():
    """Получает список предварительных подписок (только для админов)"""
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        
        # Подключаемся к MongoDB
        if not user_auth.connect():
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
        
        # Получаем список предварительных подписок
        result = user_auth.list_pre_subscriptions(active_only)
        
        if result['success']:
            return jsonify({
                'success': True,
                'subscriptions': result['subscriptions'],
                'count': result['count']
            })
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        logger.error(f"Ошибка получения списка предварительных подписок: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/admin/pre_subscriptions/<email>', methods=['DELETE'])
def remove_pre_subscription(email):
    """Удаляет предварительную подписку (только для админов)"""
    try:
        # Подключаемся к MongoDB
        if not user_auth.connect():
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
        
        # Удаляем предварительную подписку
        result = user_auth.remove_pre_subscription(email)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Предварительная подписка удалена'
            })
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        logger.error(f"Ошибка удаления предварительной подписки: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/admin/pre_subscriptions/cleanup', methods=['POST'])
def cleanup_expired_pre_subscriptions():
    """Очищает истекшие предварительные подписки (только для админов)"""
    try:
        # Подключаемся к MongoDB
        if not user_auth.connect():
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
        
        # Очищаем истекшие предварительные подписки
        result = user_auth.cleanup_expired_pre_subscriptions()
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'Очищено {result["cleaned_count"]} истекших предварительных подписок',
                'cleaned_count': result['cleaned_count']
            })
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        logger.error(f"Ошибка очистки истекших предварительных подписок: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/admin/pre_subscriptions/check/<email>', methods=['GET'])
def check_pre_subscription(email):
    """Проверяет наличие предварительной подписки для email (только для админов)"""
    try:
        # Подключаемся к MongoDB
        if not user_auth.connect():
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
        
        # Проверяем предварительную подписку
        result = user_auth.get_pre_subscription(email)
        
        if result['success']:
            return jsonify({
                'success': True,
                'subscription': result['subscription']
            })
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            })
            
    except Exception as e:
        logger.error(f"Ошибка проверки предварительной подписки: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)