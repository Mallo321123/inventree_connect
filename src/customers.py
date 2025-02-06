from db import get_db, close_db
from request import inventree_request, shopware_request
from log_config import setup_logging

logging = setup_logging()


def update_customers():
    logging.info("Updating customers")
    
    update_customers_shopware()
    sync_inventree()

    logging.info("Customers updated")


# Check if customers in db are still in Shopware, and update them if needed
def update_customers_shopware():
    limit = 500
    page = 1
    counter = 0
    counter_new = 0
    counter_updated = 0

    logging.info("Updating customer db from Shopware")

    conn, cursor = get_db()

    # Reset all updated flags
    cursor.execute("UPDATE addresses SET updated = 0")
    conn.commit()

    while True:
        customers_data, data_count = shopware_request(
            "get", "/api/customer", page=page, limit=limit
        )  # Request a page of customers

        if customers_data is None:
            break

        for customer in customers_data:  # For each customer in the page
            cursor.execute(
                """
                           SELECT id FROM customers WHERE shopware_id = ?
                           """,
                (customer["id"],),
            )  # Check if the customer is in the database

            result = cursor.fetchone()

            data = {
                "shopware_id": customer["id"],
                "is_in_shopware": True,
                "firstName": customer["firstName"],
                "lastName": customer["lastName"],
                "email": customer["email"],
                "updated": True,
            }

            if result is None:
                id = create_customer_db(data)

                if id is None:
                    logging.error(f"Failed to create customer {customer['id']} in db")
                    continue

                counter_new += 1

            else:
                data["id"] = result[0]
                update_customer_db(data)
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
    counter = 0

    conn, cursor = get_db()

    cursor.execute(
        "SELECT id FROM customers WHERE (is_in_inventree = 0 OR is_in_inventree IS NULL) AND is_in_shopware = 1"
    )

    ids = cursor.fetchall()

    for id in ids:
        response = create_customer_inventree(id[0])
        
        if response is not None:
            counter += 1

    logging.info(f"{counter} Kunden erfolgreich in Inventree erstellt")
    close_db(conn)


# Create a new customer in the database
def create_customer_db(data):
    conn, cursor = get_db()

    original_lastName = data["lastName"]
    counter = 1

    # Check for existing combinations
    while True:
        cursor.execute("""
            SELECT id FROM customers 
            WHERE firstName = ? AND lastName = ? AND email = ?
        """, (data["firstName"], data["lastName"], data["email"]))
        
        if not cursor.fetchone():
            break
            
        data["lastName"] = f"{original_lastName} ({counter})"
        counter += 1

    # Lists to store fields and values
    fields = []
    values = []

    # List of all possible fields
    possible_fields = [
        "inventree_id",
        "shopware_id",
        "is_in_inventree",
        "is_in_shopware",
        "firstName", 
        "lastName",
        "email",
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
        logging.warning("No fields provided for create_customer_db")
        return None

    # Construct and execute query
    placeholders = ",".join(["?" for _ in fields])
    query = f"""
        INSERT INTO customers ({",".join(fields)})
        VALUES ({placeholders})
        RETURNING id
    """

    cursor.execute(query, values)
    id = cursor.fetchone()[0]
    conn.commit()
    close_db(conn)

    return id


# Update a customer in the database
def update_customer_db(data):
    if "id" not in data:
        logging.error("No id provided for update_customer_db")
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
        "firstName",
        "lastName",
        "email",
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
    query = f"UPDATE customers SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(query, values)

    conn.commit()
    close_db(conn)


# creates a customer in Inventree with the given id
def create_customer_inventree(id):
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

    response = inventree_request("post", "/api/company/", data=data)
    
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
