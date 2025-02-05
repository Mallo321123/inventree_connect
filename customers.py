import requests
import json
import os
from dotenv import load_dotenv

from db import get_db, close_db

from log_config import setup_logging

logging = setup_logging()


def update_customers():
    logging.info("Updating customers in db")
    update_customers_shopware()

    sync_inventree()

    logging.info("Customers updated")


# Check if customers in db are still in Shopware, and update them if needed
def update_customers_shopware():
    load_dotenv()

    base_url = os.getenv("SHOPWARE_URL")

    limit = 500
    page = 1
    counter = 0
    counter_new = 0
    counter_updated = 0

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
        customers_data, data_count = request(page, limit)  # Request a page of customers

        if customers_data is None:
            break

        for customer in customers_data:  # For each customer in the page
            cursor.execute(
                """
                           SELECT * FROM customers WHERE shopware_id = ?
                           """,
                (customer["id"],),
            )  # Check if the customer is in the database

            result = cursor.fetchone()

            if result is None:
                cursor.execute(
                    """
                                 INSERT INTO customers (shopware_id, is_in_shopware, firstName, lastName, email, updated)
                                 VALUES (?, ?, ?, ?, ?, ?)
                                 """,
                    (
                        customer["id"],
                        True,
                        customer["firstName"],
                        customer["lastName"],
                        customer["email"],
                        True,
                    ),
                )
                counter_new += 1

            else:
                cursor.execute(
                    """
                               UPDATE customers SET is_in_shopware = ?, updated = ?, firstName = ?, lastName = ?, email = ?
                               WHERE shopware_id = ?
                               """,
                    (
                        True,
                        True,
                        customer["firstName"],
                        customer["lastName"],
                        customer["email"],
                        customer["id"],
                    ),
                )
                counter_updated += 1

            counter += 1

        conn.commit()

        if data_count < limit:
            break

        page += 1

    # Set all customers that are not updated to not in shopware
    cursor.execute("""
        UPDATE customers SET is_in_shopware = 0 
        WHERE updated = 0 OR updated IS NULL
    """)
    conn.commit()

    logging.info(
        f"{counter} Kunden verarbeiten, {counter_new} neu, {counter_updated} aktualisiert"
    )
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


def create_customer_db(data):
    conn, cursor = get_db()

    cursor.execute(
        """
        INSERT INTO customers (inventree_id, shopware_id, is_in_inventree, is_in_shopware, firstName, lastName, email)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            data["inventree_id"],
            data["shopware_id"],
            bool(data["is_in_inventree"]),
            bool(data["is_in_shopware"]),
            data["firstName"],
            data["lastName"],
            data["email"],
        ),
    )

    id = cursor.fetchone()[0]
    conn.commit()
    close_db(conn)

    return id


def create_customer_inventree(id):
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
        """SELECT firstName, lastName, email FROM customers WHERE id = ?""", (id,)
    )
    customer = cursor.fetchone()

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
    try:
        customer_id = response["pk"]
    except TypeError:
        return None

    cursor.execute(
        "UPDATE customers SET inventree_id = ?, is_in_inventree = 1 WHERE id = ?",
        (customer_id, id),
    )

    conn.commit()
    close_db(conn)

    return customer_id