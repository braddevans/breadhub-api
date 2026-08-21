# BreadHub Barcode API

Flask REST API for generating barcodes in multiple formats.

## Features

- Code 128 barcode generation
- Customizable output (PNG, JPEG)
- Font selection by ID
- Uppercase text conversion
- Clean, maintainable codebase

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd breadhub-api
   ```

2. Create virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the server:
   ```bash
   python main.py
   ```

2. API available at `http://localhost:5000`

## API Endpoints

### Generate Barcode

```
GET /barcode?data=<data>&format=<format>&raw=<true/false>
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
```
GET /barcode?data=CODE128&type=code128&module_width=0.2&font_size=10
```

### List Available Fonts

```
GET /barcode/fonts
```

## Project Structure

```
breadhub-api/
├── config.py           # App configuration
├── extensions.py       # Flask extensions
├── main.py            # App factory
├── requirements.txt    # Dependencies
├── fonts/             # Custom fonts
└── routes/
    └── barcode.py     # Barcode API endpoints
```

## License

MIT
