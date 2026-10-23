import importlib
import pkgutil
from flask import Blueprint
from loguru import logger
from typing import Self


class BaseRoute:
    """Base class for all route modules that provides common blueprint setup."""

    def __init__(self, name: str, import_name: str | None = None, url_prefix: str = ''):
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
    def create(cls: type[Self], *args, **kwargs) -> tuple[Blueprint, str]:
        """
        Create a new route instance and return its blueprint and URL prefix.

        Returns:
            Tuple of (blueprint, url_prefix)
        """
        instance = cls(*args, **kwargs)
        return instance.bp, instance.url_prefix

def init_app(app):
    """
    Register every route module's blueprint under /api.

    Blueprints are built fresh for each app: Flask forbids adding routes or
    nested blueprints to a blueprint once it has been registered, so sharing
    module-level instances would break any second call to create_app.

    Args:
        app: The Flask application instance
    """
    api_bp = Blueprint('api', __name__)

    for module_info in pkgutil.iter_modules(__path__):
        if module_info.ispkg:
            continue

        module_name = f'{__name__}.{module_info.name}'
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, 'create_blueprint'):
                blueprint, url_prefix = module.create_blueprint()
                api_bp.register_blueprint(blueprint, url_prefix=url_prefix)
                logger.info("Registered blueprint: {} at /api{}", module_name, url_prefix)
        except Exception:
            logger.exception("Failed to register routes from {}", module_name)

    app.register_blueprint(api_bp, url_prefix='/api')

__all__ = ['init_app', 'BaseRoute']
