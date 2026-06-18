# main.py — бэкенд дашборда TutorDog
# Читает данные из Google Sheets и отдаёт их фронтенду
# Запуск: python3 -m uvicorn main:app --host 0.0.0.0 --port 8000

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()

# Пути и ID таблиц
CREDS_FILE = '/opt/tutordog-dashboard/service_account.json'
SHEET_MAIN = '1czMIqlFs5QtRN08EJ-DeWMxCGrwXPoAFh5kpKaZcIzA'      # Сотрудники, Активные сессии, Банк вопросов
SHEET_RESULTS = '14w82dGBM2JAeYFGcb8lP8i7uHM4BCm7LAf5jLfds15k'   # Итоги тестов, Детализация ответов

# Права доступа к Google Sheets
SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

def get_sheets_client():
    # Авторизация через сервисный аккаунт
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

@app.get("/api/data")
def get_data():
    # Основной эндпоинт — возвращает все данные для дашборда
    client = get_sheets_client()
    main_file = client.open_by_key(SHEET_MAIN)
    results_file = client.open_by_key(SHEET_RESULTS)

    employees = main_file.worksheet('Сотрудники').get_all_records()
    sessions = main_file.worksheet('Активные сессии').get_all_records()
    questions_bank = main_file.worksheet('Банк вопросов').get_all_records()
    results = results_file.worksheet('Итоги тестов').get_all_records()
    details = results_file.worksheet('Детализация ответов').get_all_records()

    return {
        "employees": employees,
        "sessions": sessions,
        "questions_bank": questions_bank,  # Банк вопросов — для ссылок на БЗ
        "results": results,
        "details": details
    }

@app.get("/", response_class=HTMLResponse)
def dashboard():
    # Отдаёт HTML-страницу дашборда
    with open('/opt/tutordog-dashboard/index.html', 'r') as f:
        return f.read()
