from flask import Blueprint, render_template

# Create a Blueprint for all pages
pages_bp = Blueprint('pages', __name__)

def init_pages(app):
    """Initialize all page routes."""
    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.utcnow}
        
    @pages_bp.route('/generator')
    def barcode_generator():
        """Serve the barcode generator HTML page."""
        return render_template('barcode_generator.html')

    app.register_blueprint(pages_bp)