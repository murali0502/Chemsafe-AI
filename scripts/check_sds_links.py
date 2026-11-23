"""Verify that published manufacturer URLs serve Safety Data Sheet PDFs."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_netlify import load_sds_catalog


def check(product):
    url = product["sds_url"]
    request = Request(url, headers={"Range": "bytes=0-4", "User-Agent": "Chemsafe-Release-Check/1"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=25) as response:
                if response.read(5) != b"%PDF-":
                    raise ValueError("response did not start with a PDF signature")
            return product["product_code"], None
        except (OSError, URLError, ValueError) as error:
            if attempt == 2:
                return product["product_code"], str(error)
            time.sleep(2 ** attempt)


def main():
    products = [item for items in load_sds_catalog().values() for item in items]
    failed = False
    with ThreadPoolExecutor(max_workers=4) as pool:
        for code, error in pool.map(check, products):
            if error:
                print(f"{code}: {error}", file=sys.stderr)
                failed = True
            else:
                print(f"{code}: manufacturer PDF available")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
