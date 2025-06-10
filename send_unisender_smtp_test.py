import smtplib
from email.mime.text import MIMEText

smtp_host = 'smtp.go2.unisender.ru'
smtp_port = 587
smtp_user = '7632090'  # ваш user_id
smtp_pass = '6u5ns3b6ewdck36reprxnmof8rf45beudi3zrw1a'  # подставьте сюда ваш API-ключ
from_email = 'info@stylebox.live'
to_email = 'info@stylebox.live'

msg = MIMEText('Тестовое письмо для активации домена в Unisender Go', 'plain', 'utf-8')
msg['Subject'] = 'Тест Unisender Go'
msg['From'] = from_email
msg['To'] = to_email

with smtplib.SMTP(smtp_host, smtp_port) as server:
    server.starttls()
    server.login(smtp_user, smtp_pass)
    server.sendmail(from_email, [to_email], msg.as_string())

print("Письмо отправлено! Проверьте почту info@stylebox.live.") 