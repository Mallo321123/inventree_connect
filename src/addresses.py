from request import shopware_request, inventree_request
from db import get_db, close_db
from log_config import setup_logging

logging = setup_logging()


def update_addresses():
    logging.info("Starte Adressen Update")

    update_addresses_shopware()  # Update the addresse from Shopware
    sync_inventree()  # Sync the addresses to Inventree

    logging.info("Adressen Update abgeschlossen")


# Updates the addresses from Shopware
def update_addresses_shopware():
    limit = 500
    page = 1
    counter_addr = 0
    counter_customer = 0

    logging.info("Updating customer address db from Shopware")

    conn, cursor = get_db()

    # Reset all updated flags
    cursor.execute("UPDATE addresses SET updated = 0")
    conn.commit()

    while True:
        customers_data, data_count = shopware_request(
            "get",
            "/api/customer",
            page=page,
            limit=limit,
            additions="associations[addresses][]",
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
                    SELECT id FROM addresses WHERE shopware_id = ?
                    """,
                    (address["id"],),
                )

                address_exists = (
                    cursor.fetchone()
                )  # Check if the address is already in the database

                data = {
                    "shopware_id": address["id"],
                    "is_in_shopware": 1,
                    "customer_id": customer_id,
                    "firstName": address["firstName"],
                    "lastName": address["lastName"],
                    "zipcode": address["zipcode"],
                    "city": address["city"],
                    "street": address["street"],
                    "updated": True,
                }

                if (
                    address_exists is None
                ):  # When the address is not in the database, insert it
                    create_address_db(data)

                else:  # When the address is already in the database, update it
                    data["id"] = address_exists[0]
                    update_address_db(data)

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


# Syncs the addresses to Inventree
def sync_inventree():
    conn, cursor = get_db()

    cursor.execute(
        "SELECT id FROM addresses WHERE (is_in_inventree = 0 OR inventree_id IS NULL) AND is_in_shopware = 1"
    )

    ids = cursor.fetchall()

    counter = 0

    for id in ids:
        address_id = create_address_inventree(id[0])

        if address_id is not None:
            counter += 1

    logging.info(f"{counter} Adressen wurden hinzugefügt")
    close_db(conn)


# Creates an address in the database with the given values
def create_address_db(data):
    conn, cursor = get_db()

    # Lists to store fields and values
    fields = []
    values = []

    # List of all possible fields
    possible_fields = [
        "inventree_id",
        "shopware_id",
        "is_in_inventree",
        "is_in_shopware",
        "customer_id",
        "firstName",
        "lastName",
        "zipcode",
        "city",
        "street",
        "updated",
    ]

    # Add only fields that exist in data
    for field in possible_fields:
        if field in data:
            fields.append(field)
            # Convert boolean fields
            if field in ["is_in_inventree", "is_in_shopware"]:
                values.append(bool(data[field]))
            else:
                values.append(data[field])

    if not fields:
        logging.warning("No fields provided for create_address_db")
        return None

    # Construct and execute query
    placeholders = ",".join(["?" for _ in fields])
    query = f"""
        INSERT INTO addresses ({",".join(fields)})
        VALUES ({placeholders})
        RETURNING id
    """

    cursor.execute(query, values)
    id = cursor.fetchone()[0]
    conn.commit()
    close_db(conn)

    return id


# Updates an address in the database with the given values
def update_address_db(data):
    if "id" not in data:
        logging.error("No id provided for update_address_db")
        return

    conn, cursor = get_db()

    # Build dynamic UPDATE query
    fields = []
    values = []

    # List of all possible fields
    possible_fields = [
        "inventree_id",
        "shopware_id",
        "is_in_inventree",
        "is_in_shopware",
        "customer_id",
        "firstName",
        "lastName",
        "zipcode",
        "city",
        "street",
        "updated",
    ]

    # Add only fields that exist in data
    for field in possible_fields:
        if field in data:
            fields.append(f"{field} = ?")
            # Convert boolean fields
            if field in ["is_in_inventree", "is_in_shopware"]:
                values.append(bool(data[field]))
            else:
                values.append(data[field])

    if not fields:
        logging.warning("No fields to update")
        return

    # Add id to values
    values.append(data["id"])

    # Construct and execute query
    query = f"UPDATE addresses SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(query, values)

    conn.commit()
    close_db(conn)


# Creates the address in Inventree with the given id
def create_address_inventree(id):
    conn, cursor = get_db()

    cursor.execute(
        """ SELECT id, customer_id, firstName, lastName, zipcode, city, street FROM addresses WHERE id = ?""",
        (id,),
    )  #
    address = cursor.fetchone()

    cursor.execute(
        """ SELECT inventree_id FROM customers WHERE id = ?""", (address[1],)
    )
    customer_id = cursor.fetchone()
    
    if customer_id is None:     # When the customer is not in Inventree, or does not exist
        cursor.execute("""SELECT id FROM customers WHERE id = ?""", (address[1],))

        customer = cursor.fetchone()

        if customer is None:
            logging.error(f"Kunde {address[1]} nicht in der Datenbank gefunden")
            
            cursor.execute("""DELETE FROM addresses WHERE customer_id = ?""", (address[1],))
            conn.commit()

        else:
            logging.warning(
                f"Kunde {customer[0]} Existiert nicht in Inventree, aber in der Datenbank"
            )

        return None

    if address[4] is None:
        postal_code = ""
    else:
        postal_code = address[4][:10]
    
    data = {
        "company": customer_id[0],
        "title": address[0],
        "line1": (address[2] + " " + address[3])[:50],
        "line2": address[6][:50],
        "postal_code": postal_code,
        "postal_city": address[5],
    }

    response = inventree_request("post", "/api/company/address/", data=data)

    try:
        address_id = response["pk"]
    except TypeError:
        return None
    
    try:
        cursor.execute(
            """
            UPDATE addresses SET is_in_inventree = 1, inventree_id = ? WHERE id = ?
            """,
            (address_id, id),
        )
    except Exception as e:
        logging.error(f"konnte nicht in Inventree erstellt werden: {e}")
        return None

    conn.commit()
    close_db(conn)

    return address_id
