from flask import Flask, request, jsonify, render_template, send_file, session
import os
from werkzeug.utils import secure_filename
from color_analysis import ColorAnalyzer
from pdf_report import generate_pdf_report
import cv2
import json
from config import CLOUDPAYMENTS_PUBLIC_ID, UNISENDER_API_KEY, UNISENDER_LIST_ID, UNISENDER_GO_API_KEY
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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic', 'heif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_to_jpg(image_path):
    """Конвертирует изображение в JPG формат"""
    try:
        with Image.open(image_path) as img:
            # Если изображение в формате RGBA, конвертируем в RGB
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Сохраняем как JPG
            jpg_path = os.path.splitext(image_path)[0] + '.jpg'
            img.save(jpg_path, 'JPEG', quality=95)
            return jpg_path
    except Exception as e:
        logger.error(f"Ошибка при конвертации изображения: {str(e)}")
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

def fix_orientation_pillow(image):
    try:
        exif = image._getexif()
        if exif is not None:
            orientation_key = next(
                k for k, v in ExifTags.TAGS.items() if v == 'Orientation'
            )
            orientation = exif.get(orientation_key, 1)
            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except Exception as e:
        print('EXIF orientation error:', e)
    return image

@app.route('/')
def index():
    return render_template('index.html', config={'CLOUDPAYMENTS_PUBLIC_ID': CLOUDPAYMENTS_PUBLIC_ID})

@app.route('/payment-success')
def payment_success():
    return render_template('payment_success.html')

@app.route('/analyze', methods=['POST', 'GET'])
def analyze():
    # Если это GET-запрос и запрошен PDF
    if request.method == 'GET' and ('pdf' in request.args or request.args.get('pdf') == '1'):
        if 'last_analysis' in session and 'last_image_path' in session:
            analysis = session['last_analysis']
            image_path = session['last_image_path']
            filename_wo_ext = os.path.splitext(os.path.basename(image_path))[0].lower()
            pdf_path = os.path.join('static/reports', f'report_{filename_wo_ext}.pdf')
            full_pdf_path = generate_pdf_report(analysis, image_path, output_path=pdf_path)
            return send_file(
                full_pdf_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=os.path.basename(full_pdf_path)
            )
        return jsonify({'error': 'No analysis found'}), 400

    if 'image' not in request.files:
        # Если нет изображения, но запрошен PDF — используем кэш анализа
        if ('pdf' in request.form or request.args.get('pdf') == '1') and 'last_analysis' in session and 'last_image_path' in session:
            analysis = session['last_analysis']
            image_path = session['last_image_path']
            filename_wo_ext = os.path.splitext(os.path.basename(image_path))[0].lower()
            pdf_path = os.path.join('static/reports', f'report_{filename_wo_ext}.pdf')
            full_pdf_path = generate_pdf_report(analysis, image_path, output_path=pdf_path)
            return send_file(
                full_pdf_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=os.path.basename(full_pdf_path)
            )
        return jsonify({'error': 'No image uploaded'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': f'Неподдерживаемый формат файла. Поддерживаемые форматы: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    try:
        # Сохраняем файл
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        logger.info(f"Файл сохранен: {filepath}")
        logger.info(f"Размер файла: {os.path.getsize(filepath)} байт")

        # Проверяем и конвертируем изображение если нужно
        try:
            with Image.open(filepath) as img:
                logger.info(f"Формат изображения: {img.format}")
                logger.info(f"Размер: {img.size}")
                logger.info(f"Режим: {img.mode}")
                img = fix_orientation_pillow(img)
                img.save(filepath)
        except UnidentifiedImageError:
            logger.error(f"Неподдерживаемый формат изображения: {filepath}")
            # cleanup_temp_files(filepath)
            return jsonify({'error': 'Неподдерживаемый формат изображения'}), 400
        except Exception as e:
            logger.error(f"Ошибка при открытии изображения: {str(e)}")
            # cleanup_temp_files(filepath)
            return jsonify({'error': 'Ошибка при обработке изображения'}), 400

        # Конвертируем в JPG если это не JPG
        original_filepath = filepath
        if not filename.lower().endswith(('.jpg', '.jpeg')):
            try:
                jpg_path = convert_to_jpg(filepath)
                # cleanup_temp_files(filepath)  # Удаляем оригинальный файл
                filepath = jpg_path
                logger.info(f"Изображение сконвертировано в JPG: {filepath}")
            except Exception as e:
                logger.error(f"Ошибка при конвертации в JPG: {str(e)}")
                # cleanup_temp_files(filepath)
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
            "from_name": "Color Type AI",
            "subject": "Ваш персональный цветовой гайд",
            "body": {
                "html": (
                    "<html><body>"
                    "<p>Здравствуйте!<br><br>"
                    "Спасибо за приобретение персонального цветового гайда.<br>"
                    f"Скачать ваш гайд можно по <a href=\"{pdf_url}\">ссылке</a>.<br><br>"
                    "С уважением,<br>"
                    "Color Type AI<br><br>"
                    "<a href=\"https://noreply.stylebox.live/ru/go2_unsubscribe\" style=\"color:#7C3AED;\">Отписаться от рассылки</a>"
                    "</p></body></html>"
                ),
                "plaintext": "Здравствуйте! Спасибо за приобретение персонального цветового гайда. Ссылка на ваш гайд: {pdf_url}".format(pdf_url=pdf_url)
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

С уважением,
Color Type AI
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
    analysis_path = f'static/reports/last_analysis_{analysis_id}.json'
    image_path = f'static/reports/last_image_{analysis_id}.jpg'
    pdf_path = f'static/reports/report_{normalize_email(email)}_{analysis_id}.pdf'
    print("[paid_callback] Analysis path:", analysis_path, "Exists:", os.path.exists(analysis_path))
    print("[paid_callback] Image path:", image_path, "Exists:", os.path.exists(image_path))
    print("[paid_callback] PDF path:", pdf_path)
    
    if status == 'completed':
        # Получаем email и analysis_id из данных
        if not email or not analysis_id:
            print("Missing required data:", {'email': email, 'analysis_id': analysis_id})
            return jsonify({'code': 10, 'message': 'No email or analysis_id'}), 400

        # Проверяем наличие файлов анализа и изображения
        if os.path.exists(analysis_path) and os.path.exists(image_path):
            try:
                # Загружаем данные анализа
                with open(analysis_path) as f:
                    analysis = json.load(f)
                # Генерируем PDF
                print("Generating PDF report...")
                full_pdf_path = generate_pdf_report(analysis, image_path, output_path=pdf_path)
                # Ждём, пока файл полностью создастся
                if not wait_for_file_complete(full_pdf_path):
                    print("PDF не был полностью создан вовремя!")
                    send_guide_email_apology(email)
                    return jsonify({'code': 11, 'message': 'PDF generation failed'}), 500
                # Явная проверка после merge
                if os.path.exists(full_pdf_path):
                    file_size = os.path.getsize(full_pdf_path)
                    print(f"PDF готов к отправке, размер: {file_size} байт")
                else:
                    print("PDF не найден после merge!")
                # Проверяем, что PDF создался
                if os.path.exists(full_pdf_path) and os.path.getsize(full_pdf_path) > 10*1024:
                    print("PDF generated successfully, sending email...")
                    # Отправляем email
                    if send_guide_email(email, full_pdf_path):
                        print("Email sent successfully!")
                        return jsonify({'code': 0, 'message': 'Success'})
                    else:
                        print("Failed to send email")
                        return jsonify({'code': 12, 'message': 'Failed to send email'}), 500
                else:
                    print("PDF was not generated or too small")
                    return jsonify({'code': 11, 'message': 'PDF generation failed'}), 500
            except Exception as e:
                print(f"Error processing payment: {str(e)}")
                return jsonify({'code': 14, 'message': f'Processing error: {str(e)}'}), 500
        else:
            print(f"Files not found:\n- Analysis exists: {os.path.exists(analysis_path)}\n- Image exists: {os.path.exists(image_path)}")
            return jsonify({'code': 11, 'message': 'Analysis or image not found'}), 404
    else:
        print(f"Payment not completed, status: {status}")
        return jsonify({'code': 13, 'message': 'Payment not completed'}), 200

def normalize_email(email):
    return ''.join(c for c in email if c.isalnum())

# --- Проверка email в Google Spreadsheet ---
# Укажи GOOGLE_SHEET_ID в .env (ID таблицы из URL)
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
GOOGLE_SHEET_RANGE = os.environ.get('GOOGLE_SHEET_RANGE', 'A:A')  # Первый столбец
GOOGLE_SHEET_WORKSHEET = os.environ.get('GOOGLE_SHEET_WORKSHEET', 'Лист1')  # Имя листа (Sheet1/Лист1)
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE', 'google_service_account.json')

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 