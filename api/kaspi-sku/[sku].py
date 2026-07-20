from http.server import BaseHTTPRequestHandler
import json
import urllib.request


def fetch_kaspi(sku):
    headers = {
        "accept": "application/json, */*",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "referer": "https://kaspi.kz/",
        "X-KS-City": "750000000",
    }
    try:
        req = urllib.request.Request(
            f"https://kaspi.kz/yml/content/item/product/{sku}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            meta = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

    card = meta.get("card") or {}
    title = card.get("name") or card.get("title", "")
    brand = (card.get("promoConditions") or {}).get("brand", "") or card.get("brand", "")

    photos = [
        img.get("large") or img.get("medium") or img.get("small") or ""
        for img in (meta.get("galleryImages") or [])
        if img.get("large") or img.get("medium") or img.get("small")
    ]

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

    return {"sku": sku, "title": title, "brand": brand, "photos": photos, "article": article}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        sku = self.path.rstrip("/").split("/")[-1].split("?")[0]
        result = fetch_kaspi(sku)
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(200 if "error" not in result else 500)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
