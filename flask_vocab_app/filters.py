import base64
from itertools import zip_longest

def b64encode(value):
    """Encode a string to base64."""
    if isinstance(value, str):
        return base64.b64encode(value.encode('utf-8')).decode('utf-8')
    return value

def zip_filter(*args):
    """Custom Jinja2 filter to zip iterables."""
    return list(zip_longest(*args, fillvalue=None))

def register_filters(app):
    """Register custom Jinja2 filters."""
    app.jinja_env.filters['b64encode'] = b64encode
    app.jinja_env.filters['zip'] = zip_filter