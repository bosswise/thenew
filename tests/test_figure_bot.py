import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from figure_bot import import_csv, parse_price


class FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.action = None
        self.payload = None
        self.shop_url = None

    def select(self, _columns):
        self.action = "select"
        return self

    def eq(self, _column, value):
        self.shop_url = value
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def execute(self):
        if self.action == "select":
            data = [{"id": "existing"}] if self.shop_url in self.client.shop_urls else []
            return SimpleNamespace(data=data)
        if self.table_name == "figures":
            self.client.figure_rows.append(self.payload)
            return SimpleNamespace(data=[{"id": "figure-id"}])
        self.client.shop_rows.append(self.payload)
        self.client.shop_urls.add(self.payload["shop_url"])
        return SimpleNamespace(data=[self.payload])


class FakeSupabase:
    def __init__(self):
        self.figure_rows = []
        self.shop_rows = []
        self.shop_urls = set()

    def table(self, table_name):
        return FakeQuery(self, table_name)


class FigureBotTests(unittest.TestCase):
    def write_csv(self, content):
        temporary = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", suffix=".csv", delete=False
        )
        with temporary:
            temporary.write(content)
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_imports_csv_and_skips_duplicate_shop_url(self):
        path = self.write_csv(
            "title,shop_name,price,shop_url\n"
            "Example figure,Example Shop,\"15,800\",https://example.com/item\n"
        )
        client = FakeSupabase()

        self.assertEqual(import_csv(path, client), (1, 0))
        self.assertEqual(import_csv(path, client), (0, 1))
        self.assertEqual(len(client.figure_rows), 1)
        self.assertEqual(client.shop_rows[0]["price"], 15800)
        self.assertEqual(client.figure_rows[0]["image_url"], "https://via.placeholder.com/300")

    def test_rejects_invalid_price_before_database_insert(self):
        path = self.write_csv(
            "title,shop_name,price,shop_url\n"
            "Example figure,Example Shop,unknown,https://example.com/item\n"
        )
        client = FakeSupabase()

        with self.assertRaisesRegex(ValueError, "CSV row 2"):
            import_csv(path, client)

        self.assertEqual(client.figure_rows, [])

    def test_rejects_csv_missing_required_columns(self):
        path = self.write_csv("title,price\nExample figure,15800\n")

        with self.assertRaisesRegex(ValueError, "missing required columns"):
            import_csv(path, FakeSupabase())

    def test_rejects_empty_csv(self):
        path = self.write_csv("title,shop_name,price,shop_url\n")

        with self.assertRaisesRegex(ValueError, "contains no product rows"):
            import_csv(path, FakeSupabase())

    def test_parse_price_accepts_commas(self):
        self.assertEqual(parse_price("15,800"), 15800)


if __name__ == "__main__":
    unittest.main()
