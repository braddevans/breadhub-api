import io
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from app.config import Config
from app.main import create_app


class TestConfig(Config):
    TESTING = True


@pytest.fixture
def app():
    return create_app(TestConfig)


def test_create_app_can_be_called_repeatedly():
    """Blueprints are built per app, so a second app gets the same routes."""
    rules = [
        sorted(rule.rule for rule in create_app(TestConfig).url_map.iter_rules())
        for _ in range(2)
    ]
    assert rules[0] == rules[1]
    assert '/api/barcode' in rules[0]
    assert '/api/imagegrid/generate' in rules[0]


@pytest.mark.parametrize('path', ['/', '/generator', '/imagegrid'])
def test_pages_render(app, path):
    assert app.test_client().get(path).status_code == 200


def _png_bytes(color):
    buffer = io.BytesIO()
    Image.new('RGB', (32, 32), color).save(buffer, 'PNG')
    return buffer.getvalue()


def test_concurrent_requests(app):
    """Requests served from many threads at once, as the gthread worker does."""

    def barcode(i):
        response = app.test_client().get(
            '/api/barcode', query_string={'data': f'ITEM{i}', 'raw': 'true'}
        )
        return response.status_code, response.data[:4]

    def grid(i):
        response = app.test_client().post(
            '/api/imagegrid/generate',
            data={
                'size': '64',
                'images': [(io.BytesIO(_png_bytes((i, 0, 0))), f'{i}.png')],
            },
            content_type='multipart/form-data',
        )
        return response.status_code, response.data[:4]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(barcode, range(32))) + list(pool.map(grid, range(16)))

    assert all(result == (200, b'\x89PNG') for result in results)
