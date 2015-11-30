import logging
import unittest


from btce import config


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    loader = unittest.TestLoader()
    tests = loader.discover(config.TEST_DIR, "*test.py")
    unittest.TextTestRunner(verbosity=2).run(tests)

