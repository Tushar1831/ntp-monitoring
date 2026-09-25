"""Expose known failures as ordinary failures for diagnosis and release gates."""
import sys
import unittest
from pathlib import Path


def remove_expected_failures(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            remove_expected_failures(test)
        else:
            method = getattr(type(test), test._testMethodName)
            if getattr(method, '__unittest_expecting_failure__', False):
                method.__unittest_expecting_failure__ = False


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent))
    remove_expected_failures(suite)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
