# handlers/lecture_content_handler.py
from typing import Dict, Any
from database.lecture_content import LectureContentGenerator
from rag.rag import RAG

def generate_lecture_content_handler(course_title: str, lecture_title: str, email: str = None) -> Dict[str, Any]:
    """Handler for generating lecture content"""
    try:
        # Get lecture content from RAG
        rag = RAG()
        lecture_response = rag.get_complete_lecture(course_title, lecture_title)
        
        if lecture_response["status"] != "success":
            return {
                "status": "error",
                "message": f"Failed to get lecture content: {lecture_response['message']}"
            }
            
        content = lecture_response.get("complete_content")
        if not content:
            return {
                "status": "error",
                "message": "No content found in lecture response"
            }
        
        # Generate content
        generator = LectureContentGenerator()
        result = generator.generate_content(
            content,
            course_title,
            lecture_title,
            email
        )
        
        return result
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate content: {str(e)}"
        }