import os
import re
import time
import gspread
from google.oauth2.service_account import Credentials
from functools import wraps
from flask import session, request, jsonify, redirect, url_for
import logging
from datetime import datetime, timedelta
from config import (
    GOOGLE_SHEET_ID, 
    GOOGLE_SHEET_SUBSCRIPTION_WORKSHEET, 
    GOOGLE_SERVICE_ACCOUNT_FILE
)
from user_auth import user_auth

logger = logging.getLogger(__name__)

# Кэш для хранения данных о подписчиках (обновляется каждые 5 минут)
_subscriber_cache = {}
_cache_timestamp = 0
CACHE_DURATION = 300  # 5 минут

def normalize_email(email):
    """Нормализует email адрес"""
    if not email:
        return None
    return email.strip().lower()

def get_subscribers_from_sheet():
    """Получает список подписчиков из Google Sheets"""
    global _subscriber_cache, _cache_timestamp
    
    # Проверяем, не устарел ли кэш
    current_time = time.time()
    if current_time - _cache_timestamp < CACHE_DURATION and _subscriber_cache:
        return _subscriber_cache
    
    try:
        # Подключаемся к Google Sheets
        creds = Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE, 
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets.readonly',
                'https://www.googleapis.com/auth/drive.readonly',
            ]
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        
        # Открываем лист с подписчиками
        worksheet = sh.worksheet(GOOGLE_SHEET_SUBSCRIPTION_WORKSHEET)
        
        # Получаем все данные из листа
        all_values = worksheet.get_all_values()
        
        subscribers = {}
        
        # Обрабатываем данные (предполагаем, что email в колонке A, дата окончания в колонке B)
        for row in all_values[1:]:  # Пропускаем заголовок
            if len(row) >= 2:
                email = normalize_email(row[0])
                end_date_str = row[1].strip()
                
                if email and end_date_str:
                    try:
                        # Парсим дату окончания подписки
                        end_date = datetime.strptime(end_date_str, '%d.%m.%Y')
                        subscribers[email] = {
                            'end_date': end_date,
                            'is_active': end_date > datetime.now()
                        }
                    except ValueError:
                        # Если не удалось распарсить дату, считаем подписку активной
                        subscribers[email] = {
                            'end_date': None,
                            'is_active': True
                        }
        
        # Обновляем кэш
        _subscriber_cache = subscribers
        _cache_timestamp = current_time
        
        logger.info(f"Загружено {len(subscribers)} подписчиков из Google Sheets")
        return subscribers
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке подписчиков из Google Sheets: {str(e)}")
        return {}

def check_subscription(email):
    """Проверяет, есть ли активная подписка у пользователя"""
    email = normalize_email(email)
    if not email:
        return False
    
    subscribers = get_subscribers_from_sheet()
    subscriber_info = subscribers.get(email)
    
    if subscriber_info:
        return subscriber_info['is_active']
    
    return False

def login_required(f):
    """Декоратор для проверки авторизации"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_id = session.get('session_id')
        logger.info(f"🔍 Проверяем авторизацию. Session ID: {session_id}")
        logger.info(f"🔍 Session keys: {list(session.keys())}")
        logger.info(f"🔍 Session permanent: {session.permanent}")
        logger.info(f"🔍 Session modified: {session.modified}")
        
        if not session_id:
            logger.warning("⚠️ Session ID отсутствует в Flask session")
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        # Проверяем сессию в MongoDB
        user = user_auth.get_user_by_session(session_id)
        if not user:
            logger.warning(f"⚠️ Пользователь не найден по session_id: {session_id}")
            session.pop('session_id', None)
            return jsonify({'error': 'Сессия истекла. Требуется повторная авторизация'}), 401
        
        logger.info(f"✅ Пользователь авторизован: {user.get('email')}")
        # Добавляем пользователя в request для использования в маршрутах
        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function

def subscription_required(f):
    """Декоратор для проверки активной подписки"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        # Проверяем сессию в MongoDB
        user = user_auth.get_user_by_session(session_id)
        if not user:
            session.pop('session_id', None)
            return jsonify({'error': 'Сессия истекла. Требуется повторная авторизация'}), 401
        
        # Проверяем подписку
        if not user_auth.check_subscription(user['_id']):
            return jsonify({'error': 'Требуется активная подписка'}), 403
        
        # Добавляем пользователя в request для использования в маршрутах
        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function

def rate_limit_check():
    """Проверка rate limiting для авторизации (временно отключено)"""
    # Временно отключаем rate limiting для тестирования
    return True, None
    
    # user_ip = request.remote_addr
    # current_time = time.time()
    # 
    # # Получаем или создаем данные о попытках входа для IP
    # if 'login_attempts' not in session:
    #     session['login_attempts'] = {}
    # 
    # attempts = session['login_attempts']
    # 
    # # Очищаем старые попытки (старше 15 минут)
    # attempts = {ip: data for ip, data in attempts.items() 
    #            if current_time - data['timestamp'] < 900}
    # 
    # user_attempts = attempts.get(user_ip, {'count': 0, 'timestamp': current_time})
    # 
    # # Проверяем лимит (5 попыток за 15 минут)
    # if user_attempts['count'] >= 5:
    #     time_diff = current_time - user_attempts['timestamp']
    #     if time_diff < 900:  # 15 минут
    #         return False, f"Слишком много попыток входа. Попробуйте через {int((900 - time_diff) / 60)} минут."
    # 
    # return True, None

def record_login_attempt(success=True):
    """Записывает попытку входа"""
    user_ip = request.remote_addr
    current_time = time.time()
    
    if 'login_attempts' not in session:
        session['login_attempts'] = {}
    
    attempts = session['login_attempts']
    
    if user_ip not in attempts:
        attempts[user_ip] = {'count': 0, 'timestamp': current_time}
    
    if not success:
        attempts[user_ip]['count'] += 1
        attempts[user_ip]['timestamp'] = current_time
    
    session['login_attempts'] = attempts 