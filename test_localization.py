import unittest
from core.JinjaEnvironmentManager import Localization
import os

my_path = os.path.join(os.path.dirname(__file__), "test_loc", "en")

class MyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pass

    def test_something(self):
        loc = Localization(my_path)
        loc["test"]


if __name__ == '__main__':
    unittest.main()
