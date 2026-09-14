import io
from PIL import Image, ImageDraw
from flask import Blueprint, request, send_file, jsonify

from app.logging_config import logger
from app.middleware import error_response

from . import BaseRoute


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
    def create_gradient_background(width, height, start_color, end_color, direction='horizontal'):
        """Create a gradient background image."""
        image = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(image)

        if direction == 'horizontal':
            for x in range(width):
                ratio = x / width
                r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
                g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
                b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
                draw.line([(x, 0), (x, height)], fill=(r, g, b))
        elif direction == 'vertical':
            for y in range(height):
                ratio = y / height
                r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
                g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
                b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
                draw.line([(0, y), (width, y)], fill=(r, g, b))
        elif direction == 'diagonal':
            for i in range(width + height):
                ratio = i / (width + height)
                r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
                g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
                b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
                # Draw diagonal lines
                for x in range(max(0, i - height), min(width, i)):
                    y = i - x
                    if 0 <= y < height:
                        draw.point((x, y), fill=(r, g, b))

        return image

    @staticmethod
    def create_grid(images, gap=10, background_color=(255, 255, 255), gradient=None):
        """Create a square grid from resized images with specified gap and background."""
        if not images:
            raise ValueError("No images provided")

        img_size = images[0].size
        img_width, img_height = img_size

        # Calculate grid dimensions (ensure square output)
        num_images = len(images)
        grid_dim = int(num_images ** 0.5)
        if grid_dim * grid_dim < num_images:
            grid_dim += 1  # Round up to make room for all images

        cols = grid_dim
        rows = grid_dim

        # Calculate total grid dimensions (square)
        grid_width = cols * img_width + (cols - 1) * gap
        grid_height = rows * img_height + (rows - 1) * gap

        # Create background
        if gradient:
            start_color, end_color, direction = gradient
            grid = ImageGridAPI.create_gradient_background(grid_width, grid_height, start_color, end_color, direction)
        else:
            grid = Image.new('RGB', (grid_width, grid_height), background_color)

        # Paste images onto grid
        for idx, img in enumerate(images):
            row = idx // cols
            col = idx % cols

            x = col * (img_width + gap)
            y = row * (img_height + gap)

            grid.paste(img, (x, y))

        return grid

    def imagegrid_page(self):
        """Serve the image grid generator HTML page."""
        from flask import render_template
        return render_template('imagegrid.html')

    def generate_grid(self):
        """Generate an image grid from uploaded files."""
        try:
            # Get form data
            gap = int(request.form.get('gap', 10))
            size = int(request.form.get('size', 512))
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

        except Exception as e:
            logger.error(f"Error generating image grid: {str(e)}", exc_info=True)
            return error_response(str(e), 500)


# Create and export the blueprint
imagegrid_bp, url_prefix = ImageGridAPI.create()
