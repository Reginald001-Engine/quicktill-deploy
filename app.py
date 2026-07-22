from flask import Flask, jsonify, request
import time
import os

app = Flask(__name__)

# Fake DB check
def check_db():
    # In real app: try connect to Azure SQL
    return True 

# Fake dependency check  
def check_deps():
    # In real app: try payment gateway
    return True

@app.route("/health/live")
def liveness():
    return jsonify({"status": "alive"}), 200

@app.route("/health/ready") 
def readiness():
    if check_db():
        return jsonify({"db": "ok", "latency_ms": 12}), 200
    return jsonify({"db": "fail"}), 503

@app.route("/health/deps")
def deps():
    if check_deps():
        return jsonify({"payment_gateway": "ok", "inventory_service": "ok"}), 200
    return jsonify({"payment_gateway": "fail"}), 503

@app.route("/api/checkout/test", methods=["POST"])
def test_checkout():
    # This is the CRITICAL path health check from 2.1
    data = request.json
    time.sleep(0.1) # simulate work
    return jsonify({"status": "authorized", "orderId": f"test-{int(time.time())}"}), 201

@app.route("/")
def home():
    return "QuickTill is running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)