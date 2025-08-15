import base64
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Dict, Type, Any, ClassVar, TypeVar, Optional

from barcode.codex import Code128
from barcode.ean import EuropeanArticleNumber13WithGuard as EAN13_GUARD
from barcode.writer import ImageWriter
from flask import Blueprint, request, jsonify, Response

from logging_config import logger

BarcodeType: TypeVar = TypeVar('BarcodeType', bound=EAN13_GUARD)

@dataclass
class BarcodeConfig:
    barcode_class: Type[BarcodeType]
    default_options: Dict[str, Any] = None
    requires_checksum: bool = False

    def __post_init__(self):
        if self.default_options is None:
            self.default_options = {}

    def validate_data(self, data: str) -> bool:
        if not data or (not data.isdigit() and self.requires_checksum):
            return False
        return True

class BarcodeAPI:

    def __init__(self):
        self.bp = Blueprint('barcode', __name__)
        self.bp.route('', methods=['GET'], endpoint='generate_barcode')(self.generate_barcode)
        self.bp.route('/', methods=['GET'], endpoint='generate_barcode_slash')(self.generate_barcode)
        self.bp.route('/writer-options', methods=['GET'], endpoint='list_all_writer_options')(self.list_all_writer_options)

    BASE_DEFAULTS = {
        'writer': ImageWriter(),
        'write_text': True,
        'quiet_zone': 4.0,
        'module_width': 0.2,
        'module_height': 15.0,
        'font_size': 10,
        'text_distance': 5.0,
        'center_text': True,
        'background': 'white',
        'foreground': 'black',
        'dpi': 300,
        'font_path': 'fonts/TypoRoundBold.otf'
    }

    BARCODE_CONFIGS: ClassVar[Dict[str, BarcodeConfig]] = {
        'code128': BarcodeConfig(
            barcode_class=Code128,
            default_options=BASE_DEFAULTS.copy()
        ),
        'ean13': BarcodeConfig(
            barcode_class=EAN13_GUARD,
            default_options={
                **BASE_DEFAULTS,
                'module_width': 0.4,
                'module_height': 12.0,
                'quiet_zone': 6.5,
                'font_size': 12,
                'format': 'PNG',
                'guard_bars': True,
                'guard_bar_height': 15.0,
                'guard_bar_color': 'black'
            },
            requires_checksum=True
        )
    }

    _FORMAT_ALIASES: ClassVar[Dict[str, str]] = {fmt: fmt for fmt in BARCODE_CONFIGS.keys()}

    @classmethod
    def get_barcode_config(cls, format_name: str) -> BarcodeConfig:
        primary_format = cls._FORMAT_ALIASES.get(format_name.lower())
        if not primary_format:
            raise ValueError(f'Unsupported barcode format: {format_name}')
        return cls.BARCODE_CONFIGS[primary_format]

    def _get_writer_options(self, barcode_format: str) -> dict:
        config = self.get_barcode_config(barcode_format)
        options = config.default_options.copy()

        for key, value in request.args.items():
            if key in ['write_text', 'center_text', 'guard_bars']:
                options[key] = value.lower() == 'true'
            elif key in ['module_width', 'module_height', 'quiet_zone', 'text_distance', 'dpi', 'guard_bar_height']:
                try:
                    options[key] = float(value)
                except ValueError:
                    pass
            elif key in ['font_size']:
                try:
                    options[key] = int(value)
                except ValueError:
                    pass
            elif key in ['background', 'foreground', 'text', 'font_path', 'guard_bar_color']:
                options[key] = value
            elif key == 'format':
                img_format = value.upper()
                if img_format in ['PNG', 'JPEG', 'GIF', 'BMP', 'TIFF']:
                    options['format'] = img_format
                else:
                    options['format'] = 'PNG'
        return options

    def list_all_writer_options(self):
        """Return default writer options for all supported barcode formats, including EAN13 guard bar settings."""
        formats = {}
        for format_name, config in self.BARCODE_CONFIGS.items():
            opts = config.default_options.copy()
            serializable_opts = {}
            for k, v in opts.items():
                if isinstance(v, (str, int, float, bool, type(None))):
                    serializable_opts[k] = v
            formats[format_name] = serializable_opts

        return jsonify({
            "formats": formats,
            "allowed_image_formats": ["PNG", "JPEG", "GIF", "BMP", "TIFF"],
            "count": len(formats)
        })

    def generate_barcode(self):
        try:
            data = request.args.get('data')
            if not data:
                return self._error_response('Missing required parameter: data', 400)
            if request.args.get('uppercase', 'false').lower() == 'true':
                data = data.upper()
            barcode_format = (request.args.get('type') or request.args.get('format') or 'code128').lower()
            raw = request.args.get('raw', 'false').lower() == 'true'
            try:
                self.get_barcode_config(barcode_format)
            except ValueError:
                return self._error_response(
                    f'Unsupported barcode format. Supported formats: {list(self.BARCODE_CONFIGS.keys())}',
                    400
                )
            return self._create_barcode_response(data, barcode_format, raw)
        except Exception as e:
            logger.error(f"Error generating barcode: {str(e)}", exc_info=True)
            return self._error_response(str(e), 500)

    def _create_barcode_instance(self, data: str, barcode_format: str):
        writer_options = self._get_writer_options(barcode_format)
        barcode_instance = self.get_barcode_config(barcode_format).barcode_class(data, writer=ImageWriter())
        return barcode_instance, writer_options

    def _create_barcode_response(self, data: str, barcode_format: str, raw: bool = False):
        logger.info("Generating {} barcode for data: {!r}", barcode_format.upper(), data)
        logger.debug("Raw mode: {}", raw)
        try:
            barcode_instance, writer_options = self._create_barcode_instance(data, barcode_format)
            buffer = BytesIO()
            barcode_instance.write(buffer, writer_options)
            buffer.seek(0)
            if raw:
                response = Response(
                    buffer.getvalue(),
                    content_type='image/png',
                    headers={
                        'Content-Type': 'image/png',
                        'Content-Length': str(len(buffer.getvalue())),
                        'Cache-Control': 'no-cache, no-store, must-revalidate',
                        'Pragma': 'no-cache',
                        'Expires': '0',
                        'Content-Disposition': f'inline; filename=barcode_{barcode_format}.png'
                    }
                )
                return response
            return self._create_json_response(buffer, data, barcode_format, writer_options)
        except ValueError as e:
            logger.warning("Validation error for {} barcode: {}", barcode_format.upper(), str(e))
            return self._error_response(str(e), 400)
        except Exception as e:
            logger.exception("Failed to generate {} barcode: {}", barcode_format.upper(), str(e))
            return self._error_response(f"Failed to generate barcode: {str(e)}", 500)

    def _create_json_response(self, buffer: BytesIO, data: str, barcode_format: str,
                              writer_options: Optional[Dict[str, Any]] = None) -> Response:
        buffer.seek(0)
        base64_encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
        serializable_options = {}
        if writer_options:
            for key, value in writer_options.items():
                if isinstance(value, (str, int, float, bool, type(None))):
                    serializable_options[key] = value
                elif isinstance(value, (list, dict, tuple)):
                    serializable_options[key] = str(value)
        response_data = {
            'barcode': f'data:image/png;base64,{base64_encoded}',
            'barcode_type': barcode_format,
            'data': data,
            'generated_at': datetime.utcnow().isoformat(),
            'options': serializable_options
        }
        return jsonify(response_data)

    def _error_response(self, message: str, status_code: int) -> Response:
        if status_code < 500:
            logger.warning("HTTP {}: {}", status_code, message)
        else:
            logger.error("HTTP {}: {}", status_code, message)
        response = jsonify({
            'error': message,
            'status': 'error',
            'status_code': status_code,
            'timestamp': datetime.now().isoformat()
        })
        response.status_code = status_code
        return response


# Create an instance of the BarcodeAPI
barcode_api = BarcodeAPI()

# Export the blueprint and URL prefix for use in the application
barcode_bp = barcode_api.bp
url_prefix = '/barcode'