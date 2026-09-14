from flask import Blueprint, render_template

# Create a Blueprint for all pages
pages_bp = Blueprint('pages', __name__)

def init_pages(app):
    """Initialize all page routes."""
    def get_domain_parts(host):
        """Split host into subdomain and tld parts."""
        if not host:
            return 'BreadHub', ''
            
        # Remove port if present
        domain = host.split(':')[0]
        parts = domain.split('.')
        
        if len(parts) == 1:
            return domain, ''
        elif len(parts) == 2:
            return '', domain  # No subdomain, return full domain as TLD
        else:
            # For domains like 'sub.domain.tld' or 'sub1.sub2.domain.tld'
            return parts[0], '.'.join(parts[1:])
    
    @app.context_processor
    def inject_template_vars():
        from datetime import datetime
        from flask import request
        
        # Get the host from the request headers
        host = request.headers.get('Host', '')
        
        # Split into subdomain and tld
        subdomain, tld = get_domain_parts(host)
        
        return {
            'now': datetime.utcnow,
            'site_name': tld if tld else 'BreadHub',  # Use TLD as site name if available
            'site_subdomain': subdomain,
            'site_tld': tld
        }
        
    @pages_bp.route('/generator')
    def barcode_generator():
        """Serve the barcode generator HTML page."""
        return render_template('barcode_generator.html')

    @pages_bp.route('/imagegrid')
    def image_grid():
        """Serve the image grid generator HTML page."""
        return render_template('imagegrid.html')

    app.register_blueprint(pages_bp)