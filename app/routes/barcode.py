import base64
import re
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import barcode
from barcode.errors import BarcodeError
from barcode.writer import ImageWriter, mm2px, pt2mm
from PIL import ImageFont
from flask import request, jsonify, Response

from app.logging_config import logger
from app.middleware import error_response

from . import BaseRoute

# Root of the `app` package, used to resolve bundled font paths such as
# 'fonts/lato.ttf' regardless of the process working directory.
APP_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = APP_ROOT / 'fonts'

# Bundled font files by lowercased name. Font family names are lowercased to
# build the filename, but some files are capitalised (Lato.ttf, Barlow.ttf).
FONT_FILES = {f.name.lower(): f for f in FONTS_DIR.glob('*.ttf')}

# Symbologies the API accepts, in the order the UI lists them. Each entry
# drives validation, the generator's type picker and the API reference page.
BARCODE_TYPES = {
    'code128': {'label': 'Code 128', 'example': 'CODE128',
                'requirements': 'Any ASCII text.'},
    'gs1_128': {'label': 'GS1-128', 'example': '0101234567890128',
                'requirements': 'GS1 application identifiers followed by their data.'},
    'code39': {'label': 'Code 39', 'example': 'TEST-39',
               'requirements': 'A\u2013Z, 0\u20139, space and - . $ / + %. Lowercase is uppercased; a check character is added.'},
    'codabar': {'label': 'Codabar', 'example': 'A40156B',
                'requirements': 'Digits and - $ : / . +, starting and ending with a letter A\u2013D.'},
    'itf': {'label': 'ITF (Interleaved 2 of 5)', 'example': '1234567890',
            'requirements': 'Digits only. An odd count is padded with a leading zero.'},
    'ean13': {'label': 'EAN-13', 'example': '590123412345',
              'requirements': '12 digits, or 13 including the check digit, which must be correct.'},
    'ean13-guard': {'label': 'EAN-13 with guard bars', 'example': '590123412345',
                    'requirements': '12 digits, or 13 including the check digit, which must be correct.'},
    'ean8': {'label': 'EAN-8', 'example': '9638507',
             'requirements': '7 digits, or 8 including the check digit, which must be correct.'},
    'ean8-guard': {'label': 'EAN-8 with guard bars', 'example': '9638507',
                   'requirements': '7 digits, or 8 including the check digit, which must be correct.'},
    'ean14': {'label': 'GTIN-14 (ITF-14)', 'example': '1234567890123',
              'requirements': '13 digits, or 14 including the check digit, which must be correct. '
                              'Printed as ITF-14, the symbology used on cartons.'},
    'upca': {'label': 'UPC-A', 'example': '03600029145',
             'requirements': '11 digits, or 12 including the check digit, which must be correct.'},
    'jan': {'label': 'JAN', 'example': '490123456789',
            'requirements': '12 digits starting 450\u2013460 or 490\u2013500, or 13 including a correct check digit.'},
    'isbn13': {'label': 'ISBN-13', 'example': '978316148410',
               'requirements': '12 digits starting 978 or 979, or 13 including a correct check digit. Hyphens are ignored.'},
    'isbn10': {'label': 'ISBN-10', 'example': '316148410',
               'requirements': '9 digits, or 10 including a correct check character (0\u20139 or X). '
                               'Printed as the equivalent ISBN-13.'},
    'issn': {'label': 'ISSN', 'example': '0317847',
             'requirements': '7 digits, or 8 including a correct check character (0\u20139 or X). '
                             'Printed as the ISSN\u2019s EAN-13 (977 prefix).'},
    'pzn': {'label': 'PZN', 'example': '123456',
            'requirements': '6 digits. The check digit is calculated.'},
}

# Types that end in a check digit python-barcode calculates. It silently
# replaces a wrong one, so when the caller includes it we verify it instead.
CHECK_DIGIT_TYPES = {'ean13', 'ean13-guard', 'ean8', 'ean8-guard', 'upca', 'jan', 'isbn13'}

# Types whose caption python-barcode splits into blocks printed between the
# guard bars. Every EAN digit is 7 modules wide, which sets the gap available
# to each block.
GUARD_BAR_TYPES = {'ean13-guard', 'ean8-guard'}
MODULES_PER_EAN_DIGIT = 7

# Share of the available width the caption may fill, leaving a little air
# between the text and the bars either side of it.
CAPTION_FILL = 0.9

class GuardCaptionWriter(ImageWriter):
    """
    ImageWriter that can drop guard-bar captions lower.

    For guard-bar types python-barcode puts the caption's bottom at
    module_height + font size, ignoring text_distance, so the digits start
    right where the bars end and read as overlapping them. `caption_offset`
    (mm) moves them down to where every other type's caption sits.
    """
    caption_offset = 0.0

    def _paint_text(self, xpos, ypos):
        super()._paint_text(xpos, ypos + self.caption_offset)


# Other common names for the same symbologies.
BARCODE_TYPE_ALIASES = {
    'ean': 'ean13',
    'gtin': 'ean14',
    'upc': 'upca',
    'isbn': 'isbn13',
    'nw-7': 'codabar',
}

# Matches the default selected in the barcode generator UI.
DEFAULT_FONT_FAMILY = 'Typo Round Bold'

# Font family names the API accepts, derived from the bundled .ttf files
# ('typo-round-bold.ttf' -> 'Typo Round Bold').
FONT_FAMILIES = sorted(f.stem.replace('-', ' ').title() for f in FONT_FILES.values())

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
        'dpi': 300,
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

        match = FONT_FILES.get(candidate.name.lower())
        if match is not None:
            return str(match)

        logger.warning("Font not found, falling back to default: {}", font_path)
        return None

    def _get_writer_options(self):
        options = self.DEFAULT_OPTIONS.copy()

        font_family = request.args.get('font_family', DEFAULT_FONT_FAMILY)
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
                    key, int(value)
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
        """Return the default writer options, which every barcode type shares."""
        serializable_opts = {k: v for k, v in self.DEFAULT_OPTIONS.items()
                           if isinstance(v, (str, int, float, bool, type(None)))}
        return jsonify({
            "formats": {name: serializable_opts for name in BARCODE_TYPES},
            "barcode_types": {name: spec['label'] for name, spec in BARCODE_TYPES.items()},
            "allowed_image_formats": sorted(IMAGE_FORMAT_MIMETYPES)
        })

    def generate_barcode(self):
        data = request.args.get('data')
        if not data:
            return error_response('Missing required parameter: data', 400)

        barcode_type = request.args.get('type', 'code128').strip().lower()
        barcode_type = BARCODE_TYPE_ALIASES.get(barcode_type, barcode_type)
        if barcode_type not in BARCODE_TYPES:
            return error_response(
                f"Unsupported barcode format: {barcode_type}. "
                f"Supported: {', '.join(BARCODE_TYPES)}",
                400
            )

        if request.args.get('uppercase', 'false').lower() == 'true':
            data = data.upper()
        raw = request.args.get('raw', 'false').lower() == 'true'
        return self._create_barcode_response(data, barcode_type, raw)

    @staticmethod
    def _render(barcode_type, data, options, caption):
        """
        Encode `data` and write the image, returning (buffer, encoded text).

        python-barcode reports bad input as BarcodeError, a bare ValueError
        from int() (JAN, ISSN) or a KeyError for an unknown Code 39 character.
        All of those are the caller's fault, so they become one ValueError
        with a readable message, which the caller maps to a 400.
        """
        label = BARCODE_TYPES[barcode_type]['label']
        library_type, library_data = BarcodeAPI._translate(barcode_type, data)
        try:
            writer = GuardCaptionWriter() if barcode_type in GUARD_BAR_TYPES else ImageWriter()
            instance = barcode.get_barcode_class(library_type)(library_data, writer=writer)
            encoded = instance.get_fullcode()
        except (BarcodeError, ValueError, KeyError) as e:
            raise ValueError(f"Invalid data for {label}: {BarcodeAPI._describe(e)}") from e

        if barcode_type in CHECK_DIGIT_TYPES:
            given, expected = re.sub(r'\D', '', data), re.sub(r'\D', '', encoded)
            if len(given) == len(expected) and given != expected:
                raise ValueError(
                    f"Invalid data for {label}: check digit should be {expected[-1]}, not {given[-1]}"
                )

        options = BarcodeAPI._snap_to_pixels(dict(options))
        buffer = BytesIO()
        try:
            # Inside the try: some types (Codabar) only validate in build(),
            # which sizing the caption calls.
            if options.get('write_text', True):
                options['font_size'] = BarcodeAPI._fit_font_size(
                    instance, barcode_type, options, caption or encoded
                )
                if barcode_type in GUARD_BAR_TYPES:
                    BarcodeAPI._place_guard_caption(writer, options)
            instance.write(buffer, options=options, text=caption)
        except (BarcodeError, KeyError) as e:
            raise ValueError(f"Invalid data for {label}: {BarcodeAPI._describe(e)}") from e
        buffer.seek(0)
        return buffer, encoded

    @staticmethod
    def _fit_font_size(instance, barcode_type, options, text):
        """
        Largest font size, up to the one requested, at which the caption fits.

        python-barcode never shrinks text, so a wide font or narrow modules
        print the caption over the bars: on guard-bar types each digit block
        overlaps the guards around it, elsewhere the caption runs past the
        edges of the image. Text width scales linearly with point size, so
        one measurement at a reference size gives the size that fits.
        """
        requested = options.get('font_size', BarcodeAPI.DEFAULT_OPTIONS['font_size'])
        module_width = options.get('module_width', BarcodeAPI.DEFAULT_OPTIONS['module_width'])
        font_path = options.get('font_path') or ImageWriter().font_path
        try:
            font = ImageFont.truetype(font_path, 100)
        except OSError:
            return requested

        def width_mm(block, size):
            return font.getlength(block) / 100 * pt2mm(size)

        if barcode_type in GUARD_BAR_TYPES:
            # The first and last blocks sit outside the guards, in the quiet
            # zone; only the blocks between guards are boxed in.
            blocks = [(b, len(b) * MODULES_PER_EAN_DIGIT * module_width)
                      for b in text.split(' ')[1:-1] if b]
        else:
            modules = len(instance.build()[0])
            quiet_zone = options.get('quiet_zone', BarcodeAPI.DEFAULT_OPTIONS['quiet_zone'])
            available = modules * module_width + quiet_zone
            blocks = [(line, available) for line in text.splitlines() if line]

        size = requested
        for block, available in blocks:
            needed = width_mm(block, size)
            if needed > available * CAPTION_FILL:
                size = min(size, available * CAPTION_FILL / needed * size)
        return max(1, int(size))

    @staticmethod
    def _translate(barcode_type, data):
        """
        Map a request to the python-barcode type and data that print it.

        python-barcode 0.16's ISBN-10 and ISSN classes truncate the EAN-13
        they build (their `digits` attribute is reused by the EAN-13 code),
        and its EAN-14 draws a 102-module pattern no scanner reads. These
        types are converted here and printed with classes that work: ISBN-10
        as its ISBN-13, ISSN as its 977 EAN-13 and GTIN-14 as ITF-14.
        Everything else passes through unchanged.
        """
        label = BARCODE_TYPES[barcode_type]['label']
        compact = re.sub(r'[\s-]', '', data).upper()

        if barcode_type == 'isbn10':
            if not re.fullmatch(r'\d{9}[\dX]?', compact):
                raise ValueError(f"Invalid data for {label}: expected 9 digits, or 10 including the check character")
            check = sum(i * int(d) for i, d in enumerate(compact[:9], start=1)) % 11
            BarcodeAPI._verify_check(label, compact, 'X' if check == 10 else str(check), 10)
            return 'isbn13', '978' + compact[:9]

        if barcode_type == 'issn':
            if not re.fullmatch(r'\d{7}[\dX]?', compact):
                raise ValueError(f"Invalid data for {label}: expected 7 digits, or 8 including the check character")
            check = -sum(w * int(d) for w, d in zip(range(8, 1, -1), compact[:7])) % 11
            BarcodeAPI._verify_check(label, compact, 'X' if check == 10 else str(check), 8)
            return 'ean13', '977' + compact[:7] + '00'

        if barcode_type == 'ean14':
            if not re.fullmatch(r'\d{13,14}', compact):
                raise ValueError(f"Invalid data for {label}: expected 13 digits, or 14 including the check digit")
            check = BarcodeAPI._gs1_check_digit(compact[:13])
            BarcodeAPI._verify_check(label, compact, check, 14)
            return 'itf', compact[:13] + check

        return barcode_type, data

    @staticmethod
    def _gs1_check_digit(digits):
        """GS1 mod-10 check digit: weights 3 and 1 alternating from the right."""
        total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
        return str(-total % 10)

    @staticmethod
    def _verify_check(label, compact, expected, full_length):
        if len(compact) == full_length and compact[-1] != expected:
            raise ValueError(f"Invalid data for {label}: check digit should be {expected}, not {compact[-1]}")

    @staticmethod
    def _snap_to_pixels(options):
        """
        Round the module width and quiet zone to whole pixels at the output DPI.

        The writer converts each bar edge from mm to a fractional pixel and
        Pillow rounds every edge on its own, so a module of, say, 1.18 px
        comes out as a mix of 1 and 2 px bars. Barcodes encode data in
        those widths, so the result does not scan. Whole-pixel modules
        starting on a whole pixel keep every bar of a width identical.
        """
        dpi = options.get('dpi', BarcodeAPI.DEFAULT_OPTIONS['dpi'])
        px_per_mm = mm2px(1, dpi)
        for key, minimum_px in (('module_width', 1), ('quiet_zone', 0)):
            value = options.get(key, BarcodeAPI.DEFAULT_OPTIONS[key])
            # The writer draws a bar from x to x + width - 1; for a 1 px bar,
            # float error can put that end a hair before the start, which
            # Pillow rejects. A millionth of a pixel extra keeps the order
            # without changing how either edge rounds.
            options[key] = (max(minimum_px, round(value * px_per_mm)) + 1e-6) / px_per_mm
        return options

    @staticmethod
    def _place_guard_caption(writer, options):
        """
        Put a guard-bar caption on the same baseline as other types' captions
        (text_distance below the bars) and stretch the guard bars down to the
        middle of the digits, as on a printed EAN.
        """
        module_height = options.get('module_height', BarcodeAPI.DEFAULT_OPTIONS['module_height'])
        text_distance = options.get('text_distance', BarcodeAPI.DEFAULT_OPTIONS['text_distance'])
        font_mm = pt2mm(options['font_size'])

        writer.caption_offset = max(0.0, text_distance - font_mm)
        baseline = module_height + font_mm + writer.caption_offset
        options['guard_height_factor'] = max(1.1, (baseline - font_mm / 2) / module_height)

    @staticmethod
    def _describe(error):
        if isinstance(error, KeyError):
            return f"character {error} is not allowed"
        if isinstance(error, ValueError) and not isinstance(error, BarcodeError):
            return "only digits are allowed"
        return str(error)

    def _create_barcode_response(self, data, barcode_type='code128', raw=False):
        logger.debug("Generating {} barcode for data: {!r}", barcode_type, data)
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

            # python-barcode ignores a 'text' option and prints the encoded data
            # unless the caption is passed to write() itself. Passing it also
            # forces the caption on, so only do so when text is shown.
            caption = render_options.pop('text', None) or None
            if not render_options.get('write_text', True):
                caption = None

            buffer, encoded = self._render(barcode_type, data, render_options, caption)

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
                        'Content-Disposition': f'inline; filename=barcode_{barcode_type}.{extension}'
                    }
                )
            return self._create_json_response(buffer, data, barcode_type, encoded, writer_options, mimetype)
        except ValueError as e:
            return error_response(str(e), 400)
        except Exception as e:
            logger.exception("Failed to generate {} barcode: {}", barcode_type, e)
            return error_response(f"Failed to generate barcode: {str(e)}", 500)

    @staticmethod
    def _create_json_response(buffer, data, barcode_type, encoded, writer_options=None, mimetype='image/png'):
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
            'barcode_type': barcode_type,
            'data': data,
            'encoded': encoded,
            'generated_at': datetime.now(UTC).isoformat(),
            'options': serializable_options
        })

def create_blueprint():
    """Entry point used by app.routes.init_app to register this module."""
    return BarcodeAPI.create()


def _limits(key, unit=''):
    low, high = NUMERIC_LIMITS[key]
    return f"{low:g}–{high:g}{unit}"


def _default(key):
    value = BarcodeAPI.DEFAULT_OPTIONS[key]
    return str(value).lower() if isinstance(value, bool) else str(value)


# Query parameters of GET /api/barcode, grouped for the API reference page.
# Defaults and ranges come from the constants above so the docs cannot drift.
PARAMETER_GROUPS = [
    ('Request', [
        {'name': 'data', 'type': 'string', 'required': True, 'default': None,
         'allowed': 'Depends on type', 'description': 'The value to encode.'},
        {'name': 'type', 'type': 'string', 'default': 'code128',
         'allowed': 'See barcode types below', 'description': 'Barcode symbology.'},
        {'name': 'raw', 'type': 'boolean', 'default': 'false', 'allowed': 'true, false',
         'description': 'Return the image itself instead of JSON with a base64 data URI.'},
        {'name': 'format', 'type': 'string', 'default': 'PNG',
         'allowed': ', '.join(IMAGE_FORMAT_MIMETYPES), 'description': 'Image format. Unknown values fall back to PNG.'},
        {'name': 'uppercase', 'type': 'boolean', 'default': 'false', 'allowed': 'true, false',
         'description': 'Uppercase the data before encoding.'},
    ]),
    ('Bars', [
        {'name': 'module_width', 'type': 'number', 'default': _default('module_width'),
         'allowed': _limits('module_width', ' mm'), 'description': 'Width of the narrowest bar.'},
        {'name': 'module_height', 'type': 'number', 'default': _default('module_height'),
         'allowed': _limits('module_height', ' mm'), 'description': 'Height of the bars.'},
        {'name': 'quiet_zone', 'type': 'number', 'default': _default('quiet_zone'),
         'allowed': _limits('quiet_zone', ' mm'), 'description': 'Blank margin either side of the bars.'},
        {'name': 'dpi', 'type': 'number', 'default': _default('dpi'),
         'allowed': _limits('dpi'), 'description': 'Output resolution.'},
    ]),
    ('Text', [
        {'name': 'write_text', 'type': 'boolean', 'default': _default('write_text'),
         'allowed': 'true, false', 'description': 'Print the human-readable text under the bars.'},
        {'name': 'center_text', 'type': 'boolean', 'default': _default('center_text'),
         'allowed': 'true, false', 'description': 'Centre the text under the bars.'},
        {'name': 'text', 'type': 'string', 'default': None,
         'allowed': 'Any text', 'description': 'Print this instead of the encoded data.'},
        {'name': 'font_family', 'type': 'string', 'default': DEFAULT_FONT_FAMILY,
         'allowed': ', '.join(FONT_FAMILIES), 'description': 'Bundled font for the text. Unknown fonts use the writer default.'},
        {'name': 'font_size', 'type': 'integer', 'default': _default('font_size'),
         'allowed': _limits('font_size', ' pt'), 'description': 'Text size.'},
        {'name': 'text_distance', 'type': 'number', 'default': _default('text_distance'),
         'allowed': _limits('text_distance', ' mm'), 'description': 'Gap between the bars and the text.'},
    ]),
    ('Colours', [
        {'name': 'foreground', 'type': 'colour', 'default': _default('foreground'),
         'allowed': 'Name or hex', 'description': 'Bar and text colour.'},
        {'name': 'background', 'type': 'colour', 'default': _default('background'),
         'allowed': 'Name or hex', 'description': 'Background colour.'},
    ]),
]
