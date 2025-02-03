from dotenv import load_dotenv
import os
import requests
import json
import threading

from db import get_db, close_db
from log_config import setup_logging

logging = setup_logging()


def update_addresses():
    logging.info("Starte Adressen Update")

    address_thread = threading.Thread(target=update_addresses_shopware)
    sync_thread = threading.Thread(target=sync_inventree)

    address_thread.start()
    # sync_thread.start()

    # sync_thread.join()
    address_thread.join()

    # update_addresses_shopware()
    # sync_inventree()

    logging.info("Adressen Update abgeschlossen")


def update_addresses_shopware():
    load_dotenv()
    base_url = os.getenv("SHOPWARE_URL")

    limit = 100
    page = 1
    counter_addr = 0
    counter_customer = 0

    logging.info("Updating customer address db from Shopware")

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
                f"{base_url}/api/customer?limit={limit}&page={page}&associations[addresses][]",
                headers=auth_headers,
                timeout=10,  # 10 Sekunden Timeout
            )

            if response.status_code != 200:
                logging.error(
                    f"Fehler beim Abrufen der Shopware Kunden: {response.status_code}"
                )
                logging.error(f"Fehlerdetails: {response.text}")
                return

            customers_data = response.json()

            return customers_data["data"], customers_data["total"]

        except requests.exceptions.Timeout:
            logging.error("Timeout beim Abrufen der Shopware Kunden liste")
            return
        except requests.exceptions.RequestException as e:
            logging.error(f"Fehler beim Abrufen der Shopware Kunden: {e}")
            logging.error(f"Fehlerdetails: {str(e)}")
            return
        except Exception as e:
            logging.error(f"Error: {e}")
            return None

    conn, cursor = get_db()
    
    # Reset all updated flags
    cursor.execute("UPDATE addresses SET updated = 0")
    conn.commit()

    while True:
        customers_data, data_count = request(
            page, limit
        )  # Request a page of customer informations containing addresses

        if customers_data is None:
            break

        for customer in customers_data:  # For each customer in the page
            addresses = customer["addresses"]  # Extract the addresses of the customer

            cursor.execute(
                """
                           SELECT id FROM customers WHERE shopware_id = ?
                           """,
                (customer["id"],),
            )  # Check if the customer is already in the database

            customer_id = cursor.fetchone()[0]

            if customer_id is None:
                logging.warning(
                    f"Kunde {customer['id']} nicht in der Datenbank gefunden"
                )
                continue

            for address in addresses:  # For each address of the customer
                cursor.execute(
                    """
                    SELECT * FROM addresses WHERE shopware_id = ?
                    """,
                    (address["id"],),
                )

                address_exists = (
                    cursor.fetchone()
                )  # Check if the address is already in the database

                if (
                    address_exists is None
                ):  # When the address is not in the database, insert it
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
                                    street,
                                    updated
                                    ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            address["id"],
                            customer_id,
                            address["firstName"],
                            address["lastName"],
                            address["zipcode"],
                            address["city"],
                            address["street"],
                            True,  # Mark the address as updated
                        ),
                    )

                else:  # When the address is already in the database, mark as updated
                    cursor.execute(
                        """
                                   UPDATE addresses SET
                                   updated = ?
                                   WHERE shopware_id = ?
                                   """,
                        (True, address["id"]),
                    )

                counter_addr += 1

            counter_customer += 1

        conn.commit()

        if data_count < limit:
            break

        page += 1
    
    # Set all addresses that are not updated to not in shopware
    cursor.execute("""
        UPDATE addresses SET is_in_shopware = 0 
        WHERE updated = 0 OR updated IS NULL
    """)
    conn.commit()

    close_db(conn)
    logging.info(
        f"{counter_addr} Adressen von {counter_customer} Kunden erfolgreich aktualisiert"
    )


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

        if customer_id is None:
            logging.error(f"Kunde mit ID {address[1]} konnte nicht gefunden werden")
            continue

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

    logging.info(f"{counter} Adressen wurden hinzugefügt")
    close_db(conn)
