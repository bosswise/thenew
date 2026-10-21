# Figure listing collector

The collector searches the official Yahoo! Shopping item-search API for figure
listings. The current searches cover Japanese terms for figures, scale figures,
Nendoroid, and figma. This is a first source, not a crawler for the entire
internet; additional retailers need their own permitted API or feed adapter.

The collector stores listing titles, seller names, prices, product URLs, image
URLs, and optional brand/release-date values returned by the API. Prices are
stored as returned by Yahoo! Shopping (JPY). Release dates and manufacturer
names may be missing or reflect marketplace metadata rather than verified
manufacturer data.

## Configure Yahoo! Shopping API access

1. Sign in to a Yahoo! JAPAN account and register an application in the
   [Yahoo! Developer Network](https://e.developer.yahoo.co.jp/shopping/register).
2. Review and accept the current
   [Yahoo! Shopping API documentation and usage terms](https://developer.yahoo.co.jp/webapi/shopping/v3/itemsearch.html).
3. In the GitHub repository, open **Settings → Secrets and variables →
   Actions → New repository secret**.
4. Add the application ID as a secret named `YAHOO_APP_ID`. Do not paste it
   into chat or commit it to the repository.

Without this secret, the scheduled job fails with a clear configuration error.

## Run and monitor

GitHub Actions runs the collector hourly and also allows a manual run from the
**Actions → Salamander Figure Bot → Run workflow** page. The collector spaces
API requests to stay below Yahoo's documented limit of one query per second.
For each matching listing it adds a figure/shop record, or updates the stored
price when that exact listing URL was already imported.

Check the Actions log for query result counts and import totals. API failures
and runs that return no valid listings fail visibly instead of reporting a
successful collection.

The API response contains image URLs; this collector stores those URLs rather
than downloading or copying image files. Follow Yahoo's current API terms when
displaying or retaining product data. This source covers Yahoo! Shopping
listings only; it does not provide comprehensive worldwide inventory.
