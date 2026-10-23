from datetime import UTC, datetime

from flask import Blueprint, render_template, request

# Routes are attached at import time, never inside init_pages: Flask forbids
# adding routes to a blueprint after it has been registered with an app.
pages_bp = Blueprint('pages', __name__)


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


@pages_bp.app_context_processor
def inject_template_vars():
    subdomain, tld = get_domain_parts(request.headers.get('Host', ''))
    return {
        'now': lambda: datetime.now(UTC),
        'site_name': tld or 'BreadHub',  # Use TLD as site name if available
        'site_subdomain': subdomain,
        'site_tld': tld
    }


@pages_bp.route('/')
def index():
    """Serve the landing page."""
    return render_template('index.html')


@pages_bp.route('/generator')
def barcode_generator():
    """Serve the barcode generator HTML page."""
    return render_template('barcode_generator.html')


@pages_bp.route('/imagegrid')
def image_grid():
    """Serve the image grid generator HTML page."""
    return render_template('imagegrid.html')


def init_pages(app):
    """Register the page routes with the app."""
    app.register_blueprint(pages_bp)
