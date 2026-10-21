import csv
import os
import re
from pathlib import Path

from supabase import Client, create_client


SUPABASE_URL = "https://qgxvmqhotuzrwbqvvsfq.supabase.co"
SUPABASE_KEY = "sb_publishable_rmcVZlVyr2SOLaf8XeIncg_3Q2CI4n3"
CSV_PATH = Path(os.environ.get("FIGURE_CSV_PATH", "figures.csv"))
REQUIRED_COLUMNS = {"title", "shop_name", "price", "shop_url"}


def parse_price(value: str) -> int:
    normalized = value.strip().replace(",", "")
    if not re.fullmatch(r"\d+", normalized):
        raise ValueError(f"price must be a whole number, got {value!r}")
    return int(normalized)


def import_csv(csv_path: Path, client: Client) -> tuple[int, int]:
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"CSV file not found: {csv_path}. Add figures.csv to the repository "
            "or set FIGURE_CSV_PATH."
        )

    imported = 0
    skipped = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

        for row_number, row in enumerate(reader, start=2):
            title = (row.get("title") or "").strip()
            shop_name = (row.get("shop_name") or "").strip()
            shop_url = (row.get("shop_url") or "").strip()
            if not title or not shop_name or not shop_url:
                raise ValueError(
                    f"CSV row {row_number}: title, shop_name, and shop_url must not be blank"
                )
            try:
                price = parse_price(row.get("price") or "")
            except ValueError as error:
                raise ValueError(f"CSV row {row_number}: {error}") from error

            existing = (
                client.table("figure_shops")
                .select("id")
                .eq("shop_url", shop_url)
                .execute()
            )
            if existing.data:
                print(f"↪️ Row {row_number}: already imported, skipping {shop_url}")
                skipped += 1
                continue

            image_url1 = (row.get("image_url1") or "").strip()
            image_url2 = (row.get("image_url2") or "").strip()
            image_url3 = (row.get("image_url3") or "").strip()
            figure_result = (
                client.table("figures")
                .insert(
                    {
                        "title": title,
                        "manufacturer": (row.get("manufacturer") or "").strip() or "미정",
                        "scale": (row.get("scale") or "").strip() or "정보없음",
                        "release_date": (row.get("release_date") or "").strip() or "정보없음",
                        "image_url1": image_url1 or "https://via.placeholder.com/300",
                        "image_url2": image_url2,
                        "image_url3": image_url3,
                        "image_url": image_url1 or "https://via.placeholder.com/300",
                        "description": (row.get("description") or "").strip(),
                        "category": (row.get("category") or "").strip() or "기타",
                        "figure_type": (row.get("figure_type") or "").strip() or "기타",
                    }
                )
                .execute()
            )
            if not figure_result.data or "id" not in figure_result.data[0]:
                raise RuntimeError("Supabase did not return the inserted figure ID")

            client.table("figure_shops").insert(
                {
                    "figure_id": figure_result.data[0]["id"],
                    "shop_name": shop_name,
                    "price": price,
                    "shop_url": shop_url,
                }
            ).execute()
            print(f"✅ Row {row_number}: imported {title}")
            imported += 1

    if imported == 0 and skipped == 0:
        raise ValueError(f"CSV contains no product rows: {csv_path}")

    return imported, skipped


def main() -> None:
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    imported, skipped = import_csv(CSV_PATH, client)
    print(f"Import finished: {imported} imported, {skipped} already present.")


if __name__ == "__main__":
    main()
