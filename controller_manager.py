from flask import Flask, request, jsonify
from datetime import datetime
import logging

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/<int:controller_id>/<status>', methods=['GET'])
def handle_controller_request(controller_id, status):
    """
    Handle controller management requests
    Expected route pattern: /{controller_id}/{status}
    Where status is either 'ON' or 'OFF'
    """
    logger.info(f"Received controller request - Controller ID: {controller_id}, Status: {status}")
    
    # Validate status parameter
    if status.upper() not in ['ON', 'OFF']:
        return jsonify({"status": "error", "message": "Status must be either 'ON' or 'OFF'"}), 400
    
    # Placeholder for actual controller management logic
    # In the future, implement actual communication with controllers here
    print(f"CONTROLLER MANAGER: Request received for controller {controller_id} to set status to {status.upper()}")
    
    # Return success response
    return jsonify({
        "status": "success",
        "message": f"Controller {controller_id} status change to {status.upper()} received",
        "controller_id": controller_id,
        "requested_status": status.upper(),
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route('/', methods=['GET'])
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