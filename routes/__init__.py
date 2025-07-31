import importlib
import os
import sys
from pathlib import Path
from flask import Blueprint
from loguru import logger

# Create main API blueprint
api_bp = Blueprint('api', __name__)

def init_app(app):
    """
    Initialize all routes with the app.
    
    Args:
        app: The Flask application instance
    """
    # Get the directory of the current file
    routes_dir = Path(__file__).parent
    
    # Dynamically import all Python modules in the routes directory
    for module_file in routes_dir.glob('*.py'):
        # Skip __init__.py
        if module_file.stem == '__init__':
            continue
            
        try:
            # Import the module
            module_name = f'routes.{module_file.stem}'
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
            
            # Register the blueprint if the module has one
            if hasattr(module, 'barcode_bp') and hasattr(module, 'url_prefix'):
                # Use a simple flag to track if we've registered this blueprint
                if not hasattr(module, '_blueprint_registered'):
                    api_bp.register_blueprint(
                        module.barcode_bp,
                        url_prefix=module.url_prefix
                    )
                    module._blueprint_registered = True
                    logger.info("Registered blueprint: {} at /api{}", module_name, module.url_prefix)
                else:
                    logger.debug("Skipping duplicate registration of blueprint: {}", module_name)
                
        except Exception as e:
            logger.error("Error importing {}: {}", module_file.stem, e)
    
    # Register the API blueprint with the app
    app.register_blueprint(api_bp, url_prefix='/api')

# Export the init_app function to make it available when importing from the routes package
__all__ = ['init_app', 'api_bp']
