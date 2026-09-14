# BreadHub API

[![Python](https://img.shields.io/badge/Python-3.9-blue.svg)](https://www.python.org/downloads/release/python-390/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)

A Flask-based REST API for generating barcodes and image grids with a modern web interface.

## Features

### Barcode Generator
- Code 128 barcode generation
- Multiple output formats (PNG, JPEG, GIF, BMP, TIFF)
- Customizable barcode dimensions and styling
- Font selection support
- Uppercase text conversion option
- Raw image or JSON response formats

### Image Grid Generator
- Upload multiple images via drag-and-drop
- Automatic grid layout calculation
- Configurable image size (64-2048px) and gap (0-100px)
- Solid color or gradient backgrounds (horizontal, vertical, diagonal)
- Download generated grids as PNG
- Settings persistence via cookies

### General
- Clean, maintainable codebase with proper package structure
- Bootstrap-based responsive UI
- Dark/light theme support
- Structured logging with loguru
- Docker Compose support for easy deployment

## Installation

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/braddevans/breadhub-api.git
   cd breadhub-api
   ```

2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the development server:
   ```bash
   python app/main.py
   ```

5. Access the application at `http://localhost:5000`

### Docker Deployment

1. Ensure Docker and Docker Compose are installed

2. Run with Docker Compose:
   ```bash
   docker-compose up
   ```

3. Access the application at `http://localhost:6400`

## API Endpoints

### Barcode API

#### Generate Barcode
```
GET /api/barcode?data=<data>&type=<type>&raw=<true/false>
```

**Parameters:**
- `data` (required): Data to encode
- `type`: Barcode format (default: code128)
  - Supported: code128
- `raw`: Return raw PNG if true, JSON if false (default)
- `uppercase`: Convert text to uppercase if true
- `font_family`: Font family to use
- `module_width`: Width of barcode modules
- `module_height`: Height of barcode modules
- `font_size`: Size of text under barcode
- `text_distance`: Space between barcode and text
- `background`: Background color (name or hex)
- `foreground`: Barcode color (name or hex)

**Example:**
```bash
curl "http://localhost:5000/api/barcode?data=CODE128&module_width=0.2&font_size=10"
```

#### List Writer Options
```
GET /api/barcode/writer-options
```

### Image Grid API

#### Generate Grid
```
POST /api/imagegrid/generate
```

**Form Parameters:**
- `images`: Multiple image files (multipart/form-data)
- `size`: Image size in pixels (64-2048, default: 512)
- `gap`: Gap between images in pixels (0-100, default: 10)
- `bg_color`: Background color (hex or RGB, default: #ffffff)
- `use_gradient`: Use gradient background (true/false)
- `gradient_start`: Gradient start color (default: #ffffff)
- `gradient_end`: Gradient end color (default: #000000)
- `gradient_direction`: Gradient direction (horizontal/vertical/diagonal)

**Example:**
```bash
curl -X POST http://localhost:5000/api/imagegrid/generate \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg" \
  -F "size=512" \
  -F "gap=10"
```

## Project Structure

```
breadhub-api/
├── app/                      # Main application package
│   ├── __init__.py
│   ├── config.py            # App configuration
│   ├── logging_config.py    # Logging setup
│   ├── main.py              # App factory
│   ├── middleware/          # Error handling middleware
│   ├── routes/              # API routes
│   │   ├── __init__.py
│   │   ├── barcode.py       # Barcode API
│   │   ├── imagegrid.py     # Image Grid API
│   │   └── pages/           # Page routes
│   ├── static/              # Static assets (CSS, JS)
│   ├── templates/           # HTML templates
│   └── fonts/               # Custom fonts
├── tests/                   # Test suite
├── wsgi.py                  # WSGI entry point
├── docker-compose.yml       # Docker configuration
├── requirements.txt         # Python dependencies
└── CHANGES.md               # Change log
```

## Configuration

Environment variables:
- `FLASK_ENV`: Flask environment (development/production)
- `LOG_LEVEL`: Logging level (DEBUG/INFO/WARNING/ERROR)
- `PYTHONPATH`: Python module path (set to /app in Docker)

## Testing

Run tests with pytest:
```bash
pytest tests/
```

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## AI Assistance

This project's documentation & commit messages used some assistance from AI tools for better organization and clarity.
