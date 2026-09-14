import io
from PIL import Image, ImageDraw
from flask import request, send_file, render_template

from app.logging_config import logger
from app.middleware import error_response

from . import BaseRoute

# Inclusive bounds for caller-supplied grid geometry. Without these, a single
# request can ask Pillow for a multi-gigapixel canvas.
SIZE_LIMITS = (16, 2048)
GAP_LIMITS = (0, 512)
MAX_IMAGES = 100
MAX_OUTPUT_PIXELS = 50_000_000


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

        # Check if hex code
        if color_str.startswith('#'):
            hex_code = color_str.lstrip('#')
            if len(hex_code) == 3:
                # Expand shorthand hex (e.g., #fff -> #ffffff)
                hex_code = ''.join([c * 2 for c in hex_code])
            if len(hex_code) != 6:
                raise ValueError(f"Invalid hex color: {color_str}")
            return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))

        # Parse as RGB tuple
        try:
            return tuple(map(int, color_str.split(',')))
        except ValueError:
            raise ValueError(f"Invalid color format: {color_str}. Use hex (#ffffff) or RGB (255,255,255)")

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
        """Create a gradient background image."""
        image = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(image)

        if direction == 'horizontal':
            for x in range(width):
                ratio = x / width
                color = ImageGridAPI._interpolate_color(start_color, end_color, ratio)
                draw.line([(x, 0), (x, height)], fill=color)
        elif direction == 'vertical':
            for y in range(height):
                ratio = y / height
                color = ImageGridAPI._interpolate_color(start_color, end_color, ratio)
                draw.line([(0, y), (width, y)], fill=color)
        elif direction == 'diagonal':
            for i in range(width + height):
                ratio = i / (width + height)
                color = ImageGridAPI._interpolate_color(start_color, end_color, ratio)
                for x in range(max(0, i - height), min(width, i)):
                    y = i - x
                    if 0 <= y < height:
                        draw.point((x, y), fill=color)

        return image

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
            gradient_direction = request.form.get('gradient_direction', 'horizontal')

            # Parse background color
            if use_gradient:
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
            for file in files:
                if file.filename:
                    img = Image.open(file.stream)
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