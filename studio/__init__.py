"""TQEC Studio. Importing the package does not start the server or compiler."""


def create_studio_app(data_dir=None):
    from .app import create_studio_app as factory

    return factory(data_dir)
