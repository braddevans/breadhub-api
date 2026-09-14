import base64
from datetime import datetime
from io import BytesIO

from barcode.codex import Code128
from barcode.writer import ImageWriter
from flask import Blueprint, request, jsonify, Response

from app.logging_config import logger
from app.middleware import error_response

from . import BaseRoute

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

    def _get_writer_options(self):
        options = self.DEFAULT_OPTIONS.copy()
        
        font_family = request.args.get('font_family', 'Roboto')
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
                options[key] = float(value) if value.replace('.', '', 1).isdigit() else options.get(key)
            elif key in int_options:
                options[key] = int(float(value)) if value.isdigit() else options.get(key)
            elif key in str_options:
                options[key] = value
            elif key == 'format':
                options['format'] = value.upper() if value.upper() in {'PNG', 'JPEG', 'GIF', 'BMP', 'TIFF'} else 'PNG'
                
        return options

    def list_all_writer_options(self):
        """Return default writer options for Code128."""
        serializable_opts = {k: v for k, v in self.DEFAULT_OPTIONS.items() 
                           if isinstance(v, (str, int, float, bool, type(None)))}
        return jsonify({
            "formats": {"code128": serializable_opts},
            "allowed_image_formats": ["PNG", "JPEG", "GIF", "BMP", "TIFF"]
        })

    def generate_barcode(self):
        try:
            data = request.args.get('data')
            if not data:
                return error_response('Missing required parameter: data', 400)
            if request.args.get('uppercase', 'false').lower() == 'true':
                data = data.upper()
            raw = request.args.get('raw', 'false').lower() == 'true'
            return self._create_barcode_response(data, raw)
        except Exception as e:
            logger.error(f"Error generating barcode: {str(e)}", exc_info=True)
            return error_response(str(e), 500)

    def _create_barcode_response(self, data, raw=False):
        logger.debug("Generating Code128 barcode for data: {!r}", data)
        try:
            writer_options = self._get_writer_options()
            barcode_instance = Code128(data, writer=ImageWriter())
            
            buffer = BytesIO()
            barcode_instance.write(buffer, options=writer_options)
            buffer.seek(0)
            
            if raw:
                return Response(
                    buffer.getvalue(),
                    content_type='image/png',
                    headers={
                        'Content-Type': 'image/png',
                        'Content-Length': str(len(buffer.getvalue())),
                        'Content-Disposition': 'inline; filename=barcode_code128.png'
                    }
                )
            return self._create_json_response(buffer, data, writer_options)
        except ValueError as e:
            return error_response(str(e), 400)
        except Exception as e:
            logger.error("Failed to generate Code128 barcode: {}", str(e))
            return error_response(f"Failed to generate barcode: {str(e)}", 500)

    def _create_json_response(self, buffer, data, writer_options=None):
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
            'barcode': f'data:image/png;base64,{base64_encoded}',
            'barcode_type': 'code128',
            'data': data,
            'generated_at': datetime.utcnow().isoformat(),
            'options': serializable_options
        })

# Create and export the blueprint
barcode_bp, url_prefix = BarcodeAPI.create()