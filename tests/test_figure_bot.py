import base64
import io
import json
import unittest
from unittest.mock import patch

from figure_bot import (
    classify_figure_type,
    get_ebay_access_token,
    parse_ebay_item,
    run_collector,
    save_ebay_product,
    search_ebay_items,
)


def make_item(
    price="19.99",
    currency="USD",
    url="https://www.ebay.com/itm/123",
):
    return {
        "title": "Nendoroid Example",
        "itemWebUrl": url,
        "price": {"value": price, "currency": currency},
        "image": {"imageUrl": "https://i.ebayimg.com/images/g/example.jpg"},
        "seller": {"username": "example-seller"},
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


class EbayCollectorTests(unittest.TestCase):
    def test_gets_oauth_client_credentials_token(self):
        response = io.BytesIO(b'{"access_token":"test-token","expires_in":7200}')

        with patch("figure_bot.urlopen", return_value=response) as mocked_urlopen:
            token = get_ebay_access_token("client-id", "client-secret")

        self.assertEqual(token, "test-token")
        request = mocked_urlopen.call_args.args[0]
        expected_basic = base64.b64encode(b"client-id:client-secret").decode("ascii")
        self.assertEqual(request.get_header("Authorization"), f"Basic {expected_basic}")
        self.assertIn(b"grant_type=client_credentials", request.data)

    def test_search_sets_marketplace_and_fixed_price_filter(self):
        response = io.BytesIO(b'{"itemSummaries":[]}')

        with patch("figure_bot.urlopen", return_value=response) as mocked_urlopen:
            items = search_ebay_items("anime figure", "test-token", "EBAY_GB")

        self.assertEqual(items, [])
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(request.get_header("X-ebay-c-marketplace-id"), "EBAY_GB")
        self.assertIn("buyingOptions", request.full_url)

    def test_parse_item_maps_listing_and_currency_fields(self):
        product = parse_ebay_item(make_item())

        self.assertEqual(product["title"], "Nendoroid Example")
        self.assertEqual(product["shop_name"], "example-seller")
        self.assertEqual(product["price"], 19.99)
        self.assertEqual(product["currency"], "USD")
        self.assertEqual(product["image_url"], "https://i.ebayimg.com/images/g/example.jpg")

    def test_rejects_invalid_price_currency_url_and_image(self):
        with self.assertRaisesRegex(ValueError, "invalid price"):
            parse_ebay_item(make_item(price="NaN"))
        with self.assertRaisesRegex(ValueError, "invalid currency"):
            parse_ebay_item(make_item(currency="US"))
        with self.assertRaisesRegex(ValueError, "invalid item URL"):
            parse_ebay_item(make_item(url="javascript:alert(1)"))
        item_without_image = make_item()
        item_without_image["image"] = {}
        with self.assertRaisesRegex(ValueError, "no product image URL"):
            parse_ebay_item(item_without_image)

    def test_classifies_supported_figure_types(self):
        self.assertEqual(classify_figure_type("Nendoroid Example"), "넨도로이드/SD")
        self.assertEqual(classify_figure_type("figma Example"), "액션 피규어")
        self.assertEqual(classify_figure_type("1/7 scale figure"), "스케일/스테츄")

    def test_inserts_new_figure_and_listing_with_currency(self):
        client = FakeSupabase()

        self.assertEqual(save_ebay_product(parse_ebay_item(make_item()), client), "inserted")
        self.assertEqual(len(client.figure_rows), 1)
        self.assertEqual(len(client.shop_rows), 1)
        self.assertEqual(client.shop_rows[0]["price"], 19.99)
        self.assertEqual(client.shop_rows[0]["currency"], "USD")

    def test_updates_existing_listing_price_and_currency(self):
        client = FakeSupabase()
        save_ebay_product(parse_ebay_item(make_item()), client)

        updated = make_item(price="21.50", currency="GBP")
        result = save_ebay_product(parse_ebay_item(updated), client)

        self.assertEqual(result, "updated")
        self.assertEqual(len(client.figure_rows), 1)
        self.assertEqual(len(client.shop_rows), 1)
        self.assertEqual(client.shop_rows[0]["price"], 21.5)
        self.assertEqual(client.shop_rows[0]["currency"], "GBP")

    def test_collector_deduplicates_same_url_across_searches(self):
        client = FakeSupabase()
        item = make_item()

        with patch("figure_bot.get_ebay_access_token", return_value="test-token"), patch(
            "figure_bot.search_ebay_items", return_value=[item]
        ), patch("figure_bot.time.sleep"):
            summary = run_collector(
                "client-id",
                "client-secret",
                client,
                search_terms=("query one", "query two"),
            )

        self.assertEqual(summary, (1, 0, 0))
        self.assertEqual(len(client.shop_rows), 1)

    def test_collector_fails_if_searches_return_no_valid_results(self):
        with patch("figure_bot.get_ebay_access_token", return_value="test-token"), patch(
            "figure_bot.search_ebay_items", return_value=[]
        ):
            with self.assertRaisesRegex(RuntimeError, "no valid figure listings"):
                run_collector("client-id", "client-secret", FakeSupabase(), search_terms=("empty",))

    def test_collector_requires_both_credentials(self):
        with self.assertRaisesRegex(ValueError, "EBAY_CLIENT_ID and EBAY_CLIENT_SECRET"):
            run_collector("", "", FakeSupabase(), search_terms=())


if __name__ == "__main__":
    unittest.main()
