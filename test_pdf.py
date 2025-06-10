import json
import os
from pdf_report import generate_pdf_report
from app import send_guide_email, normalize_email

# Пути к файлам
analysis_id = "764991b1-3519-47dd-89d1-7d40ac3b9012"
email = "sergei.v.kim@gmail.com"

analysis_path = f'static/reports/last_analysis_{analysis_id}.json'
image_path = f'static/reports/last_image_{analysis_id}.jpg'
pdf_path = f'static/reports/report_{normalize_email(email)}_{analysis_id}.pdf'

print(f"Loading analysis from: {analysis_path}")
print(f"Using image from: {image_path}")
print(f"Will save PDF to: {pdf_path}")

# Загружаем анализ
with open(analysis_path) as f:
    analysis = json.load(f)

# Генерируем PDF
print("\nGenerating PDF...")
try:
    full_pdf_path = generate_pdf_report(analysis, image_path, output_path=pdf_path)
    print(f"PDF generation completed, full path: {full_pdf_path}")
except Exception as e:
    print(f"Error generating PDF: {str(e)}")
    import traceback
    print("Traceback:", traceback.format_exc())

# Проверяем, что PDF создался
if os.path.exists(full_pdf_path):
    print(f"\nPDF generated successfully at: {full_pdf_path}")
    print("Sending email...")
    if send_guide_email(email, full_pdf_path):
        print("Email sent successfully!")
    else:
        print("Failed to send email")
else:
    print("\nFailed to generate PDF") 