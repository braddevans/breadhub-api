import io
from PIL import Image, UnidentifiedImageError
from flask import request, send_file, render_template
from werkzeug.exceptions import HTTPException

from app.logging_config import logger
from app.middleware import error_response

from . import BaseRoute

# Inclusive bounds for caller-supplied grid geometry. Without these, a single
# request can ask Pillow for a multi-gigapixel canvas.
SIZE_LIMITS = (16, 2048)
GAP_LIMITS = (0, 512)
MAX_IMAGES = 100
MAX_OUTPUT_PIXELS = 50_000_000

# Largest source image accepted, checked from the header before decoding so a
# small 'decompression bomb' file cannot expand into hundreds of MB of pixels.
MAX_INPUT_PIXELS = 40_000_000

GRADIENT_DIRECTIONS = {'horizontal', 'vertical', 'diagonal'}

# Resolution the gradient is interpolated at before being upscaled.
GRADIENT_STEPS = 256


class ImageGridAPI(BaseRoute):
    """Image Grid Generator API routes."""

    def __init__(self):
        super().__init__('imagegrid', url_prefix='/imagegrid')

    def _register_routes(self):
        """Register all image grid routes."""
        self.bp.route('', methods=['GET'], endpoint='imagegrid_page')(self.imagegrid_page)
        self.bp.route('/generate', methods=['POST'], endpoint='generate_grid')(self.generate_grid)

    @staticmethod
    def parse_color(color_str):
        """Parse color string as hex code or RGB tuple."""
        color_str = color_str.strip()
        invalid = ValueError(
            f"Invalid color format: {color_str}. Use hex (#ffffff) or RGB (255,255,255)"
        )

        # Check if hex code
        if color_str.startswith('#'):
            hex_code = color_str.lstrip('#')
            if len(hex_code) == 3:
                # Expand shorthand hex (e.g., #fff -> #ffffff)
                hex_code = ''.join([c * 2 for c in hex_code])
            if len(hex_code) != 6:
                raise ValueError(f"Invalid hex color: {color_str}")
            try:
                return tuple(int(hex_code[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                raise ValueError(f"Invalid hex color: {color_str}")

        # Parse as RGB tuple
        parts = color_str.split(',')
        if len(parts) != 3:
            raise invalid

        try:
            channels = tuple(int(part) for part in parts)
        except ValueError:
            raise invalid

        if any(not 0 <= channel <= 255 for channel in channels):
            raise ValueError(
                f"Invalid color format: {color_str}. RGB channels must be 0-255"
            )
        return channels

    @staticmethod
    def _grid_dimension(num_images):
        """Side length of the smallest square grid that fits num_images."""
        grid_dim = int(num_images ** 0.5)
        if grid_dim * grid_dim < num_images:
            grid_dim += 1  # Round up to make room for all images
        return grid_dim

    @staticmethod
    def _interpolate_color(start_color, end_color, ratio):
        """Interpolate between two RGB colors based on ratio."""
        return tuple(
            int(start_color[i] + (end_color[i] - start_color[i]) * ratio)
            for i in range(3)
        )

    @staticmethod
    def create_gradient_background(width, height, start_color, end_color, direction='horizontal'):
        """
        Create a gradient background image.

        The gradient is built once at low resolution and upscaled by Pillow,
        rather than interpolated per pixel in Python. The visual result is the
        same, but a full-size diagonal gradient drops from seconds of CPU to
        milliseconds.
        """
        if direction not in GRADIENT_DIRECTIONS:
            raise ValueError(
                f"Unknown gradient_direction: {direction}. "
                f"Supported: {', '.join(sorted(GRADIENT_DIRECTIONS))}"
            )

        steps = GRADIENT_STEPS
        span = steps - 1

        if direction == 'horizontal':
            small_size = (steps, 1)
            ratios = (x / span for x in range(steps))
        elif direction == 'vertical':
            small_size = (1, steps)
            ratios = (y / span for y in range(steps))
        else:  # diagonal
            small_size = (steps, steps)
            ratios = ((x + y) / (2 * span) for y in range(steps) for x in range(steps))

        small = Image.new('RGB', small_size)
        small.putdata([
            ImageGridAPI._interpolate_color(start_color, end_color, ratio)
            for ratio in ratios
        ])

        return small.resize((width, height), Image.Resampling.BILINEAR)

    def create_grid(self, images, gap=10, background_color=(255, 255, 255), gradient=None):
        """Create a square grid from resized images with specified gap and background."""
        if not images:
            raise ValueError("No images provided")

        img_size = images[0].size
        img_width, img_height = img_size

        # Calculate grid dimensions (ensure square output)
        grid_dim = self._grid_dimension(len(images))

        # Calculate total grid dimensions (square)
        grid_width = grid_dim * img_width + (grid_dim - 1) * gap
        grid_height = grid_dim * img_height + (grid_dim - 1) * gap

        # Create background
        if gradient:
            start_color, end_color, direction = gradient
            grid = self.create_gradient_background(grid_width, grid_height, start_color, end_color, direction)
        else:
            grid = Image.new('RGB', (grid_width, grid_height), background_color)

        # Paste images onto grid
        for idx, img in enumerate(images):
            row = idx // grid_dim
            col = idx % grid_dim

            x = col * (img_width + gap)
            y = row * (img_height + gap)

            grid.paste(img, (x, y))

        return grid

    def imagegrid_page(self):
        """Serve the image grid generator HTML page."""
        return render_template('imagegrid.html')

    @staticmethod
    def _bounded_int(name, raw, default, limits):
        """Parse an integer form field, rejecting junk and out-of-range values."""
        if raw is None or raw == '':
            return default

        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a whole number, got {raw!r}")

        low, high = limits
        if not low <= value <= high:
            raise ValueError(f"{name} must be between {low} and {high}, got {value}")
        return value

    def generate_grid(self):
        """Generate an image grid from uploaded files."""
        try:
            # Get form data
            gap = self._bounded_int('gap', request.form.get('gap'), 10, GAP_LIMITS)
            size = self._bounded_int('size', request.form.get('size'), 512, SIZE_LIMITS)
            bg_color = request.form.get('bg_color', '#ffffff')
            use_gradient = request.form.get('use_gradient') == 'true'
            gradient_start = request.form.get('gradient_start', '#ffffff')
            gradient_end = request.form.get('gradient_end', '#000000')
            gradient_direction = request.form.get('gradient_direction', 'horizontal').strip().lower()

            # Parse background color
            if use_gradient:
                if gradient_direction not in GRADIENT_DIRECTIONS:
                    raise ValueError(
                        f"Unknown gradient_direction: {gradient_direction}. "
                        f"Supported: {', '.join(sorted(GRADIENT_DIRECTIONS))}"
                    )
                start_color = self.parse_color(gradient_start)
                end_color = self.parse_color(gradient_end)
                gradient = (start_color, end_color, gradient_direction)
                background_color = None
            else:
                background_color = self.parse_color(bg_color)
                gradient = None

            # Get uploaded files
            files = request.files.getlist('images')
            if not files or all(f.filename == '' for f in files):
                return error_response('No images uploaded', 400)

            named_files = [f for f in files if f.filename]
            if len(named_files) > MAX_IMAGES:
                return error_response(
                    f'Too many images: {len(named_files)} (max {MAX_IMAGES})', 400
                )

            # Reject a grid that would allocate an unreasonable canvas before
            # any decoding work happens.
            grid_dim = self._grid_dimension(len(named_files))
            output_pixels = (grid_dim * size + (grid_dim - 1) * gap) ** 2
            if output_pixels > MAX_OUTPUT_PIXELS:
                return error_response(
                    f'Requested grid is too large ({output_pixels:,} pixels, '
                    f'max {MAX_OUTPUT_PIXELS:,}). Reduce size or image count.',
                    400
                )

            # Process images
            resized_images = []
            for file in named_files:
                try:
                    img = Image.open(file.stream)
                except UnidentifiedImageError:
                    raise ValueError(f"{file.filename} is not a readable image")

                # Image.open only reads the header, so the dimensions can be
                # vetted before committing memory to a full decode.
                if img.size[0] * img.size[1] > MAX_INPUT_PIXELS:
                    raise ValueError(
                        f"{file.filename} is too large "
                        f"({img.size[0]}x{img.size[1]}, max {MAX_INPUT_PIXELS:,} pixels)"
                    )

                if img.mode != 'RGB':
                    img = img.convert('RGB')
                resized = img.resize((size, size), Image.Resampling.LANCZOS)
                resized_images.append(resized)

            if not resized_images:
                return error_response('No valid images processed', 400)

            # Create grid
            grid = self.create_grid(resized_images, gap, background_color, gradient)

            # Save to bytes buffer
            img_io = io.BytesIO()
            grid.save(img_io, 'PNG')
            img_io.seek(0)

            return send_file(img_io, mimetype='image/png', as_attachment=False)

        except HTTPException:
            # Reading request.form/files parses the body, which raises 413 when
            # it exceeds MAX_CONTENT_LENGTH. Let Flask report those as-is.
            raise
        except ValueError as e:
            # Bad geometry, unparseable colours and undecodable uploads are all
            # caller errors rather than server faults.
            logger.warning("Rejected image grid request: {}", e)
            return error_response(str(e), 400)
        except Exception as e:
            logger.exception("Error generating image grid: {}", e)
            return error_response(str(e), 500)


# Create and export the blueprint
imagegrid_bp, url_prefix = ImageGridAPI.create()


def create_blueprint():
    """Entry point used by app.routes.init_app to register this module."""
    return imagegrid_bp, url_prefix