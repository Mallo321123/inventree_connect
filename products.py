from dotenv import load_dotenv
import os
import requests
import json


from db import get_db, close_db
from log_config import setup_logging

logging = setup_logging()


def update_products():
    update_products_shopware()
    sync_inventree()


# updates product db from shopware
def update_products_shopware():
    load_dotenv()
    base_url = os.getenv("SHOPWARE_URL")

    limit = 50
    page = 1
    counter = 0
    count_update = 0

    def request(page, limit):
        try:
            # Token bei jedem Request neu einlesen
            with open("auth.json", "r") as f:
                auth_data = json.load(f)

            access_token = auth_data["shopware_token"]

            auth_headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.get(
                f"{base_url}/api/product?limit={limit}&page={page}&associations[children][]",
                headers=auth_headers,
                timeout=10,  # 10 Sekunden Timeout
            )

            if response.status_code != 200:
                logging.error(
                    f"Fehler beim Abrufen der Shopware Produkten: {response.status_code}"
                )
                logging.error(f"Fehlerdetails: {response.text}")
                return

            product_data = response.json()

            return product_data["data"], product_data["total"]

        except requests.exceptions.Timeout:
            logging.error("Timeout beim Abrufen der Shopware Produkt liste")
            return
        except requests.exceptions.RequestException as e:
            logging.error(f"Fehler beim Abrufen der Shopware Produkte: {e}")
            logging.error(f"Fehlerdetails: {str(e)}")
            return
        except Exception as e:
            logging.error(f"Error: {e}")
            return None

    conn, cursor = get_db()

    while True:
        products, product_count = request(page, limit)

        if products is None:
            break

        for product in products:                
            if product["name"] is None:
                logging.warning(f"Produkt hat keinen Namen, produktNumber: {product['productNumber']}")
                continue
                
            if product["children"] is not None:
                
                for child in product["children"]:
                    
                    if child["name"] is None:
                        logging.warning(f"Produkt hat keinen Namen, produktNumber: {child['productNumber']}")
                        child["name"] = child["productNumber"]

                    cursor.execute(
                        """
                        SELECT * FROM products WHERE shopware_id = ?
                    """,
                        (child["id"],),
                    )

                    if cursor.fetchone() is None:
                        cursor.execute(
                            """
                            INSERT INTO products (shopware_id, name, description, is_in_shopware, active, productNumber)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """,
                            (
                                child["id"],
                                child["name"],
                                child["description"],
                                True,
                                child["active"],
                                child["productNumber"],
                            ),
                        )
                        count_update += 1
                    else:
                        cursor.execute(
                            """
                            UPDATE products
                            SET name = ?, description = ?, active = ?, productNumber = ?
                            WHERE shopware_id = ?
                        """,
                            (
                                child["name"],
                                child["description"],
                                child["active"],
                                child["productNumber"],
                                child["id"],
                            ),
                        )
                        count_update += 1

                    counter += 1
                    conn.commit()

            cursor.execute(
                """
                SELECT * FROM products WHERE shopware_id = ?
            """,
                (product["id"],),
            )

            if cursor.fetchone() is None:
                cursor.execute(
                    """
                    INSERT INTO products (shopware_id, name, description, is_in_shopware, active, productNumber)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        product["id"],
                        product["name"],
                        product["description"],
                        True,
                        product["active"],
                        product["productNumber"],
                    ),
                )
                count_update += 1
            else:
                cursor.execute(
                    """
                    UPDATE products
                    SET name = ?, description = ?, active = ?, productNumber = ?
                    WHERE shopware_id = ?
                """,
                    (
                        product["name"],
                        product["description"],
                        product["active"],
                        product["productNumber"],
                        product["id"],
                    ),
                )
                count_update += 1

            counter += 1
            conn.commit()

        if product_count < limit:
            break

        page += 1

    logging.info(f"{count_update} Produkte aktualisiert, {counter} Produkte insgesamt")
    close_db(conn)


def valid_shopware_product():
    load_dotenv()
    base_url = os.getenv("SHOPWARE_URL")

    conn, cursor = get_db()

    def request(id):
        try:
            # Token bei jedem Request neu einlesen
            with open("auth.json", "r") as f:
                auth_data = json.load(f)

            access_token = auth_data["shopware_token"]

            auth_headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.get(
                f"{base_url}/api/product/{id}",
                headers=auth_headers,
                timeout=10,  # 10 Sekunden Timeout
            )

            if response.status_code == 404:
                return response.status_code

            if response.status_code != 200:
                logging.error(
                    f"Fehler beim Abrufen des Shopware Produktes: {response.status_code}"
                )
                logging.error(f"Fehlerdetails: {response.text}")
                return None

            product_data = response.json()
            return product_data["data"]

        except requests.exceptions.Timeout:
            logging.error("Timeout beim Abrufen des Shopware Produktes")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Fehler beim Abrufen des Shopware Produktes: {e}")
            logging.error(f"Fehlerdetails: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error: {e}")
            return None

    cursor.execute("""
                   Select shopware_id from products WHERE is_in_shopware = 1
                   """)

    shopware_ids = cursor.fetchall()

    for shopware_id in shopware_ids:
        product = request(shopware_id[0])

        if product == 404:
            cursor.execute(
                """
                UPDATE products
                SET is_in_shopware = ?
                WHERE shopware_id = ?
            """,
                (False, shopware_id[0]),
            )
            conn.commit()
            logging.info(f"Produkt {shopware_id[0]} nicht mehr in Shopware")

    close_db(conn)
    logging.info("Shopware Produkte validiert")


def sync_inventree():
    load_dotenv()
    base_url = os.getenv("INVENTREE_URL")

    def request(data):
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
                f"{base_url}/api/part/",
                json=data,
                timeout=10,
                headers=headers,
            )

            if response.status_code != 201:
                logging.error(f"fehler beim erstellen dieses Produktes: {data}")
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

    cursor.execute("""
        SELECT name, description, active, id FROM products WHERE is_in_shopware = 1 AND (is_in_inventree = 0 OR inventree_id IS NULL)
    """)
    products = cursor.fetchall()

    for product in products:
        # Sanitize description by removing problematic characters
        if product[1]:
            product_desc = (
                product[1]
                .replace("<", "")
                .replace(">", "")
                .replace("/", "")
                .replace("\\", "")
                .replace("div", "")
                .replace('span="de"', "")
            )
        else:
            product_desc = ""

        product_desc = product_desc[:250]

        name = product[0][:100]
        
        try:
            active = product[2]
            
            if active != 1 or active != 0:
                active = 1
                
            else:
                active = bool(active)
                
        except Exception as e:
            logging.error(f"Error: {e}")
            active = 1

        data = {
            "name": name,
            "description": product_desc,
            "active": bool(active),
            "minimum_stock": 10,  # Default Value
            "salable": True,
        }

        response = request(data)

        cursor.execute(
            """
            UPDATE products
            SET is_in_inventree = ?, inventree_id = ?
            WHERE id = ?
        """,
            (True, response["pk"], product[3]),
        )

        conn.commit()

    close_db(conn)
    logging.info("Inventree Produkte synchronisiert")
