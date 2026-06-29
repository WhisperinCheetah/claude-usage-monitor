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

    def test_spark_cost(self):
        self.assertEqual(fmt.fmt_spark_cost(0), "")
        self.assertEqual(fmt.fmt_spark_cost(-1), "")
        self.assertEqual(fmt.fmt_spark_cost(0.423), "$0.42")
        self.assertEqual(fmt.fmt_spark_cost(3.42), "$3.4")
        self.assertEqual(fmt.fmt_spark_cost(42.6), "$43")
        self.assertEqual(fmt.fmt_spark_cost(123.4), "$123")


if __name__ == "__main__":
    unittest.main()
