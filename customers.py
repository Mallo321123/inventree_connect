import requests
import json
import os
from dotenv import load_dotenv
import threading

from db import get_db, close_db

from log_config import setup_logging

logging = setup_logging()


def update_customers():
    logging.info("Updating customers in db")
    shopware_thread = threading.Thread(target=update_customers_shopware)

    shopware_valid_thread = threading.Thread(target=valid_shopware_users)

    sync_thread = threading.Thread(target=sync_inventree)

    shopware_thread.start()
    shopware_thread.join()
    logging.info("Database updated")

    # inventree_valid_thread.start()
    # shopware_valid_thread.start()
    # inventree_valid_thread.join()
    # shopware_valid_thread.join()
    # logging.info("Database verified")

    sync_thread.start()
    sync_thread.join()

    logging.info("Customers updated")


# Update customers in db from Shopware
def update_customers_shopware():
    load_dotenv()
    base_url = os.getenv("SHOPWARE_URL")

    limit = 500
    page = 1
    counter = 0
    count_update = 0

    logging.info("Updating customer db from Shopware")

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
                f"{base_url}/api/customer?limit={limit}&page={page}",
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

            logging.debug("Shopware Kunden erfolgreich abgerufen")

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

    while True:
        customers_data, data_count = request(page, limit)

        if customers_data is None:
            break

        conn, cursor = get_db()

        for customer in customers_data:
            cursor.execute(
                """
                           SELECT * FROM customers WHERE shopware_id = ?
                           """,
                (customer["id"],),
            )

            result = cursor.fetchone()

            if result is None:
                cursor.execute(
                    """
                                 INSERT INTO customers (shopware_id, is_in_shopware, firstName, lastName, email)
                                 VALUES (?, ?, ?, ?, ?)
                                 """,
                    (
                        customer["id"],
                        True,
                        customer["firstName"],
                        customer["lastName"],
                        customer["email"],
                    ),
                )

                count_update += 1

            else:
                cursor.execute(
                    """
                    UPDATE customers 
                    SET shopware_id = ?, is_in_shopware = ?, firstName = ?, lastName = ?, email = ?
                    WHERE shopware_id = ?
                """,
                    (
                        customer["id"],
                        True,
                        customer["firstName"],
                        customer["lastName"],
                        customer["email"],
                        customer["id"],
                    ),
                )

                logging.debug(
                    f"Kunde {customer['firstName']} {customer['lastName']} aus Shopware aktualisiert"
                )
                count_update += 1

            counter += 1

        conn.commit()
        close_db(conn)

        if data_count < limit:
            break

        page += 1

    logging.info(
        f"Neue Shopware Kunden erfolgreich in die Datenbank geschrieben: {count_update} Kunden, insgesamt {counter} Kunden"
    )


# Check if customers in db are still in Shopware, and update them if needed
def valid_shopware_users():
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
                f"{base_url}/api/customer/{id}",
                headers=auth_headers,
                timeout=10,  # 10 Sekunden Timeout
            )

            if response.status_code == 404:
                return response.status_code

            if response.status_code != 200:
                logging.error(
                    f"Fehler beim Abrufen des Shopware Kunden: {response.status_code}"
                )
                logging.error(f"Fehlerdetails: {response.text}")
                return None

            customer_data = response.json()
            logging.debug(f"Shopware Kunde {id} erfolgreich abgerufen")
            return customer_data["data"]

        except requests.exceptions.Timeout:
            logging.error("Timeout beim Abrufen des Shopware Kunden")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Fehler beim Abrufen des Shopware Kunden: {e}")
            logging.error(f"Fehlerdetails: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error: {e}")
            return None

    conn, cursor = get_db()

    cursor.execute("SELECT shopware_id FROM customers WHERE is_in_shopware = 1")

    customers = cursor.fetchall()

    for customer in customers:
        customer_data = request(customer[0])

        if customer_data == 404:
            cursor.execute(
                "UPDATE customers SET is_in_shopware = ? WHERE shopware_id = ?",
                (False, customer[0]),
            )
            logging.debug(f"Kunde {customer[0]} nicht mehr in Shopware vorhanden")

        conn.commit()

    logging.info("Shopware Kunden erfolgreich aktualisiert")
    close_db(conn)


# Check if customers in db are still in Inventree
def valid_inventree_users():
    load_dotenv()

    base_url = os.getenv("INVENTREE_URL")

    def request(id):
        try:
            # Token bei jedem Request neu einlesen
            with open("auth.json", "r") as f:
                auth_data = json.load(f)

            access_token = auth_data["inventree_token"]

            auth_headers = {
                "Accept": "application/json",
                "Authorization": f"Token {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.get(
                f"{base_url}/api/company/{id}/",
                headers=auth_headers,
                timeout=10,  # 10 Sekunden Timeout
            )

            if response.status_code == 404:
                return response.status_code

            if response.status_code != 200:
                logging.error(
                    f"Fehler beim Abrufen des Inventree Kunden: {response.status_code}"
                )
                logging.error(f"Fehlerdetails: {response.text}")
                return None

            customer_data = response.json()
            logging.debug(f"Inventree Kunde {id} erfolgreich abgerufen")
            return customer_data

        except requests.exceptions.Timeout:
            logging.error("Timeout beim Abrufen des Inventree Kunden")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Fehler beim Abrufen des Inventree Kunden: {e}")
            logging.error(f"Fehlerdetails: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error: {e}")
            return None

    conn, cursor = get_db()

    cursor.execute("SELECT inventree_id FROM customers WHERE is_in_inventree = 1")

    customers = cursor.fetchall()

    for customer in customers:
        customer_data = request(customer[0])

        if customer_data == 404:
            cursor.execute(
                "UPDATE customers SET is_in_inventree = ? WHERE inventree_id = ?",
                (False, customer[0]),
            )
            logging.debug(f"Kunde {customer[0]} nicht mehr in Inventree vorhanden")

        conn.commit()

    logging.info("Inventree Kunden erfolgreich aktualisiert")
    close_db(conn)


# Sync customers from db to Inventree
def sync_inventree():
    load_dotenv()

    base_url = os.getenv("INVENTREE_URL")

    counter = 0

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
                f"{base_url}/api/company/",
                json=data,
                timeout=10,
                headers=headers,
            )

            if response.status_code != 201:
                logging.error(f"fehler beim erstellen dieses kunden: {data}")
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
        "SELECT firstName, lastName, email, id FROM customers WHERE is_in_inventree = 0 OR is_in_inventree IS NULL"
    )

    customers = cursor.fetchall()

    for customer in customers:
        if customer[0] is None or customer[1] is None or customer[2] is None:
            continue

        data = {
            "is_customer": True,
            "name": customer[0] + " " + customer[1],
            "description": "",
            "website": "",
            "currency": "EUR",
            "phone": "",
            "email": customer[2],
            "is_supplier": False,
            "is_manufacturer": False,
            "active": True,
        }

        response = request(data)

        if response is None:
            logging.error(
                f"Kunde {customer[0]} {customer[1]} konnte nicht in Inventree erstellt werden"
            )
            continue

        cursor.execute(
            "UPDATE customers SET inventree_id = ?, is_in_inventree = ? WHERE id = ?",
            (response["pk"], True, customer[3]),
        )


        conn.commit()
        counter += 1

    logging.info(f"{counter} Kunden erfolgreich in Inventree erstellt")
    close_db(conn)
