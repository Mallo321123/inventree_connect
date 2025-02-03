from dotenv import load_dotenv
import os
import requests
import json

from db import get_db, close_db
from log_config import setup_logging

logging = setup_logging()


def update_addresses():
    logging.info("Starte Adressen Update")

    update_addresses_shopware()
    sync_inventree()

    logging.info("Adressen Update abgeschlossen")


def update_addresses_shopware():
    load_dotenv()
    base_url = os.getenv("SHOPWARE_URL")

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
                f"{base_url}/api/customer/{id}?associations[addresses][]",
                headers=auth_headers,
                timeout=10,  # 10 Sekunden Timeout
            )

            if response.status_code != 200:
                logging.error(
                    f"Fehler beim Abrufen des Shopware Kunden: {response.status_code}"
                )
                logging.error(f"Fehlerdetails: {response.text}")
                return

            customer_data = response.json()

            return customer_data["data"]

        except requests.exceptions.Timeout:
            logging.error("Timeout beim Abrufen des Shopware Kunden")
            return
        except requests.exceptions.RequestException as e:
            logging.error(f"Fehler beim Abrufen des Shopware Kunden: {e}")
            logging.error(f"Fehlerdetails: {str(e)}")
            return
        except Exception as e:
            logging.error(f"Error: {e}")
            return None

    conn, cursor = get_db()

    cursor.execute("SELECT shopware_id FROM customers WHERE is_in_shopware = 1")
    customers = cursor.fetchall()

    counter = 0

    for customer in customers:
        shopware_id = customer[0]
        customer_data = request(shopware_id)
        addresses = customer_data["addresses"]

        if customer_data is None:
            logging.error(f"Kunde mit ID {shopware_id} konnte nicht abgerufen werden")
            continue

        for address in addresses:
            cursor.execute(
                """
                           SELECT * FROM addresses WHERE shopware_id = ?
                           """,
                (address["id"],),
            )

            address_exists = cursor.fetchone()

            if address_exists is None:
                cursor.execute(
                    """
                               SELECT id FROM customers WHERE shopware_id = ?
                               """,
                    (shopware_id,),
                )

                customer_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                                 INSERT INTO addresses (
                                    shopware_id,
                                    is_in_shopware,
                                    customer_id,
                                    firstName,
                                    lastName,
                                    zipcode,
                                    city,
                                    street
                                    ) VALUES (?, 1, ?, ?, ?, ?, ?, ?)""",
                    (
                        address["id"],
                        customer_id,
                        address["firstName"],
                        address["lastName"],
                        address["zipcode"],
                        address["city"],
                        address["street"],
                    ),
                )

                conn.commit()

                counter += 1

    logging.info(f"{counter} Adressen wurden hinzugefügt")
    close_db(conn)


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
                f"{base_url}/api/company/address/",
                json=data,
                timeout=10,
                headers=headers,
            )

            if response.status_code != 201:
                logging.error(f"fehler beim erstellen dieser Adresse: {data}")
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

    cursor.execute(
        "SELECT id, customer_id, firstName, lastName, zipcode, city, street FROM addresses WHERE is_in_inventree = 0 OR inventree_id IS NULL"
    )

    addresses = cursor.fetchall()

    counter = 0

    for address in addresses:
        cursor.execute(
            """
                       SELECT inventree_id FROM customers WHERE id = ?
                          """,
            (address[1],),
        )

        customer_id = cursor.fetchone()[0]

        data = {
            "company": customer_id,
            "title": address[0],
            "line1": address[2] + " " + address[3],
            "line2": address[6],
            "postal_code": address[4],
            "postal_city": address[5],
        }

        response = request(data)

        cursor.execute(
            """
                       UPDATE addresses SET is_in_inventree = 1, inventree_id = ? WHERE id = ?
                          """,
            (response["pk"], address[0]),
        )

        conn.commit()

        counter += 1
        break

    logging.info(f"{counter} Adressen wurden hinzugefügt")
    close_db(conn)
