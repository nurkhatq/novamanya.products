чтоб делать запрос и достучаться к каспи важно упамянуть юзер эйджент, и вот пример функции как получить заказы и тд

self.session.headers.update({
            "X-Auth-Token": self.token,
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json, application/json",
            "User-Agent": f"MyKaspiIntegration/1.0 ({self.store_name})",
        })
        
def get_orders_batch(self, date_range: Dict[str, str], page: int = 0) -> List[Dict]:
        """Получает батч заказов для указанного диапазона дат и страницы"""
        
        start_timestamp = int(datetime.datetime.fromisoformat(date_range["start"].replace('Z', '+00:00')).timestamp() * 1000)
        end_timestamp = int(datetime.datetime.fromisoformat(date_range["end"].replace('Z', '+00:00')).timestamp() * 1000)
        
        days_diff = (end_timestamp - start_timestamp) / (1000 * 60 * 60 * 24)
        if days_diff > 14:
            raise ValueError(f"Date range too large: {days_diff} days. Max allowed: 14 days")
        
        url = f"{self.common_config['API_BASE_URL']}/orders"
        params = {
            "page[number]": page,
            "page[size]": self.common_config["BATCH_SIZE"],
            "filter[orders][creationDate][$ge]": start_timestamp,
            "filter[orders][creationDate][$le]": end_timestamp,
            "include[orders]": "user,deliveryAddress",
            "sort": "creationDate"
        }
        
        logging.info(f"[{self.store_name}] API запрос: период {round(days_diff)} дней, страница {page}, размер батча {self.common_config['BATCH_SIZE']}")
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            orders_count = len(data.get("data", []))
            logging.info(f"[{self.store_name}] Успешный запрос: получено {orders_count} заказов")
            
            return data.get("data", [])
            
        except requests.exceptions.RequestException as e:
            logging.error(f"[{self.store_name}] Ошибка API запроса: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logging.error(f"[{self.store_name}] Статус код: {e.response.status_code}")
            raise
        except Exception as e:
            logging.error(f"[{self.store_name}] Неожиданная ошибка при получении заказов: {e}")
            raise


 def get_order_details(self, order_id: str) -> Dict:
        """Получает детальную информацию о заказе"""
        url = f"{self.common_config['API_BASE_URL']}/orders/{order_id}"
        logging.debug(f"[{self.store_name}] Запрос деталей заказа: {order_id}")
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("data", {})
        except requests.exceptions.RequestException as e:
            logging.error(f"[{self.store_name}] Ошибка получения деталей заказа {order_id}: {e}")
            return {}
        except Exception as e:
            logging.error(f"[{self.store_name}] Неожиданная ошибка при получении деталей заказа {order_id}: {e}")
            return {}