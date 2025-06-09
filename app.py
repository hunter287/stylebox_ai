from flask import Flask, request, jsonify, render_template, send_file, session
import os
from werkzeug.utils import secure_filename
from color_analysis import ColorAnalyzer
from pdf_report import generate_pdf_report
import cv2
import json
from config import CLOUDPAYMENTS_PUBLIC_ID

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
    'soft_summer', 'deep_winter', 'warm_autumn'
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
        if 'pdf' in request.form or request.args.get('pdf') == '1':
            pdf_path = os.path.join('static/reports', f'report_{filename_wo_ext}.pdf')
            full_pdf_path = generate_pdf_report(result, filepath, output_path=pdf_path)
            return send_file(
                full_pdf_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=os.path.basename(full_pdf_path)
            )
        return jsonify(result)
    except Exception as e:
        print('ERROR in /analyze:', e)
        if 'filepath' in locals() and os.path.exists(filepath):
            pass
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 