import base64
import json
import math
import os
import time
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from supabase import Client, create_client


SUPABASE_URL = "https://qgxvmqhotuzrwbqvvsfq.supabase.co"
SUPABASE_KEY = "sb_publishable_rmcVZlVyr2SOLaf8XeIncg_3Q2CI4n3"
EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_SCOPE = "https://api.ebay.com/oauth/api_scope"
SEARCH_TERMS = ("anime figure", "scale figure", "nendoroid figure", "figma figure")
REQUEST_INTERVAL_SECONDS = 1.1


def _http_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value.strip()


def get_ebay_access_token(client_id: str, client_secret: str) -> str:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    body = urlencode(
        {"grant_type": "client_credentials", "scope": EBAY_SCOPE}
    ).encode("ascii")
    request = Request(
        EBAY_TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        detail = error.read(300).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"eBay OAuth returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach eBay OAuth: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError("eBay OAuth returned invalid JSON") from error

    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("eBay OAuth response did not contain an access token")
    return token


def search_ebay_items(
    query: str,
    access_token: str,
    marketplace_id: str = "EBAY_US",
) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "limit": "50",
        "filter": "buyingOptions:{FIXED_PRICE}",
    }
    request = Request(
        f"{EBAY_SEARCH_URL}?{urlencode(params)}",
        headers={
            "Authorization": "Bearer " + access_token,
            "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        detail = error.read(300).decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"eBay Browse API returned HTTP {error.code} for query {query!r}: {detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"Could not reach eBay Browse API for query {query!r}: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"eBay Browse API returned invalid JSON for query {query!r}") from error

    if isinstance(payload, dict) and payload.get("errors"):
        raise RuntimeError(f"eBay Browse API error for query {query!r}: {payload['errors']}")
    if not isinstance(payload, dict) or not isinstance(payload.get("itemSummaries", []), list):
        raise RuntimeError(f"eBay Browse API response did not contain item summaries for {query!r}")
    return payload.get("itemSummaries", [])


def parse_ebay_item(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("eBay result is not a JSON object")
    title = item.get("title")
    url = _http_url(item.get("itemWebUrl"))
    price_info = item.get("price")
    if not isinstance(price_info, dict):
        price_info = {}
    raw_price = price_info.get("value")
    currency = price_info.get("currency")
    try:
        price = Decimal(str(raw_price))
    except (InvalidOperation, ValueError):
        price = Decimal("NaN")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("eBay result has no item title")
    if not url:
        raise ValueError(f"eBay result has an invalid item URL: {title}")
    if not price.is_finite() or price <= 0 or not math.isfinite(float(price)):
        raise ValueError(f"eBay result has an invalid price: {title}")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise ValueError(f"eBay result has an invalid currency: {title}")

    image_info = item.get("image")
    if not isinstance(image_info, dict):
        image_info = {}
    image_url = _http_url(image_info.get("imageUrl"))
    if not image_url:
        raise ValueError(f"eBay result has no product image URL: {title}")

    seller_info = item.get("seller")
    if not isinstance(seller_info, dict):
        seller_info = {}
    seller = seller_info.get("username")

    return {
        "title": title.strip(),
        "shop_name": seller if isinstance(seller, str) and seller else "eBay seller",
        "price": float(price),
        "currency": currency.upper(),
        "shop_url": url,
        "image_url": image_url,
    }


def classify_figure_type(title: str) -> str:
    lowered = title.casefold()
    if "nendoroid" in lowered:
        return "넨도로이드/SD"
    if "noodle stopper" in lowered:
        return "누들 스토퍼"
    if "figma" in lowered or "action figure" in lowered:
        return "액션 피규어"
    if any(word in lowered for word in ("scale figure", "statue")) or any(
        scale in lowered for scale in ("1/4", "1/6", "1/7", "1/8")
    ):
        return "스케일/스테츄"
    return "기타"


def save_ebay_product(product: dict[str, Any], client: Client) -> str:
    existing_offer = (
        client.table("figure_shops")
        .select("id")
        .eq("shop_url", product["shop_url"])
        .execute()
    )
    if existing_offer.data:
        client.table("figure_shops").update(
            {
                "price": product["price"],
                "currency": product["currency"],
                "shop_name": product["shop_name"],
            }
        ).eq("id", existing_offer.data[0]["id"]).execute()
        return "updated"

    existing_figure = (
        client.table("figures")
        .select("id")
        .eq("title", product["title"])
        .eq("manufacturer", "미정")
        .execute()
    )
    if existing_figure.data:
        figure_id = existing_figure.data[0]["id"]
    else:
        figure_result = (
            client.table("figures")
            .insert(
                {
                    "title": product["title"],
                    "manufacturer": "미정",
                    "scale": "정보없음",
                    "release_date": "정보없음",
                    "image_url1": product["image_url"],
                    "image_url2": "",
                    "image_url3": "",
                    "image_url": product["image_url"],
                    "description": "eBay listing",
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
            "currency": product["currency"],
            "shop_url": product["shop_url"],
        }
    ).execute()
    return "inserted"


def run_collector(
    client_id: str,
    client_secret: str,
    client: Client,
    marketplace_id: str = "EBAY_US",
    search_terms: tuple[str, ...] = SEARCH_TERMS,
    request_interval: float = REQUEST_INTERVAL_SECONDS,
) -> tuple[int, int, int]:
    if not client_id.strip() or not client_secret.strip():
        raise ValueError("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required.")
    if not marketplace_id.strip():
        raise ValueError("EBAY_MARKETPLACE_ID must not be blank.")

    access_token = get_ebay_access_token(client_id, client_secret)
    seen_urls: set[str] = set()
    inserted = 0
    updated = 0
    invalid = 0
    valid_results = 0

    for index, query in enumerate(search_terms):
        if index:
            time.sleep(request_interval)
        items = search_ebay_items(query, access_token, marketplace_id)
        print(f"eBay {marketplace_id} query {query!r}: {len(items)} results")
        for item in items:
            try:
                product = parse_ebay_item(item)
            except ValueError as error:
                invalid += 1
                print(f"Skipping invalid eBay result: {error}")
                continue

            if product["shop_url"] in seen_urls:
                continue
            seen_urls.add(product["shop_url"])
            valid_results += 1
            result = save_ebay_product(product, client)
            if result == "inserted":
                inserted += 1
            else:
                updated += 1

    print(
        f"eBay sync finished: {inserted} new listings, "
        f"{updated} prices updated, {invalid} invalid results skipped."
    )
    if valid_results == 0:
        raise RuntimeError("eBay returned no valid figure listings for the configured searches.")
    return inserted, updated, invalid


def main() -> None:
    client_id = os.environ.get("EBAY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("EBAY_CLIENT_SECRET", "").strip()
    marketplace_id = os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_US").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "eBay credentials are missing. Add EBAY_CLIENT_ID and EBAY_CLIENT_SECRET "
            "to GitHub Actions repository secrets."
        )

    client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    run_collector(client_id, client_secret, client, marketplace_id)


if __name__ == "__main__":
    main()
