import io
import json
import unittest
from unittest.mock import patch

from figure_bot import (
    classify_figure_type,
    parse_yahoo_hit,
    run_collector,
    save_yahoo_product,
    search_yahoo_items,
)


def make_hit(price=15800, url="https://store.example.jp/item/123"):
    return {
        "name": "ねんどろいど Example",
        "url": url,
        "price": price,
        "image": {"medium": "https://images.example.jp/item.jpg"},
        "seller": {"name": "Example Shop"},
        "brand": {"name": "Example Maker"},
        "releaseDate": "2026-10-01",
    }


class FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.action = "select"
        self.payload = None
        self.filters = {}

    def select(self, _columns):
        self.action = "select"
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def execute(self):
        if self.table_name == "figure_shops":
            if self.action == "select":
                found = [
                    {"id": row["id"], "figure_id": row["figure_id"]}
                    for row in self.client.shop_rows
                    if row["shop_url"] == self.filters.get("shop_url")
                ]
                return type("Response", (), {"data": found})()
            if self.action == "update":
                for row in self.client.shop_rows:
                    if row["id"] == self.filters.get("id"):
                        row.update(self.payload)
                return type("Response", (), {"data": []})()

            row = dict(self.payload, id=f"offer-{len(self.client.shop_rows) + 1}")
            self.client.shop_rows.append(row)
            return type("Response", (), {"data": [row]})()

        if self.action == "select":
            found = [
                {"id": row["id"]}
                for row in self.client.figure_rows
                if row["title"] == self.filters.get("title")
                and row["manufacturer"] == self.filters.get("manufacturer")
            ]
            return type("Response", (), {"data": found})()

        row = dict(self.payload, id=f"figure-{len(self.client.figure_rows) + 1}")
        self.client.figure_rows.append(row)
        return type("Response", (), {"data": [row]})()


class FakeSupabase:
    def __init__(self):
        self.figure_rows = []
        self.shop_rows = []

    def table(self, table_name):
        return FakeQuery(self, table_name)


class YahooCollectorTests(unittest.TestCase):
    def test_parse_yahoo_hit_maps_listing_fields(self):
        product = parse_yahoo_hit(make_hit())

        self.assertEqual(product["title"], "ねんどろいど Example")
        self.assertEqual(product["shop_name"], "Example Shop")
        self.assertEqual(product["price"], 15800)
        self.assertEqual(product["manufacturer"], "Example Maker")
        self.assertEqual(product["image_url"], "https://images.example.jp/item.jpg")

    def test_rejects_missing_url_and_invalid_price(self):
        with self.assertRaisesRegex(ValueError, "invalid product URL"):
            parse_yahoo_hit(make_hit(url="javascript:alert(1)"))
        with self.assertRaisesRegex(ValueError, "invalid price"):
            parse_yahoo_hit(make_hit(price=0))
        hit_without_image = make_hit()
        hit_without_image["image"] = {}
        with self.assertRaisesRegex(ValueError, "no product image URL"):
            parse_yahoo_hit(hit_without_image)

    def test_classifies_supported_figure_types(self):
        self.assertEqual(classify_figure_type("ねんどろいど Example"), "넨도로이드/SD")
        self.assertEqual(classify_figure_type("figma Example"), "액션 피규어")
        self.assertEqual(classify_figure_type("1/7 Example"), "스케일/스테츄")

    def test_search_yahoo_items_uses_json_api(self):
        payload = {"hits": [make_hit()]}
        response = io.BytesIO(json.dumps(payload).encode("utf-8"))

        with patch("figure_bot.urlopen", return_value=response) as mocked_urlopen:
            hits = search_yahoo_items("フィギュア", "test-app-id")

        self.assertEqual(hits, payload["hits"])
        request = mocked_urlopen.call_args.args[0]
        self.assertIn("appid=test-app-id", request.full_url)
        self.assertIn("%E3%83%95%E3%82%A3%E3%82%AE%E3%83%A5%E3%82%A2", request.full_url)

    def test_inserts_new_figure_and_listing(self):
        client = FakeSupabase()

        product = parse_yahoo_hit(make_hit())
        self.assertEqual(save_yahoo_product(product, client), "inserted")
        self.assertEqual(len(client.figure_rows), 1)
        self.assertEqual(len(client.shop_rows), 1)
        self.assertEqual(client.shop_rows[0]["price"], 15800)

    def test_updates_existing_listing_price(self):
        client = FakeSupabase()
        save_yahoo_product(parse_yahoo_hit(make_hit(price=15800)), client)

        result = save_yahoo_product(parse_yahoo_hit(make_hit(price=16800)), client)

        self.assertEqual(result, "updated")
        self.assertEqual(len(client.figure_rows), 1)
        self.assertEqual(len(client.shop_rows), 1)
        self.assertEqual(client.shop_rows[0]["price"], 16800)

    def test_collector_deduplicates_same_url_returned_by_queries(self):
        client = FakeSupabase()
        hit = make_hit()

        with patch("figure_bot.search_yahoo_items", return_value=[hit]), patch(
            "figure_bot.time.sleep"
        ):
            summary = run_collector("test-app-id", client, ("query one", "query two"))

        self.assertEqual(summary, (1, 0, 0))
        self.assertEqual(len(client.shop_rows), 1)

    def test_collector_fails_when_all_queries_return_no_products(self):
        with patch("figure_bot.search_yahoo_items", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "no valid figure listings"):
                run_collector("test-app-id", FakeSupabase(), ("empty query",))

    def test_collector_requires_app_id(self):
        with self.assertRaisesRegex(ValueError, "YAHOO_APP_ID is required"):
            run_collector("", FakeSupabase(), ())


if __name__ == "__main__":
    unittest.main()
