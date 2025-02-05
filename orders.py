import requests
import json
import os
from dotenv import load_dotenv

from db import get_db, close_db
from customers import create_customer_db, create_customer_inventree
from log_config import setup_logging
from addresses import create_address_db, create_address_inventree
from datetime import datetime

logging = setup_logging()


def update_orders():
    #update_orders_shopware()
    sync_orders_inventree()

def update_orders_shopware():
    load_dotenv()
    base_url = os.getenv("SHOPWARE_URL")

    def request(limit = 10):
        try:
            # Token bei jedem Request neu einlesen
            with open("auth.json", "r") as f:
                auth_data = json.load(f)

            access_token = auth_data["shopware_token"]

            auth_headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            response = requests.get(
                f"{base_url}/api/order?sort=-orderDateTime&limit={limit}&associations[addresses][]&associations[lineItems][]&associations[orderCustomer][]",  # Limit direkt in der Query
                headers=auth_headers,
                timeout=10,  # 10 Sekunden Timeout
            )

            if response.status_code != 200:
                logging.error(
                    f"Fehler beim Abrufen der Shopware Bestellungen: {response.status_code}"
                )
                logging.error(f"Fehlerdetails: {response.text}")
                return

            orders_data = response.json()
            return orders_data["data"], orders_data["total"]

        except requests.exceptions.Timeout:
            logging.error("Timeout beim Abrufen der Shopware Bestellungen")
            return
        except requests.exceptions.RequestException as e:
            logging.error(f"Fehler beim Abrufen der Shopware Bestellungen: {e}")
            logging.error(f"Fehlerdetails: {str(e)}")
            return
        except Exception as e:
            logging.error(f"Error: {e}")
            return None
        
    conn, cursor = get_db()

    order_count = 10    # Anzahl der Bestellungen, die rückläufig abgerufen werden sollen
    
    orders, orders_total = request(order_count)

    counter_new = 0
    product_counter = 0
    
    for order in orders:
        cursor.execute("""SELECT id FROM orders WHERE shopware_id = ?""", (order["id"],))
        
        with open("order.json", "w") as f:
            json.dump(order, f)
        
        if cursor.fetchone() is None:   # When order is not in database
            try:
                cursor.execute("""SELECT id FROM customers WHERE shopware_id = ?""", (order["orderCustomer"]["id"],))
                customer_id = cursor.fetchone()[0]
            
            except TypeError:
                logging.warning(f"Kunde {order['orderCustomer']['id']} nicht in Datenbank gefunden")
                customer_id = None
                pass
            
            if customer_id is None:
                data = {
                    "inventree_id": None,
                    "shopware_id": order["orderCustomer"]["id"],
                    "is_in_shopware": True,
                    "is_in_inventree": None,
                    "firstName": order["orderCustomer"]["firstName"],
                    "lastName": order["orderCustomer"]["lastName"],
                    "email": order["orderCustomer"]["email"],
                }
                
                customer_id = create_customer_db(data)
            
            products = []
            
            for item in order["lineItems"]:
                cursor.execute(
                    """SELECT id FROM products WHERE shopware_id = ?""",
                    (item["productId"],),
                )
                product_id = cursor.fetchone()[0]
                quantity = item["quantity"]

                item = {
                    product_id: quantity
                }
                
                products.append(item)
                product_counter += 1
            
            try:
                cursor.execute("""SELECT id FROM addresses WHERE shopware_id = ?""", (order["addresses"][0]["id"],))
                address_id = cursor.fetchone()[0]
            except TypeError:
                logging.warning(f"Adresse {order['addresses'][0]['id']} nicht in Datenbank gefunden")
                data = {
                    "inventree_id": None,
                    "shopware_id": order["addresses"][0]["id"],
                    "is_in_shopware": True,
                    "is_in_inventree": None,
                    "customer_id": customer_id,
                    "firstName": order["addresses"][0]["firstName"],
                    "lastName": order["addresses"][0]["lastName"],
                    "street": order["addresses"][0]["street"],
                    "zipcode": order["addresses"][0]["zipcode"],
                    "city": order["addresses"][0]["city"],
                }
                address_id = create_address_db(data)
                
            products = json.dumps(products)
            
            cursor.execute(
                """INSERT INTO orders (shopware_id, is_in_shopware, shopware_order_number, creation_date, customer_id, state, products, address_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order["id"],
                    True,
                    order["orderNumber"],
                    order["orderDateTime"],
                    customer_id,
                    order["stateMachineState"]["name"],
                    products,
                    address_id,
                ),
            )
            
            counter_new += 1
            
            conn.commit()
            
        else:
            continue
            # Todo: Update existing orders
    
    logging.info(f"{counter_new} neue Bestellungen hinzugefügt, insgesamt {orders_total} Bestellungen Verarbeitet")
    

def sync_orders_inventree():
    load_dotenv()
    base_url = os.getenv("INVENTREE_URL")
    
    def create(data):
        try:
            # Token bei jedem Request neu einlesen
            with open("auth.json", "r") as f:
                auth_data = json.load(f)

            access_token = auth_data["inventree_token"]

            headers = {
                "Accept": "application/json",
                "Authorization": f"Token {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                f"{base_url}/api/order/so/",
                json=data,
                timeout=10,
                headers=headers,
            )

            if response.status_code != 201:
                logging.error(f"fehler beim erstellen dieser Bestellung: {data}")
                logging.error(f"Error response body: {response.text}")
                return

            return response.json()

        except requests.exceptions.Timeout:
            logging.error("Request timed out after 10 seconds")
            return None

        except requests.exceptions.RequestException as e:
            logging.error(f"POST failed: {e}")
            logging.error(f"Error details: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error: {e}")
            return None
    
    def add_product(data):
        try:
            # Token bei jedem Request neu einlesen
            with open("auth.json", "r") as f:
                auth_data = json.load(f)

            access_token = auth_data["inventree_token"]

            headers = {
                "Accept": "application/json",
                "Authorization": f"Token {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                f"{base_url}/api/order/so-line/",
                json=data,
                timeout=10,
                headers=headers,
            )

            if response.status_code != 201:
                logging.error(f"fehler beim hinzufügen von Produkten zu einer Bestellung: {data}")
                logging.error(f"Error response body: {response.text}")
                return

            return response.json()

        except requests.exceptions.Timeout:
            logging.error("Request timed out after 10 seconds")
            return None

        except requests.exceptions.RequestException as e:
            logging.error(f"POST failed: {e}")
            logging.error(f"Error details: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error: {e}")
            return None
    
    def get_stock(id):
        try:
            # Token bei jedem Request neu einlesen
            with open("auth.json", "r") as f:
                auth_data = json.load(f)

            access_token = auth_data["inventree_token"]

            headers = {
                "Accept": "application/json",
                "Authorization": f"Token {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.get(
                f"{base_url}/api/stock/?available=true&part={id}&limit=10",
                timeout=10,
                headers=headers,
            )

            if response.status_code != 201:
                logging.error(
                    f"fehler beim abrufen des Lagerbestandes: {data}"
                )
                logging.error(f"Error response body: {response.text}")
                return

            return response.json()

        except requests.exceptions.Timeout:
            logging.error("Request timed out after 10 seconds")
            return None

        except requests.exceptions.RequestException as e:
            logging.error(f"GET failed: {e}")
            logging.error(f"Error details: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error: {e}")
            return None
    
    def alocate_stock(data):
        try:
            # Token bei jedem Request neu einlesen
            with open("auth.json", "r") as f:
                auth_data = json.load(f)

            access_token = auth_data["inventree_token"]

            headers = {
                "Accept": "application/json",
                "Authorization": f"Token {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                f"{base_url}/api/order/so-line/",
                json=data,
                timeout=10,
                headers=headers,
            )

            if response.status_code != 201:
                logging.error(
                    f"fehler beim hinzufügen von stock zu einer Bestellung: {data}"
                )
                logging.error(f"Error response body: {response.text}")
                return

            return response.json()

        except requests.exceptions.Timeout:
            logging.error("Request timed out after 10 seconds")
            return None

        except requests.exceptions.RequestException as e:
            logging.error(f"POST failed: {e}")
            logging.error(f"Error details: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error: {e}")
            return None
    
    conn, cursor = get_db()
    
    cursor.execute("""SELECT shopware_order_number, creation_date, customer_id, products, address_id, id FROM orders WHERE is_in_inventree = 0 OR is_in_inventree IS NULL""")
    
    orders = cursor.fetchall()
    
    counter = 0
    product_counter = 0
    
    for order in orders:
        
        creation_date = order[1].split("T")[0]
        
        cursor.execute("""SELECT inventree_id FROM addresses WHERE id = ?""", (order[4],))
        address_id = cursor.fetchone()[0]    
        
        cursor.execute("""SELECT inventree_id FROM customers WHERE id = ?""", (order[2],))
        customer_id = cursor.fetchone()[0]
        
        if customer_id is None:
            logging.warning(f"Kunde {order[2]} ist noch nicht in Inventree")
            customer_id = create_customer_inventree(order[2])
            
            if customer_id is None:
                logging.error(f"Kunde {order[2]} konnte nicht in Inventree erstellt werden")
                continue
            
        if address_id is None:
            logging.warning(f"Adresse {order[4]} ist noch nicht in Inventree")
            address_id = create_address_inventree(order[4])
            
            if address_id is None:
                logging.error(f"Adresse {order[4]} konnte nicht in Inventree erstellt werden")
                continue
        
        
        reference = f"SO-{''.join(filter(str.isdigit, order[0]))}"
        
        data = {
            "creation_date": creation_date,
            "customer_reference": order[0],
            "address": address_id,
            "customer": customer_id,
            "reference": reference,
            "order_currency": "EUR",
        }
        
        response = create(data)
        
        try:
            order_id = response["pk"]
        except TypeError:
            logging.error(f"Bestellung {order[0]} konnte nicht in Inventree erstellt werden")
            continue
        
        if response is not None:
            cursor.execute("""UPDATE orders SET is_in_inventree = 1, inventree_id = ? WHERE id = ?""", (order_id, order[5]))
            conn.commit()
        else:
            logging.error(f"Bestellung {order[0]} konnte nicht in Inventree erstellt werden")
            continue
            
        products = json.loads(order[3])
        
        for product_item in products:
            for product_id, quantity in product_item.items():
                cursor.execute("""SELECT inventree_id FROM products WHERE id = ?""", (product_id,))
                inventree_product_id = cursor.fetchone()[0]
                
                data = {
                    "order": order_id,
                    "part": inventree_product_id,
                    "quantity": quantity,
                    "sale_price_currency": "EUR",
                }
                
            respone = add_product(data)
            
            product_counter += 1
            
            stock = get_stock(inventree_product_id)
            
            if stock is None:
                logging.warning(f"Kein Lagerbestand für Produkt {inventree_product_id} gefunden")
                continue
            
            if stock[0]["quantity"] < quantity:
                logging.warning(f"Produkt {inventree_product_id} nicht genügend Lagerbestand")
                continue
            
            data = {
                0: {
                    "line_item": respone["pk"],
                    "quantity": quantity,
                    "stock_item": stock[0]["pk"],
                }
            }
            
            response = alocate_stock(data)
        
        counter += 1
    
    close_db(conn)
    logging.info(f"{counter} Bestellungen mit {product_counter} Produkten in Inventree synchronisiert")