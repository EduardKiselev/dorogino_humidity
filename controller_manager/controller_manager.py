from flask import Flask, jsonify
from datetime import datetime
import logging
import requests
import os
from dotenv import load_dotenv
load_dotenv() 

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IP_MAP = {
    1:  os.getenv('CONTROLLER_1_IP', None),
    2:  os.getenv('CONTROLLER_2_IP', None),
}
STATUS_MAP = {
    'ON':  'open',
    'OFF':  'close',
}

def handle_switch_request(controller_id, status_upper):
    ip = IP_MAP.get(controller_id)
    
    if not ip:
        logger.error(f"Controller {controller_id} IP not configured in environment")
        return False
    url = f"http://{ip}:80/valve/{STATUS_MAP[status_upper]}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        logger.info(f"Command sent to {controller_id}: {status_upper}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send command to {controller_id}: {e}")
        return False
@app.route('/<int:controller_id>/<status>', methods=['GET'])
def handle_controller_request(controller_id, status):
    """
    Handle controller management requests
    Expected route pattern: /{controller_id}/{status}
    Where status is either 'ON' or 'OFF'
    """
    logger.info(f"Received controller request - Controller ID: {controller_id}, Status: {status}")
    
    status_upper = status.upper()

    if status_upper not in STATUS_MAP:
        return jsonify({"status": "error", "message": "Status must be either 'ON' or 'OFF'"}), 400
    
    if controller_id not in IP_MAP:
        return jsonify({"status": "error", "message": f"Controller {controller_id} not found"}), 404
    success = handle_switch_request(controller_id, status_upper)

    if not success:
        return jsonify({
            "status": "error",
            "message": f"Failed to communicate with controller {controller_id} ip - {IP_MAP[controller_id]}"
        }), 503

    return jsonify({
        "status": "success",
        "message": f"Controller {controller_id} status change to {status.upper()} received",
        "controller_id": controller_id,
        "requested_status": status_upper,
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route('/', methods=['GET'])
@app.route('/health', methods=['GET']) 
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "controller-manager"}), 200

if __name__ == '__main__':
    print("🚀 Starting Controller Management Service...")
    print("🔌 Available endpoints:")
    print("   GET  /<controller_id>/ON  - Turn controller ON")
    print("   GET  /<controller_id>/OFF - Turn controller OFF")
    print("   GET  /health              - Health check")
    
    app.run(host='0.0.0.0', port=5001, debug=True)