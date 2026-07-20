from http.server import BaseHTTPRequestHandler
import json
import re
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

    # Step 1: metadata — title, brand, photos, article
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

    price = ""
    debug = {}

    # Step 2: HTML page — price from <meta> tag + more photos
    if shop_link:
        try:
            req2 = urllib.request.Request(
                f"https://kaspi.kz/shop{shop_link}?c=750000000",
                headers=html_headers,
            )
            with urllib.request.urlopen(req2, timeout=20) as r:
                html_status = r.status
                html = r.read().decode("utf-8", errors="replace")
            debug["html_status"] = html_status
            debug["html_len"] = len(html)

            m = re.search(r'<meta[^>]+property="product:price:amount"[^>]+content="(\d+)"', html)
            if not m:
                m = re.search(r'<meta[^>]+content="(\d+)"[^>]+property="product:price:amount"', html)
            if m:
                price = int(m.group(1))
                debug["price_src"] = "meta_tag"

            marker = "BACKEND.components.item = "
            pos = html.find(marker)
            debug["backend_marker"] = pos != -1
            if pos != -1:
                try:
                    js = html.index("{", pos + len(marker))
                    raw = _extract_json_object(html, js)
                    data = json.loads(raw) if raw else {}
                    html_photos = [
                        img.get("large") or img.get("medium") or img.get("small") or ""
                        for img in (data.get("galleryImages") or [])
                        if img.get("large") or img.get("medium") or img.get("small")
                    ]
                    if html_photos:
                        photos = html_photos
                    if not price:
                        price = (data.get("card") or {}).get("price") or ""
                        if price:
                            debug["price_src"] = "backend_json"
                    if article == sku:
                        for group in (data.get("specifications") or []):
                            for feat in (group.get("features") or []):
                                nl = (feat.get("name") or "").lower()
                                if any(k in nl for k in ("артикул", "article", "код товара")):
                                    vals = feat.get("featureValues") or []
                                    val = ", ".join(v.get("value", "") for v in vals if v.get("value"))
                                    if val:
                                        article = val
                                        break
                except Exception as e:
                    debug["backend_parse_err"] = str(e)
        except Exception as e:
            debug["html_err"] = str(e)

    # Step 3: offers API for price if still missing
    if not price:
        try:
            req3 = urllib.request.Request(
                f"https://kaspi.kz/yml/offer-view/offers/{sku}?cityId=750000000",
                headers=json_headers,
            )
            with urllib.request.urlopen(req3, timeout=10) as r:
                offers_status = r.status
                od = json.loads(r.read().decode("utf-8"))
            debug["offers_status"] = offers_status
            offers = od.get("offers") or []
            debug["offers_count"] = len(offers)
            prices = [o["price"] for o in offers if o.get("price")]
            if prices:
                price = min(prices)
                debug["price_src"] = "offers_api"
        except Exception as e:
            debug["offers_err"] = str(e)

    return {
        "sku": sku,
        "title": title,
        "brand": brand,
        "price": price,
        "photos": photos,
        "article": article,
        "_debug": debug,
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
