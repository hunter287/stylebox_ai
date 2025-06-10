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

@app.route('/')
def index():
    return render_template('index.html', config={'CLOUDPAYMENTS_PUBLIC_ID': CLOUDPAYMENTS_PUBLIC_ID})

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
    
    try:
        # Сохраняем файл
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        # Проверяем имя файла: если это цветотип, возвращаем готовый результат
        filename_wo_ext = os.path.splitext(file.filename)[0].lower()
        analyzer = ColorAnalyzer()
        if filename_wo_ext in PRESET_COLOR_TYPES:
            print("DEBUG: Using preset analysis for", filename_wo_ext)
            preset_result = analyzer.get_preset_analysis(filename_wo_ext)
            print("DEBUG: Preset result:", preset_result)
            # Добавляем основные палитры для совместимости с фронтом
            preset_result["main_palette_hex"] = preset_result.get("bright_colors_hex", [])[:9]
            preset_result["additional_palette_hex"] = preset_result.get("bright_colors_hex", [])
            session['last_analysis'] = preset_result
            session['last_image_path'] = filepath
            if 'pdf' in request.form or request.args.get('pdf') == '1':
                pdf_path = os.path.join('static/reports', f'report_{filename_wo_ext}.pdf')
                full_pdf_path = generate_pdf_report(preset_result, filepath, output_path=pdf_path)
                return send_file(
                    full_pdf_path,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=os.path.basename(full_pdf_path)
                )
            return jsonify(preset_result)

        # Обычный анализ изображения
        result = analyzer.analyze_image(filepath)
        print("\n=== ANALYZE RESULT ===\n" + json.dumps(result, ensure_ascii=False, indent=2))
        session['last_analysis'] = result
        session['last_image_path'] = filepath
        # --- Генерируем analysis_id и сохраняем анализ/изображение по нему ---
        analysis_id = str(uuid.uuid4())
        result['analysis_id'] = analysis_id
        with open(f'static/reports/last_analysis_{analysis_id}.json', 'w') as f:
            json.dump(result, f)
        shutil.copyfile(filepath, f'static/reports/last_image_{analysis_id}.jpg')
        # Возвращаем analysis_id клиенту
        return jsonify({**result, 'analysis_id': analysis_id})
    except Exception as e:
        print('ERROR in /analyze:', e)
        if 'filepath' in locals() and os.path.exists(filepath):
            pass
        return jsonify({'error': str(e)}), 500

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
            if os.path.exists(full_pdf_path):
                break
        if os.path.exists(full_pdf_path):
            # Отправляем email с вложением
            if send_guide_email(email, full_pdf_path):
                return jsonify({'success': True})
            else:
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
    custom_fields = data.get('CustomFields')
    print("[paid_callback] after custom_fields extraction")
    custom_fields_dict = {}  # всегда определяем заранее
    analysis_id = (
        data.get('analysis_id') or
        data.get('AnalysisId') or
        data.get('analysisId')
    )
    print("[paid_callback] after analysis_id extraction, value:", analysis_id)
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
                
                # Проверяем, что PDF создался
                if os.path.exists(full_pdf_path):
                    print("PDF generated successfully, sending email...")
                    # Отправляем email
                    if send_guide_email(email, full_pdf_path):
                        print("Email sent successfully!")
                        return jsonify({'code': 0, 'message': 'Success'})
                    else:
                        print("Failed to send email")
                        return jsonify({'code': 12, 'message': 'Failed to send email'}), 500
                else:
                    print("PDF was not generated")
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 