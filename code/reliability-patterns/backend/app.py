import random
import time
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/api/data')
def get_data():
    if random.random() < 0.7: 
        time.sleep(10)
        return jsonify({"error": "Internal Server Error"}), 500

    return jsonify({
        "id": 123, 
        "info": "Важные данные от бэкенда", 
        "timestamp": time.time()
    }), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)