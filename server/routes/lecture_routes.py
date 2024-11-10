from flask import Blueprint, request, jsonify
from handlers.lecture_content_handler import generate_lecture_content_handler

new_lecture_routes = Blueprint('new_lecture_routes', __name__)

@new_lecture_routes.route('/generate-lecture', methods=['POST'])
def generate_lecture():
    """Generate lecture content"""
    try:
        data = request.get_json()

        # Validate required fields
        if not data or 'course_title' not in data or 'lecture_title' not in data:
            return jsonify({
                "status": "error",
                "message": "Missing required fields: 'course_title' and 'lecture_title'"
            }), 400

        course_title = data['course_title']
        lecture_title = data['lecture_title']
        email = data.get('email')  # Optional field

        # Call the actual handler to generate content
        response = generate_lecture_content_handler(course_title, lecture_title, email)

        status_code = 200 if response['status'] == 'success' else 500
        return jsonify(response), status_code

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Server error: {str(e)}"
        }), 500
