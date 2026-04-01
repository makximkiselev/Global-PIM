import os
from pathlib import Path

# чтобы импорт app работал стабильно (cwd не важен)
import sys
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8010"))

    # ВАЖНО: запускаем реальное приложение из backend/app/main.py
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
