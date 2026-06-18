import unittest
from usage_monitor import format as fmt


class TestFormat(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(fmt.fmt_tokens(950), "950")
        self.assertEqual(fmt.fmt_tokens(12_400), "12.4K")
        self.assertEqual(fmt.fmt_tokens(2_500_000), "2.5M")
        self.assertEqual(fmt.fmt_tokens(1_200_000_000), "1.2B")

    def test_cost(self):
        self.assertEqual(fmt.fmt_cost(58.912), "$58.91")
        self.assertEqual(fmt.fmt_cost(0), "$0.00")


if __name__ == "__main__":
    unittest.main()
