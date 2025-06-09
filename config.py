import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Google Cloud Vision configuration
GOOGLE_CLOUD_CREDENTIALS = os.getenv('GOOGLE_CLOUD_CREDENTIALS')

# OpenAI API Key
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# CloudPayments configuration
CLOUDPAYMENTS_PUBLIC_ID = os.getenv('CLOUDPAYMENTS_PUBLIC_ID')

# Email configuration
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
EMAIL_FROM = os.getenv('SMTP_USERNAME')

# Unisender configuration
UNISENDER_API_KEY = os.getenv('UNISENDER_API_KEY')
UNISENDER_LIST_ID = os.getenv('UNISENDER_LIST_ID')

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///stylist_ai.db')

# Application settings
MAX_REQUESTS_PER_DAY = 10 