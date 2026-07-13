# main.py — бэкенд дашборда TutorDog
# Читает данные из Google Sheets и отдаёт их фронтенду
# Запуск: DASH_USER=... DASH_PASS=... python3 -m uvicorn main:app --host 127.0.0.1 --port 8000

import os
import secrets
import time

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()
security = HTTPBasic()

# Пути и ID таблиц
CREDS_FILE = '/opt/tutordog-dashboard/service_account.json'
SHEET_MAIN = '1czMIqlFs5QtRN08EJ-DeWMxCGrwXPoAFh5kpKaZcIzA'      # Сотрудники, Активные сессии, Банк вопросов
SHEET_RESULTS = '14w82dGBM2JAeYFGcb8lP8i7uHM4BCm7LAf5jLfds15k'   # Итоги тестов, Детализация ответов

# Права доступа к Google Sheets
SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# Учётные данные дашборда — только из окружения, без дефолтов
DASH_USER = os.environ.get('DASH_USER', '')
DASH_PASS = os.environ.get('DASH_PASS', '')

# Кэш ответа /api/data, чтобы не бить по квоте Google Sheets на каждый запрос
CACHE_TTL_SECONDS = 60
_cache = {'ts': 0.0, 'data': None}


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    # Basic-аутентификация; сравнение через compare_digest от timing-атак
    if not DASH_USER or not DASH_PASS:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Dashboard auth is not configured (DASH_USER/DASH_PASS)'
        )
    user_ok = secrets.compare_digest(credentials.username, DASH_USER)
    pass_ok = secrets.compare_digest(credentials.password, DASH_PASS)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Unauthorized',
            headers={'WWW-Authenticate': 'Basic'},
        )
    return credentials.username


def get_sheets_client():
    # Авторизация через сервисный аккаунт
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def load_data():
    client = get_sheets_client()
    main_file = client.open_by_key(SHEET_MAIN)
    results_file = client.open_by_key(SHEET_RESULTS)

    return {
        "employees": main_file.worksheet('Сотрудники').get_all_records(),
        "sessions": main_file.worksheet('Активные сессии').get_all_records(),
        "questions_bank": main_file.worksheet('Банк вопросов').get_all_records(),
        "results": results_file.worksheet('Итоги тестов').get_all_records(),
        "details": results_file.worksheet('Детализация ответов').get_all_records(),
    }


@app.get("/api/data")
def get_data(user: str = Depends(require_auth)):
    # Основной эндпоинт — возвращает все данные для дашборда (за аутентификацией, с кэшем)
    now = time.monotonic()
    if _cache['data'] is None or now - _cache['ts'] > CACHE_TTL_SECONDS:
        _cache['data'] = load_data()
        _cache['ts'] = now
    return _cache['data']


@app.get("/", response_class=HTMLResponse)
def dashboard(user: str = Depends(require_auth)):
    # Отдаёт HTML-страницу дашборда
    with open('/opt/tutordog-dashboard/index.html', 'r') as f:
        return f.read()
