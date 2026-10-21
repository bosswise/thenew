# Figure CSV importer

The scheduled web scraper has been replaced with an explicit CSV import. The
current AmiAmi and Good Smile pages did not provide product links to the
collector, and this repository has no verified official product feed/API.
This importer does not try to bypass those sites' access restrictions.

## Prepare `figures.csv`

Add a UTF-8 CSV file named `figures.csv` to the repository root. Only
`title`, `shop_name`, `price`, and `shop_url` are required. The remaining
columns may be left blank or omitted.

```csv
title,manufacturer,scale,release_date,image_url1,image_url2,image_url3,description,category,figure_type,shop_name,price,shop_url
Example figure,Example Maker,1/7 scale,2026-10,https://example.com/figure.jpg,,,Example description,애니메이션,스케일/스테츄,Example Shop,15800,https://example.com/products/example
```

Use a whole-number price (commas are accepted when quoted, for example
`"15,800"`). Rows with a `shop_url` already in `figure_shops` are skipped, so
rerunning an unchanged CSV will not import the same shop listing twice.

## Run the import

Commit `figures.csv`, then open the repository's **Actions** tab, select
**Salamander Figure Bot**, and choose **Run workflow**. The workflow is manual
because no supported automatic product feed has been configured. Add updated
CSV rows and run it again when you have new listings.

Import errors are printed in the workflow log and make the run fail instead
of reporting a false success.
