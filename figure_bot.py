import json
import math
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from supabase import Client, create_client


SUPABASE_URL = "https://qgxvmqhotuzrwbqvvsfq.supabase.co"
SUPABASE_KEY = "sb_publishable_rmcVZlVyr2SOLaf8XeIncg_3Q2CI4n3"
YAHOO_API_URL = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
SEARCH_TERMS = ("フィギュア", "スケールフィギュア", "ねんどろいど", "figma")
REQUEST_INTERVAL_SECONDS = 1.1


def _http_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value.strip()


def parse_yahoo_hit(hit: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(hit, dict):
        raise ValueError("Yahoo result is not a JSON object")
    title = hit.get("name")
    url = _http_url(hit.get("url"))
    price = hit.get("price")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Yahoo result has no product name")
    if not url:
        raise ValueError(f"Yahoo result has an invalid product URL: {title}")
    if (
        isinstance(price, bool)
        or not isinstance(price, (int, float))
        or not math.isfinite(price)
        or price <= 0
    ):
        raise ValueError(f"Yahoo result has an invalid price: {title}")

    image_data = hit.get("image")
    if not isinstance(image_data, dict):
        image_data = {}
    image_url = _http_url(image_data.get("medium")) or _http_url(image_data.get("small"))
    seller = hit.get("seller")
    if not isinstance(seller, dict):
        seller = {}
    brand = hit.get("brand")
    if not isinstance(brand, dict):
        brand = {}
    release_date = hit.get("releaseDate")
    if not image_url:
        raise ValueError(f"Yahoo result has no product image URL: {title}")
    seller_name = seller.get("name")
    brand_name = brand.get("name")

    return {
        "title": title.strip(),
        "shop_name": seller_name if isinstance(seller_name, str) and seller_name else "Yahoo!ショッピング",
        "price": int(price),
        "shop_url": url,
        "image_url": image_url,
        "manufacturer": brand_name if isinstance(brand_name, str) and brand_name else "미정",
        "release_date": release_date if isinstance(release_date, str) and release_date else "정보없음",
    }


def search_yahoo_items(query: str, app_id: str) -> list[dict[str, Any]]:
    request_url = f"{YAHOO_API_URL}?{urlencode({'appid': app_id, 'query': query})}"
    request = Request(
        request_url,
        headers={"Accept": "application/json", "User-Agent": "ThenewFigureCatalog/1.0"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        detail = error.read(300).decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Yahoo Shopping API returned HTTP {error.code} for query {query!r}: {detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"Could not reach Yahoo Shopping API for query {query!r}: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Yahoo Shopping API returned invalid JSON for query {query!r}") from error

    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"Yahoo Shopping API error for query {query!r}: {payload['error']}")
    if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
        raise RuntimeError(f"Yahoo Shopping API response did not contain a hits list for {query!r}")
    return payload["hits"]


def classify_figure_type(title: str) -> str:
    lowered = title.casefold()
    if "ねんどろいど" in title or "nendoroid" in lowered:
        return "넨도로이드/SD"
    if "ぬーどるストッパー" in title or "noodle stopper" in lowered:
        return "누들 스토퍼"
    if any(word in lowered for word in ("figma", "action figure")) or "可動フィギュア" in title:
        return "액션 피규어"
    if any(word in lowered for word in ("scale figure", "statue")) or any(
        scale in title for scale in ("1/4", "1/6", "1/7", "1/8")
    ):
        return "스케일/스테츄"
    if "スケールフィギュア" in title:
        return "스케일/스테츄"
    return "기타"


def save_yahoo_product(product: dict[str, Any], client: Client) -> str:
    existing_offer = (
        client.table("figure_shops")
        .select("id")
        .eq("shop_url", product["shop_url"])
        .execute()
    )
    if existing_offer.data:
        client.table("figure_shops").update(
            {"price": product["price"], "shop_name": product["shop_name"]}
        ).eq("id", existing_offer.data[0]["id"]).execute()
        return "updated"

    existing_figure = (
        client.table("figures")
        .select("id")
        .eq("title", product["title"])
        .eq("manufacturer", product["manufacturer"])
        .execute()
    )
    if existing_figure.data:
        figure_id = existing_figure.data[0]["id"]
    else:
        image_url = product["image_url"]
        figure_result = (
            client.table("figures")
            .insert(
                {
                    "title": product["title"],
                    "manufacturer": product["manufacturer"],
                    "scale": "정보없음",
                    "release_date": product["release_date"],
                    "image_url1": image_url,
                    "image_url2": "",
                    "image_url3": "",
                    "image_url": image_url,
                    "description": "Yahoo!ショッピング商品",
                    "category": "기타",
                    "figure_type": classify_figure_type(product["title"]),
                }
            )
            .execute()
        )
        if not figure_result.data or "id" not in figure_result.data[0]:
            raise RuntimeError(f"Supabase did not return an ID for {product['title']!r}")
        figure_id = figure_result.data[0]["id"]

    client.table("figure_shops").insert(
        {
            "figure_id": figure_id,
            "shop_name": product["shop_name"],
            "price": product["price"],
            "shop_url": product["shop_url"],
        }
    ).execute()
    return "inserted"


def run_collector(
    app_id: str,
    client: Client,
    search_terms: tuple[str, ...] = SEARCH_TERMS,
    request_interval: float = REQUEST_INTERVAL_SECONDS,
) -> tuple[int, int, int]:
    if not app_id.strip():
        raise ValueError("YAHOO_APP_ID is required. Add your Yahoo Developer application ID as a secret.")

    seen_urls: set[str] = set()
    inserted = 0
    updated = 0
    invalid = 0
    valid_results = 0

    for index, query in enumerate(search_terms):
        if index:
            time.sleep(request_interval)
        hits = search_yahoo_items(query, app_id)
        print(f"Yahoo! Shopping query {query!r}: {len(hits)} results")
        for hit in hits:
            try:
                product = parse_yahoo_hit(hit)
            except ValueError as error:
                invalid += 1
                print(f"Skipping invalid Yahoo result: {error}")
                continue

            if product["shop_url"] in seen_urls:
                continue
            seen_urls.add(product["shop_url"])
            valid_results += 1
            result = save_yahoo_product(product, client)
            if result == "inserted":
                inserted += 1
            else:
                updated += 1

    print(
        f"Yahoo! Shopping sync finished: {inserted} new listings, "
        f"{updated} prices updated, {invalid} invalid results skipped."
    )
    if valid_results == 0:
        raise RuntimeError("Yahoo Shopping returned no valid figure listings for the configured searches.")
    return inserted, updated, invalid


def main() -> None:
    app_id = os.environ.get("YAHOO_APP_ID", "").strip()
    if not app_id:
        raise RuntimeError(
            "YAHOO_APP_ID is missing. Create a Yahoo! Developer application and "
            "add its application ID to GitHub Actions secrets."
        )

    client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    run_collector(app_id, client)


if __name__ == "__main__":
    main()
