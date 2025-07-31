import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Type, Any, Optional, List, ClassVar, TypeVar
from flask import Blueprint, request, jsonify, send_file, Response
from io import BytesIO
from pathlib import Path
from barcode.writer import ImageWriter
from barcode.codex import Code39, Code128, PZN, Gs1_128, PZN7
from barcode.ean import EuropeanArticleNumber13, JAN, EuropeanArticleNumber8 as EAN8, EuropeanArticleNumber13WithGuard as EAN13_GUARD
from barcode.isxn import InternationalStandardBookNumber13, InternationalStandardBookNumber10, InternationalStandardSerialNumber
from barcode.upc import UniversalProductCodeA
from loguru import logger

# Import base class for type hints
from barcode.ean import EAN13  # Using EAN13 as the base class for type hints

# Type variable for barcode classes
BarcodeType = TypeVar('BarcodeType', bound=EAN13)  # Using EAN13 as the base class


@dataclass
class BarcodeConfig:
    barcode_class: Type[EuropeanArticleNumber13]
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
    BARCODE_CONFIGS: ClassVar[Dict[str, BarcodeConfig]] = {
        'code39': BarcodeConfig(
            barcode_class=Code39,
            default_options={
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
                'dpi': 300
            }
        ),
        'code128': BarcodeConfig(
            barcode_class=Code128,
            default_options={
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
                'dpi': 300
            }
        ),
        'ean13': BarcodeConfig(
            barcode_class=EAN13_GUARD,
            default_options={
                'writer': ImageWriter(),
                'module_width': 0.4,
                'module_height': 12.0,
                'quiet_zone': 6.5,
                'font_size': 12,
                'text_distance': 5.0,
                'center_text': True,
                'background': 'white',
                'foreground': 'black',
                'dpi': 300,
                'format': 'PNG'
            },
            requires_checksum=True
        ),
        'ean8': BarcodeConfig(
            barcode_class=EAN8,
            default_options={
                'writer': ImageWriter(),
                'write_text': True
            },
            requires_checksum=True
        ),
        'upca': BarcodeConfig(
            barcode_class=UniversalProductCodeA,
            default_options={
                'writer': ImageWriter(),
                'write_text': True
            },
            requires_checksum=True
        ),
        'isbn13': BarcodeConfig(
            barcode_class=InternationalStandardBookNumber13,
            default_options={
                'writer': ImageWriter(),
                'write_text': True
            },
            requires_checksum=True
        ),
        'isbn10': BarcodeConfig(
            barcode_class=InternationalStandardBookNumber10,
            default_options={
                'writer': ImageWriter(),
                'write_text': True
            },
            requires_checksum=True
        ),
        'issn': BarcodeConfig(
            barcode_class=InternationalStandardSerialNumber,
            default_options={
                'writer': ImageWriter(),
                'write_text': True
            },
            requires_checksum=True
        ),
        'pzn': BarcodeConfig(
            barcode_class=PZN,
            default_options={
                'writer': ImageWriter(),
                'write_text': True
            },
            requires_checksum=True
        ),
        'pzn7': BarcodeConfig(
            barcode_class=PZN7,
            default_options={
                'writer': ImageWriter(),
                'write_text': True
            },
            requires_checksum=True
        ),
        'gs1_128': BarcodeConfig(
            barcode_class=Gs1_128,
            default_options={
                'writer': ImageWriter(),
                'write_text': True
            }
        ),
        'jan': BarcodeConfig(
            barcode_class=JAN,
            default_options={
                'writer': ImageWriter(),
                'write_text': True
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
    
    def __init__(self):
        """Initialize the BarcodeAPI with default settings and register routes."""
        self.bp = Blueprint('barcode', __name__)
        # Register routes - use root path since the blueprint will be mounted at /barcode
        self.bp.route('/', methods=['GET'])(self.generate_barcode)
        self.bp.route('/fonts', methods=['GET'])(self.list_fonts)
    
    def generate_barcode(self):
        """
        Generate a barcode image.
        
        Query Parameters:
            data (str): The data to encode in the barcode (required)
            format (str): Barcode format (default: code128)
            raw (bool): If true, returns raw PNG image. If false (default), returns JSON with base64-encoded image
            
        Returns:
            Response: Either a JSON response with the barcode data or a raw PNG image
        """
        try:
            # Get request parameters
            data = request.args.get('data')
            if not data:
                return self._error_response('Missing required parameter: data', 400)
                
            # Convert data to uppercase if requested
            if request.args.get('uppercase', 'false').lower() == 'true':
                data = data.upper()
                
            barcode_format = request.args.get('format', 'code128').lower()
            raw = request.args.get('raw', 'false').lower() == 'true'
            
            # Validate barcode format
            try:
                self.get_barcode_config(barcode_format)
            except ValueError:
                return self._error_response(
                    f'Unsupported barcode format. Supported formats: {list(self.BARCODE_CONFIGS.keys())}',
                    400
                )
            
            # Generate and return the barcode
            return self._create_barcode_response(data, barcode_format, raw)
            
        except Exception as e:
            logger.error(f"Error generating barcode: {str(e)}", exc_info=True)
            return self._error_response(str(e), 500)
    
    def _get_available_fonts(self) -> Dict[int, str]:
        """
        Get a dictionary of available fonts in the fonts directory.
        
        Returns:
            Dict[int, str]: Dictionary mapping font numbers to font file paths
        """
        fonts_dir = Path('fonts')
        if not fonts_dir.exists():
            return {}
            
        # Supported font extensions
        font_exts = {'.ttf', '.otf'}
        
        # Get all font files and map to numbers starting from 1
        fonts = {}
        for i, font_file in enumerate(sorted(fonts_dir.glob('*')), 1):
            if font_file.suffix.lower() in font_exts and font_file.is_file():
                fonts[i] = str(font_file.absolute())
                
        return fonts
        
    def _get_font_path(self, font_id: Optional[str] = None) -> Optional[str]:
        """
        Get font path by ID or return default (None).
        
        Args:
            font_id: Font ID as string (will be converted to int)
            
        Returns:
            Optional[str]: Path to the selected font or None for default
        """
        if not font_id:
            return None
            
        try:
            font_id = int(font_id)
            fonts = self._get_available_fonts()
            return fonts.get(font_id)
        except (ValueError, TypeError):
            return None
    
    def _get_writer_options(self, barcode_format: str = None) -> dict:
        """
        Get the writer options from request parameters with defaults.
        
        Args:
            barcode_format: The type of barcode being generated (e.g., 'EAN13')
            
        Returns:
            dict: Dictionary of writer options
        """
        # Get the barcode config if format is provided
        config = None
        if barcode_format:
            try:
                config = self.get_barcode_config(barcode_format)
            except ValueError:
                pass  # Use default options if format is not recognized
        
        # Start with default options from config or empty dict
        options = {}
        if config and config.default_options:
            options.update(config.default_options)
        
        # Get font by ID if provided
        font_path = self._get_font_path(request.args.get('font_id'))
        if font_path is not None:
            options['font_path'] = font_path
        
        # Get text and apply uppercase if requested
        text = request.args.get('text', '')
        if request.args.get('uppercase', 'false').lower() == 'true':
            text = text.upper()
        
        # Ensure format is a valid image format (PNG, JPEG, etc.)
        output_format = request.args.get('format')
        if output_format:
            output_format = output_format.upper()
            if output_format not in ['PNG', 'JPEG', 'GIF', 'BMP', 'TIFF']:
                output_format = 'PNG'  # Default to PNG if format is not recognized
            options['format'] = output_format
        
        # Update options from request parameters
        bool_params = ['write_text', 'center_text']
        float_params = [
            'module_width', 'module_height', 'quiet_zone',
            'text_distance', 'dpi'
        ]
        int_params = ['font_size']
        
        # Handle boolean parameters
        for param in bool_params:
            if param in request.args:
                options[param] = request.args.get(param, 'true').lower() == 'true'
        
        # Handle float parameters
        for param in float_params:
            if param in request.args:
                try:
                    options[param] = float(request.args[param])
                except (ValueError, TypeError):
                    pass  # Keep default if conversion fails
        
        # Handle integer parameters
        for param in int_params:
            if param in request.args:
                try:
                    options[param] = int(request.args[param])
                except (ValueError, TypeError):
                    pass  # Keep default if conversion fails
        
        # Handle color parameters
        for color_param in ['background', 'foreground']:
            if color_param in request.args:
                options[color_param] = request.args[color_param]
        
        # Set the text if provided
        if text:
            options['text'] = text
            
        return options
        
    def list_fonts(self):
        """
        List all available fonts with their IDs.
        
        Returns:
            Response: JSON response with available fonts
        """
        fonts = self._get_available_fonts()
        return jsonify({
            'fonts': [{'id': k, 'name': Path(v).name} for k, v in fonts.items()],
            'count': len(fonts)
        })

    def _validate_barcode_data(self, data: str, barcode_format: str) -> None:
        """
        Validate the barcode data against the format requirements.
        
        Args:
            data: The data to validate
            barcode_format: The barcode format
            
        Raises:
            ValueError: If the data is invalid for the given format
        """
        config = self.get_barcode_config(barcode_format)
        
        if not config.validate_data(data):
            if config.requires_checksum and not data.isdigit():
                raise ValueError(f"{barcode_format.upper()} requires numeric input")
            if len(data) < config.min_length or len(data) > config.max_length:
                raise ValueError(
                    f"{barcode_format.upper()} requires data length between "
                    f"{config.min_length} and {config.max_length} characters"
                )
    
    def _create_barcode_instance(self, data: str, barcode_format: str):
        """
        Create a barcode instance with the given data and format.
        
        Args:
            data: The data to encode
            barcode_format: The barcode format
            
        Returns:
            A tuple of (barcode_instance, writer_options)
        """
        config = self.get_barcode_config(barcode_format)
        
        # Create a copy of the default options
        writer_options = config.default_options.copy()
        
        # Remove writer options that shouldn't be passed to the barcode constructor
        barcode_kwargs = {}
        for key in ['writer']:  # Only pass writer to constructor
            if key in writer_options:
                barcode_kwargs[key] = writer_options.pop(key)
        
        # Create the barcode instance with only the allowed options
        barcode_instance = config.barcode_class(data, writer=ImageWriter())
        
        return barcode_instance, writer_options
    
    def _create_barcode_response(self, data: str, barcode_format: str, raw: bool = False) -> Response:
        """
        Create a barcode and return the appropriate response.
        
        Args:
            data: The data to encode in the barcode
            barcode_format: The format of the barcode
            raw: Whether to return a raw PNG image or a JSON response
            
        Returns:
            Response: Either a JSON response or a raw PNG image
        """
        logger.info("Generating {} barcode for data: {!r}", barcode_format.upper(), data)
        logger.debug("Raw mode: {}", raw)
        
        try:
            config = self.get_barcode_config(barcode_format)
            logger.debug("Using barcode config: {}", config)
            
            barcode_instance, writer_options = self._create_barcode_instance(data, barcode_format)
            logger.debug("Created barcode instance: {}", barcode_instance.__class__.__name__)
            
            request_writer_options = self._get_writer_options(barcode_format)
            writer_options.update(request_writer_options)
            logger.debug("Merged writer options: {}", writer_options)
            
            if not writer_options.get('text'):
                writer_options['text'] = data
                logger.debug("Set default text to input data")
            
            if 'writer' not in writer_options:
                writer_options['writer'] = ImageWriter()
                logger.debug("Added default ImageWriter")
            
            buffer = BytesIO()
            barcode_instance.write(buffer, writer_options)
            buffer.seek(0)
            
            logger.success("Successfully generated {} barcode", barcode_format.upper())
            
            if raw:
                format_type = writer_options.get("format", "png").lower()
                logger.debug("Returning raw {} image", format_type)
                return send_file(
                    buffer,
                    mimetype=f'image/{format_type}',
                    as_attachment=False,
                    download_name=f'barcode.{format_type}'
                )
                
            logger.debug("Returning JSON response")
            return self._create_json_response(buffer, data, barcode_format, writer_options)
                
        except ValueError as e:
            logger.warning("Validation error for {} barcode: {}", barcode_format.upper(), str(e))
            return self._error_response(str(e), 400)
        except Exception as e:
            logger.exception("Failed to generate {} barcode: {}", barcode_format.upper(), str(e))
            return self._error_response(f"Failed to generate barcode: {str(e)}", 500)
    
    def _create_json_response(self, buffer: BytesIO, data: str, barcode_format: str, writer_options: Optional[Dict[str, Any]] = None) -> Response:
        """
        Create a JSON response with the barcode data.
        
        Args:
            buffer: The buffer containing the barcode image
            data: The original data that was encoded
            barcode_format: The format of the barcode
            writer_options: The writer options used to generate the barcode
            
        Returns:
            Response: A Flask Response object containing the JSON data
        """
        # Convert the buffer to base64
        buffer.seek(0)
        base64_encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # Filter out non-serializable objects from writer_options
        serializable_options = {}
        if writer_options:
            for key, value in writer_options.items():
                # Skip non-serializable objects like ImageWriter
                if isinstance(value, (str, int, float, bool, type(None))):
                    serializable_options[key] = value
                elif isinstance(value, (list, dict, tuple)):
                    # For nested structures, we'll just include their string representation
                    serializable_options[key] = str(value)
        
        # Create the response data
        response_data = {
            'barcode': f'data:image/png;base64,{base64_encoded}',
            'barcode_type': barcode_format,
            'data': data,
            'generated_at': datetime.utcnow().isoformat(),
            'options': serializable_options
        }
        
        # Convert to a proper Flask Response object
        return jsonify(response_data)
    
    def _error_response(self, message: str, status_code: int) -> Response:
        """
        Create an error response.
        
        Args:
            message: The error message
            status_code: The HTTP status code
            
        Returns:
            Response: A Flask Response object containing the error message
        """
        if status_code < 500:
            logger.warning("HTTP {}: {}", status_code, message)
        else:
            logger.error("HTTP {}: {}", status_code, message)
        
        response = jsonify({
            'error': message,
            'status': 'error',
            'status_code': status_code,
            'timestamp': datetime.utcnow().isoformat()
        })
        response.status_code = status_code
        return response

# Create an instance of the BarcodeAPI
barcode_api = BarcodeAPI()

# Export the blueprint and URL prefix for use in the application
barcode_bp = barcode_api.bp
url_prefix = '/barcode'
