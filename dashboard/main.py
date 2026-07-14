# main.py — бэкенд дашборда TutorDog
# Читает данные из Google Sheets и отдаёт их фронтенду за сессионной авторизацией.
# Запуск: DASH_USER=... DASH_PASS=... SESSION_SECRET=... \
#   python3 -m uvicorn main:app --host 127.0.0.1 --port 8010

import os
import secrets
import time

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import gspread
from google.oauth2.service_account import Credentials

# Пути и ID таблиц
CREDS_FILE = '/opt/tutordog-dashboard/service_account.json'
INDEX_PAGE = '/opt/tutordog-dashboard/index.html'
LOGIN_PAGE = '/opt/tutordog-dashboard/login.html'
SHEET_MAIN = '1czMIqlFs5QtRN08EJ-DeWMxCGrwXPoAFh5kpKaZcIzA'      # Сотрудники, Активные сессии, Банк вопросов
SHEET_RESULTS = '14w82dGBM2JAeYFGcb8lP8i7uHM4BCm7LAf5jLfds15k'   # Итоги тестов, Детализация ответов

# Права доступа к Google Sheets
SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# Учётные данные дашборда и ключ подписи сессии — только из окружения, без дефолтов
DASH_USER = os.environ.get('DASH_USER', '')
DASH_PASS = os.environ.get('DASH_PASS', '')
SESSION_SECRET = os.environ.get('SESSION_SECRET', '')

# Fail-fast: без стойкого ключа подпись сессии подделываема, без кред вход невозможен
if len(SESSION_SECRET) < 32:
    raise RuntimeError('SESSION_SECRET is missing or too short (need >= 32 chars)')
if not DASH_USER or not DASH_PASS:
    raise RuntimeError('DASH_USER/DASH_PASS are not configured')

# Срок жизни сессии — 30 дней («запомнить меня» по умолчанию)
SESSION_MAX_AGE = 60 * 60 * 24 * 30

# Кэш ответа /api/data, чтобы не бить по квоте Google Sheets на каждый запрос
CACHE_TTL_SECONDS = 60
_cache = {'ts': 0.0, 'data': None}

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=SESSION_MAX_AGE,
    same_site='lax',
    https_only=True,
)


def is_authed(request: Request) -> bool:
    return request.session.get('auth') is True


def credentials_valid(username: str, password: str) -> bool:
    # Сравнение через compare_digest — постоянное время, защита от timing-атак
    if not DASH_USER or not DASH_PASS:
        return False
    user_ok = secrets.compare_digest(username, DASH_USER)
    pass_ok = secrets.compare_digest(password, DASH_PASS)
    return user_ok and pass_ok


def get_sheets_client():
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


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authed(request):
        return RedirectResponse('/', status_code=302)
    with open(LOGIN_PAGE, 'r', encoding='utf-8') as f:
        return HTMLResponse(f.read())


@app.post("/login")
def login_submit(request: Request, username: str = Form(''), password: str = Form('')):
    if credentials_valid(username, password):
        request.session['auth'] = True
        return RedirectResponse('/', status_code=303)
    return RedirectResponse('/login?error=1', status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/login', status_code=303)


@app.get("/api/data")
def get_data(request: Request):
    if not is_authed(request):
        return JSONResponse({'detail': 'Unauthorized'}, status_code=401)
    now = time.monotonic()
    if _cache['data'] is None or now - _cache['ts'] > CACHE_TTL_SECONDS:
        _cache['data'] = load_data()
        _cache['ts'] = now
    return _cache['data']


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if not is_authed(request):
        return RedirectResponse('/login', status_code=302)
    with open(INDEX_PAGE, 'r', encoding='utf-8') as f:
        return HTMLResponse(f.read())
