"""Test-only authenticated UI harness.

Production Auth.gate.require_login is never bypassed. This decorator patches
only the duration of an individual unittest test method that renders app.py.
Auth gate/security-specific tests intentionally do not use this helper.
"""
import functools
from unittest.mock import patch


def isolated_authenticated_ui_tests(cls):
    for name, method in list(vars(cls).items()):
        if not name.startswith('test_') or not callable(method):
            continue
        @functools.wraps(method)
        def wrapper(self, *args, __method=method, **kwargs):
            with patch('Auth.gate.require_login', return_value=None):
                return __method(self, *args, **kwargs)
        setattr(cls, name, wrapper)
    return cls
