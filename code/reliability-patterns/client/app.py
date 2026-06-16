import time
import requests
import logging
import threading
from flask import Flask, jsonify
from logging.handlers import RotatingFileHandler
from collections import deque

app = Flask(__name__)

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FaultToleranceClient")
handler = RotatingFileHandler('app.log', maxBytes=10485760, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

BACKEND_URL = "http://backend:5000/health"

# ==========================================
# УТИЛИТЫ И КЛАССЫ ПАТТЕРНОВ
# ==========================================

# --- 1. Rate Limiter (Алгоритм Token Bucket) ---
class TokenBucket:
    """
    Паттерн: Rate Limiter.
    Позволяет пропускать только N запросов за определенный период времени.
    """
    def __init__(self, tokens, fill_rate):
        self.capacity = tokens
        self.tokens = tokens
        self.fill_rate = fill_rate  # токенов в секунду
        self.last_time = time.time() # 18:46:01
        self.lock = threading.Lock()

    def consume(self):
        with self.lock:
            now = time.time()
            # Добавляем новые токены на основе прошедшего времени
            elapsed = now - self.last_time
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
            self.last_time = now

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

rate_limiter = TokenBucket(tokens=2, fill_rate=0.5)

# --- 3. Circuit Breaker ---
class SimpleCircuitBreaker:
    def __init__(self):
        self.failures = 0
        self.state = "CLOSED" 
        self.last_failure_time = 0
        self.recovery_timeout = 10 
        self.threshold = 3

    def call(self, func):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info("CircuitBreaker: Пробуем восстановиться (HALF-OPEN)...")
            else:
                raise Exception("CircuitBreaker: Цепь разомкнута! Fail Fast.")

        try:
            result = func()
            if self.state != "CLOSED":
                self.state = "CLOSED"
                self.failures = 0
                logger.info("CircuitBreaker: Работа восстановлена (CLOSED)")
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            logger.error(f"CircuitBreaker ошибка ({self.failures}/{self.threshold}): {e}")
            
            if self.failures >= self.threshold:
                self.state = "OPEN"
                logger.critical("CircuitBreaker: ПРЕВЫШЕН ПОРОГ ОШИБОК. ЦЕПЬ РАЗОМКНУТА!")
            raise e

cb = SimpleCircuitBreaker()

# --- 4. Simple In-Memory Cache (для Fallback) ---
local_cache = {"data": None, "timestamp": 0}

@app.route('/unsafe')
def unsafe_request():
    try:
        resp = requests.get(BACKEND_URL)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/retry')
def retry_request():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(f"Retry: Попытка {attempt+1}")
            resp = requests.get(BACKEND_URL, timeout=2)
            if resp.status_code == 500:
                raise Exception("500 Server Error")
            return jsonify(resp.json())
        except Exception as e:
            logger.warning(f"Retry: Ошибка {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                return jsonify({"error": "Сервис недоступен после всех попыток"}), 504

@app.route('/backoff')
def exponential_backoff():
    max_retries = 4
    for attempt in range(max_retries):
        try:
            resp = requests.get(BACKEND_URL, timeout=2)
            resp.raise_for_status()
            return jsonify(resp.json())
        except Exception as e:
            delay = 0.5 * (2 ** attempt)
            logger.info(f"Backoff: Ждем {delay} сек. Ошибка: {e}")
            time.sleep(delay)
    return jsonify({"error": "Service Unavailable"}), 503

@app.route('/circuit')
def circuit_request():
    def logic():
        resp = requests.get(BACKEND_URL, timeout=2)
        resp.raise_for_status()
        return resp.json()

    try:
        data = cb.call(logic)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "status": "Circuit Breaker Blocked"}), 503

# --- DEMO: Rate Limiter ---
@app.route('/ratelimit')
def ratelimit_request():
    # Сначала проверяем, есть ли токены
    if not rate_limiter.consume():
        # Если токенов нет - сразу отказ (Throttling / Rate Limiting)
        logger.warning("RateLimiter: Лимит превышен (429 Too Many Requests)")
        return jsonify({"error": "Too Many Requests. Please slow down."}), 429
    
    # Если токен есть, идем к бэкенду
    try:
        logger.info("RateLimiter: Токен получен, запрос разрешен")
        resp = requests.get(BACKEND_URL, timeout=2)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/smart')
def smart_request():
    """
    Демонстрирует 'Graceful Degradation' с использованием кеша.
    Если бэкенд недоступен, отдаем последние известные данные.
    """
    try:
        resp = requests.get(BACKEND_URL, timeout=1)
        if resp.status_code == 200:
            data = resp.json()
            local_cache["data"] = data
            local_cache["timestamp"] = time.time()
            return jsonify({"source": "backend", "data": data})
        else:
            raise Exception(f"Status {resp.status_code}")
            
    except Exception as e:
        logger.warning(f"Ошибка получения данных: {e}. Пытаемся отдать кеш.")

        if local_cache["data"]:
            age = time.time() - local_cache["timestamp"]
            return jsonify({
                "source": "cache_fallback", 
                "message": "Бэкенд недоступен, данные из кеша",
                "cache_age_seconds": round(age, 1),
                "data": local_cache["data"]
            }), 200
        else:
            return jsonify({"error": "Сервис недоступен и кеш пуст"}), 503

if __name__ == "__main__":
    logger.info("Запуск Client App на порту 8080...")
    app.run(host='0.0.0.0', port=8080, threaded=True)