bind = "127.0.0.1:8000"
workers = 3
timeout = 120
accesslog = "access.log"
errorlog = "error.log"
capture_output = True
enable_stdio_inheritance = True

# Переменные окружения загружаются из файла .env
# Создайте файл .env в корневой директории проекта и добавьте необходимые переменные
# Пример содержимого .env:
# OPENAI_API_KEY=your-api-key-here 