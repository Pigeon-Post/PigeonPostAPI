from flask import Flask
from flask_cors import CORS
from routes.rag_routes import rag_routes
from routes.lecture_routes import new_lecture_routes
from config.config import Config

def create_app():
    app = Flask(__name__)
   
    # Enable CORS
    CORS(app)

    app.config.from_object(Config)
    
    app.register_blueprint(rag_routes, url_prefix='/api/v1')
    app.register_blueprint(new_lecture_routes, url_prefix='/api/v2')
    
    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Not found"}, 404
    
    @app.errorhandler(500)
    def server_error(error):
        return {"error": "Internal server error"}, 500
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=Config.PORT_NUMBER, 
        debug=Config.DEBUG
    )