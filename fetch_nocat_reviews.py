"""
fetch_nocat_reviews.py
Запуск: python fetch_nocat_reviews.py

Что делает:
  1. Тянет базу с VPS
  2. Находит все "нет в Kaspi" карточки (status пустой) у которых есть дубли
  3. Для каждого SKU (главный + дубли) запрашивает кол-во отзывов с Kaspi
  4. Определяет лучший дубль (больше всего отзывов)
  5. Отправляет результат на VPS → /api/update-reviews
"""

import asyncio
import aiohttp
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

VPS_API  = "http://194.238.41.18/products/api"
KASPI    = "https://kaspi.kz"
CONCURRENCY = 15

HEADERS = {
    "accept":     "application/json, */*",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "referer":    "https://kaspi.kz/",
}

def kaspi_sku(sku):
    """144221726_894491249 → 144221726"""
    return sku.split("_")[0]


async def fetch_reviews(session, sem, sku):
    ksku = kaspi_sku(sku)
    url  = f"{KASPI}/yml/creview/rest/misc/product/{ksku}/summary"
    async with sem:
        for attempt in range(3):
            try:
                async with session.get(url) as r:
                    if r.status == 200:
                        data = (await r.json(content_type=None)).get("data") or {}
                        return {
                            "sku":     sku,
                            "ksku":    ksku,
                            "reviews": data.get("reviewsCount") or 0,
                            "rating":  data.get("global") or 0,
                        }
                    if r.status in (429, 503):
                        await asyncio.sleep(5 * (attempt + 1))
                    else:
                        break
            except Exception:
                await asyncio.sleep(1.5)
    return {"sku": sku, "ksku": ksku, "reviews": 0, "rating": 0}


async def main():
    import requests

    # 1. Загружаем базу с VPS
    print("1. Загружаю базу с VPS...")
    db = requests.get(f"{VPS_API}/db", timeout=30).json()
    print(f"   {len(db)} записей")

    # 2. Находим nocat с дублями
    def is_nocat(r):
        return (not (r.get("catalog_info") or {}).get("status")
                and r.get("source") != "kaspi_only")

    nocat_with_dups = [r for r in db if r and is_nocat(r) and r.get("dop_skus")]
    print(f"   Нет в Kaspi с дублями: {len(nocat_with_dups)}")

    if not nocat_with_dups:
        print("Нечего обрабатывать.")
        return

    # 3. Собираем все SKU для запроса отзывов
    all_skus = set()
    for rec in nocat_with_dups:
        all_skus.add(rec["main_sku"])
        for d in rec["dop_skus"]:
            all_skus.add(d)
    print(f"\n2. Запрашиваю отзывы для {len(all_skus)} SKU с Kaspi...")

    sem       = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    timeout   = aiohttp.ClientTimeout(total=15)

    reviews_map = {}  # sku → {reviews, rating}
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector, timeout=timeout) as session:
        tasks = [fetch_reviews(session, sem, sku) for sku in all_skus]
        done  = 0
        for coro in asyncio.as_completed(tasks):
            res = await coro
            reviews_map[res["sku"]] = res
            done += 1
            print(f"   {done}/{len(all_skus)}  {res['sku']} → {res['reviews']} отзывов", end="\r")
    print()

    # 4. Строим результат
    print("\n3. Определяю лучшие дубли...")
    result = {}
    for rec in nocat_with_dups:
        main_sku  = rec["main_sku"]
        dop_skus  = rec["dop_skus"]
        main_rev  = reviews_map.get(main_sku, {})

        dups_info = []
        for d in dop_skus:
            info = reviews_map.get(d, {})
            dups_info.append({
                "sku":     d,
                "reviews": info.get("reviews", 0),
                "rating":  info.get("rating",  0),
            })

        # Лучший дубль — у кого больше отзывов (при равенстве — выше рейтинг)
        best = max(dups_info, key=lambda x: (x["reviews"], x["rating"])) if dups_info else None

        entry = {
            "main_sku":      main_sku,
            "main_reviews":  main_rev.get("reviews", 0),
            "main_rating":   main_rev.get("rating",  0),
            "dups":          dups_info,
            "best_dup":      best["sku"]      if best else None,
            "best_reviews":  best["reviews"]  if best else 0,
            "best_rating":   best["rating"]   if best else 0,
        }
        result[main_sku] = entry

        print(f"   {main_sku}: главный={main_rev.get('reviews',0)} отз, "
              f"лучший дубль={best['sku'] if best else '—'} ({best['reviews'] if best else 0} отз)")

    # 5. Отправляем на VPS
    print(f"\n4. Отправляю результат на VPS ({len(result)} записей)...")
    r = requests.post(
        f"{VPS_API}/update-reviews",
        json={"reviews": result},
        timeout=30,
    )
    if r.status_code == 200:
        print("   ✓ Успешно сохранено на VPS")
    else:
        print(f"   ✗ Ошибка: {r.status_code} {r.text[:200]}")

    # Сохраняем локально тоже
    with open("nocat_reviews.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("   Локально: nocat_reviews.json")

    print(f"\n{'═'*55}")
    print(f"  Обработано: {len(result)} карточек")
    has_best = sum(1 for v in result.values() if v["best_dup"])
    print(f"  С лучшим дублем: {has_best}")
    print(f"{'═'*55}")


if __name__ == "__main__":
    asyncio.run(main())
