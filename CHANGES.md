# Project Cleanup Changes

## Date
September 14, 2026

## Overview
Cleaned up the breadhub-api project by removing security-sensitive files, eliminating code duplication, and improving consistency across the codebase.

## Security Cleanup

### Removed Files
- **`.git-credentials.template`** - Git credential template file (security risk)
- **`.gitconfig`** - Personal git configuration (should not be in repository)

## Code Cleanup

### `main.py`
- **Removed duplicate index route** (lines 60-62) - The `/` route was already handled by `routes/pages/__init__.py`
- **Consolidated IP extraction logic** - Created helper functions `get_real_ip()` and `should_skip_logging()` to eliminate duplicate code in request/response logging

### `config.py`
- **Removed unused file upload settings**:
  - `UPLOAD_FOLDER`
  - `ALLOWED_EXTENSIONS`
  - `MAX_CONTENT_LENGTH`
- These settings were not used anywhere in the codebase

### `routes/__init__.py`
- **Removed unused imports**: `TypeVar`, `Any` from typing module
- **Removed dead legacy compatibility code** (lines 76-81) - Old-style module support that is no longer needed
- Simplified `create()` method signature to use string literal for type hint

### `wsgi.py`
- **Removed empty hook functions**:
  - `when_ready()`
  - `on_starting()`
  - `worker_int()`
- These functions served no purpose and were empty

### `static/css/base.css`
- **Removed duplicate theme overrides** (lines 249-267) - Theme variables were already defined earlier in the file
- **Fixed broken CSS** - Added missing closing brace for `#barcodePreviewContainer:not(.has-barcode)` selector

### `middleware/error_handler.py`
- **Replaced standard logging with loguru** for consistency with the rest of the application
- Changed from `from logging import getLogger` to `from logging_config import logger`

### `docker-compose.yml`
- **Replaced `build` directive with `image` directive** - Now uses standard `python:3.9-slim` image instead of building from Dockerfile
- **Added `PYTHONPATH=/app` environment variable** to enable proper package imports
- **Modified command** to install dependencies on-the-fly using `pip install -r requirements.txt` before starting Gunicorn
- This eliminates the need for the Dockerfile and allows the application to run with just docker-compose

### `Dockerfile`
- **Removed** - No longer needed since docker-compose.yml uses a pre-built Python image

## Project Restructuring

### New Directory Structure
Reorganized the project into a proper Python package structure:

**Before:**
```
breadhub-api/
├── config.py
├── logging_config.py
├── main.py
├── middleware/
├── routes/
├── static/
├── templates/
├── fonts/
├── wsgi.py
└── ...
```

**After:**
```
breadhub-api/
├── app/                    # Main application package
│   ├── __init__.py
│   ├── config.py
│   ├── logging_config.py
│   ├── main.py
│   ├── middleware/
│   ├── routes/
│   ├── static/
│   ├── templates/
│   └── fonts/
├── tests/
├── wsgi.py                # Entry point stays at root
├── requirements.txt
├── docker-compose.yml
└── ...
```

### Changes Made
- **Created `app/` package directory** with `__init__.py`
- **Moved Python files** (`config.py`, `logging_config.py`, `main.py`) to `app/`
- **Moved subdirectories** (`middleware/`, `routes/`, `static/`, `templates/`, `fonts/`) to `app/`
- **Updated all imports** to use `app.` prefix (e.g., `from app.config import Config`)
- **Updated `wsgi.py`** to import from `app.main`
- **Updated `docker-compose.yml`** to set `PYTHONPATH=/app` for proper package imports
- **Updated tests** to import from `app.routes.barcode`

## Image Grid Generator Integration

### Overview
Integrated the Image Grid Generator from the `braddevans/imagegridgen` GitHub repository as a new route in the application.

### Changes Made
- **Created `app/routes/imagegrid.py`** - New route module with image grid generation logic adapted from the original project
  - Includes `ImageGridAPI` class extending `BaseRoute`
  - Implements color parsing, gradient background creation, and grid generation
  - Provides `/api/imagegrid/generate` POST endpoint for generating grids from uploaded images
- **Created `app/templates/imagegrid.html`** - UI template adapted from the original project
  - Converted from Tailwind CSS to Bootstrap to match existing project styling
  - Includes drag-and-drop file upload, settings for image size, gap, and background colors
  - Supports solid colors and gradient backgrounds (horizontal, vertical, diagonal)
  - Cookie-based settings persistence
- **Updated `app/routes/pages/__init__.py`** - Added `/imagegrid` route to serve the image grid generator page
- **Updated `app/templates/base.html`** - Added "Image Grid" link to navigation bar
- **No new dependencies required** - Uses existing `Pillow` library already in requirements.txt

### Features
- Upload multiple images via drag-and-drop or file browser
- Configure image size (64-2048px) and gap (0-100px)
- Choose solid background color or gradient (horizontal/vertical/diagonal)
- Automatic grid layout calculation for square output
- Download generated grid as PNG
- Settings persistence via cookies
- Responsive Bootstrap UI matching existing design

## Benefits
- **Improved security**: Removed sensitive credential files
- **Reduced code duplication**: Consolidated repeated logic into helper functions
- **Better maintainability**: Removed dead code and unused imports
- **Consistent logging**: Standardized on loguru throughout the application
- **Fixed CSS bugs**: Corrected syntax errors in stylesheet
