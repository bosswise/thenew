# Figure listing collector

The collector searches the eBay Browse API for fixed-price listings matching
anime figure, scale figure, Nendoroid, and figma searches. It is a first
international marketplace source, not a crawler for the entire internet.
Additional retailers require their own permitted API or feed integration.

For each valid listing, the collector stores the listing title, seller, price,
ISO currency, product URL, and eBay-provided image URL. The workflow searches
the `EBAY_US` marketplace by default, so prices may be in USD or another
currency returned by eBay. Manufacturer and release-date values are not
provided by this search and remain unknown.

## Configure eBay API access

1. Register or sign in at the [eBay Developer Program](https://developer.ebay.com/).
2. Create an application and obtain its **Production** App ID (Client ID) and
   Cert ID (Client Secret). Review eBay's current Browse API and API license
   requirements before using the data.
3. In the GitHub repository, open **Settings → Secrets and variables →
   Actions → New repository secret**.
4. Add these repository secrets:
   - `EBAY_CLIENT_ID` — Production App ID (Client ID)
   - `EBAY_CLIENT_SECRET` — Production Cert ID (Client Secret)
5. In the Supabase SQL editor, run the migration in
   [`supabase/migrations/20261022000000_add_price_currency.sql`](./supabase/migrations/20261022000000_add_price_currency.sql).
   This adds an ISO currency column so USD and other returned currencies are
   not displayed as unlabelled amounts.

Never put the Client Secret in source code, CSV files, or chat. The collector
uses the OAuth client-credentials flow and does not require an eBay buyer
account login.

## Run and monitor

GitHub Actions runs the collector hourly and also allows manual runs from
**Actions → Salamander Figure Bot → Run workflow**. It searches the `EBAY_US`
marketplace; the workflow can be changed to another eBay marketplace ID when
needed.

The collector spaces search requests to avoid sending them in a burst. It
inserts new listings and updates the price and currency of listings with a
matching item URL. Check the Actions log for query result counts and import
totals. Missing credentials, API errors, and runs with no valid listings fail
visibly instead of reporting a successful collection.

The collector stores eBay's image URL and does not download image files.
Follow eBay's current API terms for displaying and retaining product data.
Search results are limited to eBay and are not a complete view of all
worldwide figure products.
