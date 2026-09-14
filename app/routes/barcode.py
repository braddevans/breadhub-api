import base64
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from barcode.codex import Code128
from barcode.writer import ImageWriter
from flask import request, jsonify, Response

from app.logging_config import logger
from app.middleware import error_response

from . import BaseRoute

# Root of the `app` package, used to resolve bundled font paths such as
# 'fonts/lato.ttf' regardless of the process working directory.
APP_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = APP_ROOT / 'fonts'

SUPPORTED_BARCODE_TYPES = {'code128'}

# Image formats the writer may emit, mapped to the mimetype used to serve them.
IMAGE_FORMAT_MIMETYPES = {
    'PNG': 'image/png',
    'JPEG': 'image/jpeg',
    'GIF': 'image/gif',
    'BMP': 'image/bmp',
    'TIFF': 'image/tiff',
}

# Inclusive (min, max) bounds for numeric writer options. These keep a stray
# query parameter from asking Pillow for a multi-gigapixel image.
NUMERIC_LIMITS = {
    'module_width': (0.01, 10.0),
    'module_height': (1.0, 1000.0),
    'quiet_zone': (0.0, 100.0),
    'text_distance': (0.0, 100.0),
    'dpi': (1.0, 1200.0),
    'font_size': (1, 200),
}

class BarcodeAPI(BaseRoute):
    """Barcode API routes."""
    
    def __init__(self):
        super().__init__('barcode', url_prefix='/barcode')
        
    def _register_routes(self):
        """Register all barcode routes."""
        self.bp.route('', methods=['GET'], endpoint='generate_barcode')(self.generate_barcode)
        self.bp.route('/', methods=['GET'], endpoint='generate_barcode_slash')(self.generate_barcode)
        self.bp.route('/writer-options', methods=['GET'], endpoint='list_all_writer_options')(self.list_all_writer_options)

    DEFAULT_OPTIONS = {
        'write_text': True,
        'quiet_zone': 4.0,
        'module_width': 0.2,
        'module_height': 15.0,
        'font_size': 10,
        'text_distance': 5.0,
        'center_text': True,
        'background': 'white',
        'foreground': 'black',
        'dpi': 150,
        'font_path': 'fonts/{font_family}.ttf'
    }

    @staticmethod
    def _resolve_font_path(font_path):
        """
        Resolve a requested font to a bundled font file.

        `font_path` and `font_family` are caller-controlled, so the resolved
        path is confined to app/fonts: anything that escapes that directory
        (absolute paths, '..' traversal) is refused. Returns None when no
        bundled font matches, which lets the writer fall back to its own
        default instead of failing the request - that is what keeps system
        fonts like Arial, which ship no .ttf here, working.
        """
        if not font_path:
            return None

        candidate = (APP_ROOT / font_path).resolve()

        if not candidate.is_relative_to(FONTS_DIR):
            logger.warning("Refusing font path outside {}: {}", FONTS_DIR, font_path)
            return None

        if candidate.is_file():
            return str(candidate)

        # Font family names are lowercased to build the filename, but some
        # bundled files are capitalised (Lato.ttf, Barlow.ttf), so fall back to
        # a case-insensitive match before giving up.
        match = next(
            (f for f in FONTS_DIR.glob('*') if f.name.lower() == candidate.name.lower()),
            None
        )
        if match is not None:
            return str(match)

        logger.warning("Font not found, falling back to default: {}", font_path)
        return None

    def _get_writer_options(self):
        options = self.DEFAULT_OPTIONS.copy()

        # Matches the default selected in the barcode generator UI.
        font_family = request.args.get('font_family', 'Typo Round Bold')
        font_filename = font_family.replace(' ', '-').lower()
        options['font_path'] = options['font_path'].format(font_family=font_filename)
        
        bool_options = ['write_text', 'center_text']
        float_options = ['module_width', 'module_height', 'quiet_zone', 'text_distance', 'dpi']
        int_options = ['font_size']
        str_options = ['background', 'foreground', 'text', 'font_path']
        
        for key, value in request.args.items():
            if key in bool_options:
                options[key] = value.lower() == 'true'
            elif key in float_options:
                options[key] = self._check_limits(
                    key, float(value)
                ) if value.replace('.', '', 1).isdigit() else options.get(key)
            elif key in int_options:
                options[key] = self._check_limits(
                    key, int(float(value))
                ) if value.isdigit() else options.get(key)
            elif key in str_options:
                options[key] = value
            elif key == 'format':
                options['format'] = value.upper() if value.upper() in IMAGE_FORMAT_MIMETYPES else 'PNG'

        return options

    @staticmethod
    def _check_limits(key, value):
        """Reject numeric options outside their supported range."""
        low, high = NUMERIC_LIMITS[key]
        if not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}, got {value}")
        return value

    def list_all_writer_options(self):
        """Return default writer options for Code128."""
        serializable_opts = {k: v for k, v in self.DEFAULT_OPTIONS.items() 
                           if isinstance(v, (str, int, float, bool, type(None)))}
        return jsonify({
            "formats": {"code128": serializable_opts},
            "allowed_image_formats": sorted(IMAGE_FORMAT_MIMETYPES)
        })

    def generate_barcode(self):
        try:
            data = request.args.get('data')
            if not data:
                return error_response('Missing required parameter: data', 400)

            barcode_type = request.args.get('type', 'code128').lower()
            if barcode_type not in SUPPORTED_BARCODE_TYPES:
                return error_response(
                    f"Unsupported barcode format: {barcode_type}. "
                    f"Supported: {', '.join(sorted(SUPPORTED_BARCODE_TYPES))}",
                    400
                )

            if request.args.get('uppercase', 'false').lower() == 'true':
                data = data.upper()
            raw = request.args.get('raw', 'false').lower() == 'true'
            return self._create_barcode_response(data, raw)
        except Exception as e:
            logger.exception("Error generating barcode: {}", e)
            return error_response(str(e), 500)

    def _create_barcode_response(self, data, raw=False):
        logger.debug("Generating Code128 barcode for data: {!r}", data)
        try:
            writer_options = self._get_writer_options()

            # The writer needs a real path on disk; the response echoes back the
            # logical path the caller asked for.
            render_options = writer_options.copy()
            resolved_font = self._resolve_font_path(render_options.get('font_path'))
            if resolved_font:
                render_options['font_path'] = resolved_font
            else:
                render_options.pop('font_path', None)

            barcode_instance = Code128(data, writer=ImageWriter())

            buffer = BytesIO()
            barcode_instance.write(buffer, options=render_options)
            buffer.seek(0)

            image_format = writer_options.get('format', 'PNG')
            mimetype = IMAGE_FORMAT_MIMETYPES[image_format]

            if raw:
                payload = buffer.getvalue()
                extension = image_format.lower()
                return Response(
                    payload,
                    content_type=mimetype,
                    headers={
                        'Content-Length': str(len(payload)),
                        'Content-Disposition': f'inline; filename=barcode_code128.{extension}'
                    }
                )
            return self._create_json_response(buffer, data, writer_options, mimetype)
        except ValueError as e:
            return error_response(str(e), 400)
        except Exception as e:
            logger.exception("Failed to generate Code128 barcode: {}", e)
            return error_response(f"Failed to generate barcode: {str(e)}", 500)

    @staticmethod
    def _create_json_response(buffer, data, writer_options=None, mimetype='image/png'):
        buffer.seek(0)
        base64_encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
        serializable_options = {}
        if writer_options:
            for key, value in writer_options.items():
                if isinstance(value, (str, int, float, bool, type(None))):
                    serializable_options[key] = value
                elif isinstance(value, (list, dict, tuple)):
                    serializable_options[key] = str(value)
        return jsonify({
            'barcode': f'data:{mimetype};base64,{base64_encoded}',
            'barcode_type': 'code128',
            'data': data,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'options': serializable_options
        })

# Create and export the blueprint
barcode_bp, url_prefix = BarcodeAPI.create()


def create_blueprint():
    """Entry point used by app.routes.init_app to register this module."""
    return barcode_bp, url_prefix