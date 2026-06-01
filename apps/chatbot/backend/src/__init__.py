"""Namespace compatibility package for legacy `src.*` imports."""

from pkgutil import extend_path


__path__ = extend_path(__path__, __name__)
