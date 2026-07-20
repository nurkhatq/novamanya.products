from http.server import BaseHTTPRequestHandler
import json
import urllib.request


def _extract_json_object(text, start):
    i, depth, in_string, escape = start, 0, False, False
    while i < len(text):
        ch = text[i]
        if escape:
            escape = False
        elif ch == "\\" and in_string:
            escape = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start: i + 1]
        i += 1
    return ""


def fetch_price(sku, json_headers):
    """Try to get min price from offers API."""
    try:
        req = urllib.request.Request(
            f"https://kaspi.kz/yml/offer-view/offers/{sku}?cityId=750000000",
            headers=json_headers,
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        offers = data.get("offers") or data.get("data") or []
        prices = [o.get("price") for o in offers if o.get("price")]
        if prices:
            return min(prices)
    except Exception:
        pass
    return ""


def fetch_kaspi(sku):
    json_headers = {
        "accept": "application/json, */*",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "referer": "https://kaspi.kz/",
        "X-KS-City": "750000000",
    }
    html_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "ru,en;q=0.9",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1",
        "referer": "https://kaspi.kz/shop/",
    }

    # Step 1: metadata
    try:
        req = urllib.request.Request(
            f"https://kaspi.kz/yml/content/item/product/{sku}",
            headers=json_headers,
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            meta = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

    card = meta.get("card") or {}
    shop_link = card.get("shopLink")

    title_fb = card.get("name") or card.get("title", "")
    brand_fb = (card.get("promoConditions") or {}).get("brand", "") or card.get("brand", "")

    # All photos from metadata
    meta_photos = [
        img.get("large") or img.get("medium") or img.get("small") or ""
        for img in (meta.get("galleryImages") or [])
        if img.get("large") or img.get("medium") or img.get("small")
    ]

    # Article from metadata specs
    article = sku
    for group in (meta.get("specifications") or []):
        for feat in (group.get("features") or []):
            nl = (feat.get("name") or "").lower()
            if any(k in nl for k in ("артикул", "article", "код товара")):
                vals = feat.get("featureValues") or []
                val = ", ".join(v.get("value", "") for v in vals if v.get("value"))
                if val:
                    article = val
                    break

    if not shop_link:
        price = fetch_price(sku, json_headers)
        return {"sku": sku, "title": title_fb, "brand": brand_fb,
                "price": price, "photos": meta_photos, "article": article}

    # Step 2: HTML page — may give price + more photos
    price = ""
    photos = meta_photos
    try:
        req2 = urllib.request.Request(
            f"https://kaspi.kz/shop{shop_link}?c=750000000",
            headers=html_headers,
        )
        with urllib.request.urlopen(req2, timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")

        marker = "BACKEND.components.item = "
        pos = html.find(marker)
        if pos != -1:
            try:
                json_start = html.index("{", pos + len(marker))
                raw = _extract_json_object(html, json_start)
                data = json.loads(raw) if raw else {}
                item_card = data.get("card") or {}
                images = data.get("galleryImages") or []
                specs = data.get("specifications") or []

                html_photos = [
                    img.get("large") or img.get("medium") or img.get("small") or img.get("url") or ""
                    for img in images
                    if img.get("large") or img.get("medium") or img.get("small") or img.get("url")
                ]
                if html_photos:
                    photos = html_photos

                price = item_card.get("price") or ""

                # Try article from HTML specs (more complete)
                if article == sku:
                    for group in specs:
                        for feat in (group.get("features") or []):
                            nl = (feat.get("name") or "").lower()
                            if any(k in nl for k in ("артикул", "article", "код товара")):
                                vals = feat.get("featureValues") or []
                                val = ", ".join(v.get("value", "") for v in vals if v.get("value"))
                                if val:
                                    article = val
                                    break

                brand_fb = (item_card.get("promoConditions") or {}).get("brand", "") or item_card.get("brand", "") or brand_fb
                title_fb = item_card.get("title", "") or title_fb
            except Exception:
                pass
    except Exception:
        pass

    # If still no price, try offers API
    if not price:
        price = fetch_price(sku, json_headers)

    return {
        "sku": sku,
        "title": title_fb,
        "brand": brand_fb,
        "price": price,
        "photos": photos,
        "article": article,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        sku = self.path.rstrip("/").split("/")[-1].split("?")[0]
        result = fetch_kaspi(sku)
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        status = 200 if "error" not in result else 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
