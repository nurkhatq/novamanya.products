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

    # Photos from metadata (fallback)
    meta_photos = [
        img.get("large") or img.get("medium") or img.get("small") or ""
        for img in (meta.get("galleryImages") or [])
        if img.get("large") or img.get("medium") or img.get("small")
    ]

    if not shop_link:
        return {"sku": sku, "title": title_fb, "brand": brand_fb,
                "price": "", "photos": meta_photos, "article": ""}

    # Step 2: HTML page — price, article, all photos
    try:
        req2 = urllib.request.Request(
            f"https://kaspi.kz/shop{shop_link}?c=750000000",
            headers=html_headers,
        )
        with urllib.request.urlopen(req2, timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        return {"sku": sku, "title": title_fb, "brand": brand_fb,
                "price": "", "photos": meta_photos, "article": ""}

    marker = "BACKEND.components.item = "
    pos = html.find(marker)
    if pos == -1:
        return {"sku": sku, "title": title_fb, "brand": brand_fb,
                "price": "", "photos": meta_photos, "article": ""}

    try:
        json_start = html.index("{", pos + len(marker))
    except ValueError:
        return {"sku": sku, "title": title_fb, "brand": brand_fb,
                "price": "", "photos": meta_photos, "article": ""}

    raw = _extract_json_object(html, json_start)
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}

    item_card = data.get("card") or {}
    images = data.get("galleryImages") or []
    specs = data.get("specifications") or []

    photos = [
        img.get("large") or img.get("medium") or img.get("small") or img.get("url") or ""
        for img in images
        if img.get("large") or img.get("medium") or img.get("small") or img.get("url")
    ] or meta_photos

    brand = (item_card.get("promoConditions") or {}).get("brand", "") or item_card.get("brand", "") or brand_fb
    price = item_card.get("price") or ""

    article = ""
    for group in specs:
        for feat in (group.get("features") or []):
            nl = (feat.get("name") or "").lower()
            if any(k in nl for k in ("артикул", "article", "код товара")):
                vals = feat.get("featureValues") or []
                val = ", ".join(v.get("value", "") for v in vals if v.get("value"))
                if val:
                    article = val
                    break

    return {
        "sku": sku,
        "title": item_card.get("title", "") or title_fb,
        "brand": brand,
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
