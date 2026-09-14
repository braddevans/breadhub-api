import importlib
import sys
from pathlib import Path
from flask import Blueprint
from loguru import logger
from typing import Optional, Type

# Create main API blueprint
api_bp = Blueprint('api', __name__)


class BaseRoute:
    """Base class for all route modules that provides common blueprint setup."""
    
    def __init__(self, name: str, import_name: Optional[str] = None, url_prefix: str = ''):
        """
        Initialize a new route with a blueprint.
        
        Args:
            name: Name of the blueprint (e.g., 'barcode')
            import_name: Import name (defaults to __name__ of the module)
            url_prefix: URL prefix for all routes in this blueprint
        """
        self.bp = Blueprint(name, import_name or name)
        self.url_prefix = url_prefix
        self._register_routes()
    
    def _register_routes(self) -> None:
        """Register routes with the blueprint. Override this in child classes."""
        raise NotImplementedError("Subclasses must implement _register_routes")
    
    @classmethod
    def create(cls: Type['BaseRoute'], *args, **kwargs) -> tuple[Blueprint, str]:
        """
        Create a new route instance and return its blueprint and URL prefix.
        
        Returns:
            Tuple of (blueprint, url_prefix)
        """
        instance = cls(*args, **kwargs)
        return instance.bp, instance.url_prefix

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
            module_name = f'app.routes.{module_file.stem}'
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
            
            # Register the blueprint if the module has one
            if hasattr(module, 'create_blueprint'):
                try:
                    blueprint, url_prefix = module.create_blueprint()
                    api_bp.register_blueprint(blueprint, url_prefix=url_prefix)
                    logger.info("Registered blueprint: {} at /api{}", module_name, url_prefix)
                except Exception as e:
                    logger.error("Failed to create blueprint for {}: {}", module_name, e)
                
        except Exception as e:
            logger.error("Error importing {}: {}", module_file.stem, e)
    
    # Register the API blueprint with the app
    app.register_blueprint(api_bp, url_prefix='/api')

# Export the init_app function to make it available when importing from the routes package
__all__ = ['init_app', 'api_bp']
