import json

from db import get_db, close_db
from customers import create_customer_db, create_customer_inventree
from log_config import setup_logging
from addresses import create_address_db, create_address_inventree

from request import shopware_request, inventree_request

logging = setup_logging()


def update_orders():
    logging.info("Starte Bestellungen Update")

    update_orders_shopware()
    sync_orders_inventree()
    update_order_status()

    logging.info("Bestellungen Update abgeschlossen")


# Adds Orders to the database
def update_orders_shopware():
    conn, cursor = get_db()

    order_count = 10  # Anzahl der Bestellungen, die rückläufig abgerufen werden sollen

    orders, orders_total = shopware_request(
        "get",
        "/api/order",
        page=1,
        limit=order_count,
        additions="sort=-orderDateTime&associations[addresses][]&associations[lineItems][]&associations[orderCustomer][]",
    )

    counter_new = 0
    product_counter = 0

    for order in orders:
        cursor.execute(
            """SELECT id FROM orders WHERE shopware_id = ?""", (order["id"],)
        )

        if cursor.fetchone() is None:  # When order is not in database
            try:
                cursor.execute(
                    """SELECT id FROM customers WHERE shopware_id = ?""",
                    (order["orderCustomer"]["id"],),
                )
                customer_id = cursor.fetchone()[0]

            except TypeError:
                logging.warning(
                    f"Kunde {order['orderCustomer']['id']} nicht in Datenbank gefunden"
                )
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

            try:
                cursor.execute(
                    """SELECT id FROM addresses WHERE shopware_id = ?""",
                    (order["addresses"][0]["id"],),
                )
                address_id = cursor.fetchone()[0]
            except TypeError:
                logging.warning(
                    f"Adresse {order['addresses'][0]['id']} nicht in Datenbank gefunden"
                )
                data = {
                    "shopware_id": order["addresses"][0]["id"],
                    "is_in_shopware": True,
                    "customer_id": customer_id,
                    "firstName": order["addresses"][0]["firstName"],
                    "lastName": order["addresses"][0]["lastName"],
                    "street": order["addresses"][0]["street"],
                    "zipcode": order["addresses"][0]["zipcode"],
                    "city": order["addresses"][0]["city"],
                }
                address_id = create_address_db(data)

            cursor.execute(
                """INSERT INTO orders (shopware_id, is_in_shopware, shopware_order_number, creation_date, customer_id, state, address_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    order["id"],
                    True,
                    order["orderNumber"],
                    order["orderDateTime"],
                    customer_id,
                    order["stateMachineState"]["name"],
                    address_id,
                ),
            )

            order_id = cursor.fetchone()[0]

            for item in order["lineItems"]:
                cursor.execute(
                    """SELECT id FROM products WHERE shopware_id = ?""",
                    (item["productId"],),
                )
                try:
                    product_id = cursor.fetchone()[0]
                except TypeError:
                    logging.warning(
                        f"Produkt {item['productId']} nicht in Datenbank gefunden"
                    )
                    continue

                cursor.execute(
                    """SELECT multiplicator, offset FROM modifier WHERE product_id = ?""",
                    (product_id,),
                )

                try:
                    modifier = cursor.fetchone()
                    item["quantity"] = item["quantity"] * modifier[0] + modifier[1]
                except TypeError:
                    pass

                cursor.execute(
                    """  SELECT p.id
                                    FROM overwrites o
                                    JOIN products p ON o.overwrite_with = p.id
                                    WHERE o.item = ?
                                    """,
                    (product_id,),
                )  # Check if product is overwritten

                try:
                    product_id = cursor.fetchone()[0]
                except TypeError:
                    pass

                cursor.execute(
                    """INSERT INTO order_position (product_id, order_id, count) VALUES (?, ?, ?)""",
                    (product_id, order_id, item["quantity"]),
                )

                product_counter += 1

            counter_new += 1

            conn.commit()

        else:
            continue
            # Todo: Update existing orders

    logging.info(
        f"{counter_new} neue Bestellungen hinzugefügt, insgesamt {orders_total} Bestellungen Verarbeitet"
    )


# Updates the status of the orders
def update_order_status():
    def interpret_state(state):  # Interpretes the state of an order into a number
        if state == "Pending" or state == "Offen":
            return 1
        elif state == "In Progress" or state == "In Bearbeitung":
            return 2
        elif state == "Complete" or state == "Abgeschlossen":
            return 3
        elif state == "Cancelled" or state == "Abgebrochen":
            return 4
        else:
            logging.error(f"Unerwarteter Bestellstatus: {state}")
            return None

    conn, cursor = get_db()

    cursor.execute(
        """SELECT inventree_id, shopware_id, inventree_state FROM orders WHERE state != 'Abgeschlossen'"""
    )
    orders = cursor.fetchall()

    for order in orders:
        response = shopware_request(
            "get",
            f"/api/order/{order[1]}",
            additions="associations[stateMachineState][]",
        )
        state_shopware = response["stateMachineState"]["name"]

        response = inventree_request("get", f"/api/order/so/{order[0]}/")
        state_inventree = response["status_text"]

        state_inventree = interpret_state(state_inventree)
        state_shopware = interpret_state(state_shopware)

        if state_shopware == state_inventree:
            continue
        elif state_shopware > state_inventree:
            if state_inventree == 1:
                response = inventree_request("post", f"/api/order/so/{order[0]}/issue/")

                if response is not None:
                    cursor.execute(
                        """UPDATE orders SET inventree_state = 'In Progress' WHERE shopware_id = ?""",
                        (order[1],),
                    )
                    conn.commit()
                    continue
                else:
                    continue

            elif state_inventree == 2:
                response = inventree_request(
                    "post", f"/api/order/so/{order[0]}/complete/"
                )

                if response is not None:
                    cursor.execute(
                        """UPDATE orders SET inventree_state = 'Complete' WHERE shopware_id = ?""",
                        (order[1],),
                    )
                    conn.commit()
                    continue
                else:
                    shipment_id = inventree_request("get", "/api/order/so/shipment/", additions=f"order={order[0]}", page=1, limit=10)
                    
                    try:
                        shipment_id = shipment_id["results"][0]["pk"]
                    except KeyError:
                        logging.error(f"Keine offene Lieferung für Bestellung {order[0]} gefunden")
                        continue
                    
                    response = inventree_request("post", f"/api/order/so/shipment/{shipment_id}/ship/")
                    
                    if response is not None:
                        cursor.execute(
                            """UPDATE orders SET inventree_state = 'Complete' WHERE shopware_id = ?""",
                            (order[1],),
                        )
                        conn.commit()
                        continue
                    else:
                        logging.error(f"Bestellung {order[0]} konnte nicht abgeschlossen werden, bitte manuell prüfen")
                        continue
            else:
                logging.error(
                    f"Unerwarteter Bestellstatus, Inventree: {state_inventree}"
                )
        else:
            logging.error(
                f"Unerwarteter Bestellstatus Kombination: Shopware: {state_shopware}, Inventree: {state_inventree}"
            )


# Synchronizes the orders with Inventree
def sync_orders_inventree():
    conn, cursor = get_db()

    # cursor.execute(
    #    """SELECT shopware_order_number, creation_date, customer_id, address_id, id FROM orders WHERE is_in_inventree = 0 OR is_in_inventree IS NULL"""
    # )
    # orders = cursor.fetchall()

    # Get all open orders, with the needed information from database
    cursor.execute("""  SELECT orders.shopware_order_number, orders.creation_date, customers.inventree_id, customers.id, addresses.inventree_id, addresses.id, orders.id,
                        (
                            SELECT json_group_array(
                                json_object('id', products.inventree_id, 'count', order_position.count)
                            )
                            FROM order_position
                            JOIN products ON order_position.product_id = products.id
                            WHERE order_position.order_id = orders.id
                        ) AS bestellpositionen
                        FROM orders
                        JOIN customers ON orders.customer_id = customers.id
                        JOIN addresses ON orders.address_id = addresses.id
                        WHERE orders.is_in_inventree = 0 OR orders.is_in_inventree IS NULL;
                   """)
    orders = cursor.fetchall()

    # 0: shopware_order_number
    # 1: creation_date
    # 2: customer_inventree_id
    # 3: customer_id
    # 4: address_inventree_id
    # 5: address_id
    # 6: order_id
    # 7: order positions as json
    #   0: inventree_product_id
    #   1: quantity

    counter = 0
    product_counter = 0

    for order in orders:
        creation_date = order[1].split("T")[0]

        if order[2] is None:  # If customer is not in Inventree
            logging.warning(f"Kunde {order[3]} ist noch nicht in Inventree")
            customer_id = create_customer_inventree(order[3])

            if customer_id is None:
                logging.error(
                    f"Kunde {order[3]} konnte nicht in Inventree erstellt werden"
                )
                continue
        else:
            customer_id = order[2]

        if order[4] is None:  # If address is not in Inventree
            logging.warning(f"Adresse {order[5]} ist noch nicht in Inventree")
            address_id = create_address_inventree(order[5])

            if address_id is None:
                logging.error(
                    f"Adresse {order[5]} konnte nicht in Inventree erstellt werden"
                )
                continue
        else:
            address_id = order[4]

        reference = f"SO-{''.join(filter(str.isdigit, order[0]))}"

        data = {
            "creation_date": creation_date,
            "customer_reference": order[0],
            "address": address_id,
            "customer": customer_id,
            "reference": reference,
            "order_currency": "EUR",
        }

        response = inventree_request(
            "post", "/api/order/so/", data=data
        )  # Create order in Inventree

        try:
            order_inventree_id = response["pk"]  # Get the order id from the response
        except TypeError:
            logging.error(
                f"Bestellung {order[0]} konnte nicht in Inventree erstellt werden"
            )
            continue

        if response is not None:
            cursor.execute(  # Update the order in the database
                """UPDATE orders SET is_in_inventree = 1, inventree_id = ? WHERE id = ?""",
                (order_inventree_id, order[6]),
            )
            conn.commit()
        else:
            continue

        products = json.loads(order[7])

        for product_item in products:  # Add the products to the order
            part = product_item["id"]
            quantity = product_item["count"]

            data = {
                "order": order_inventree_id,
                "part": part,
                "quantity": quantity,
                "sale_price_currency": "EUR",
            }

            response = inventree_request(
                "post", "/api/order/so-line/", data=data
            )  # Add product to order

            product_counter += 1
            
            order_items_id = inventree_request("get", "/api/order/so-line/", additions=f"order={order_inventree_id}", page=1, limit=100)
            
            try:
                order_items_id = order_items_id["results"][0]
            except KeyError:
                logging.warning(f"Keine Bestellpositionen für Bestellung {order_inventree_id} gefunden")
                continue
            
            order_item_id = None
            try:
                for item in order_items_id:
                    if item['part'] == part:
                        order_item_id = item['pk']
                        break
            except TypeError:
                order_item_id = order_items_id['pk']

            if order_item_id is None:
                logging.warning(f"Keine Bestellposition für Teil {part} gefunden")
                continue
            
            stock = inventree_request(
                "get",
                "/api/stock/",
                additions=f"available=true&part={part}",
            )  # Check if product is in stock

            try:
                if stock is None:
                    logging.warning(f"Kein Lagerbestand für Produkt {part} gefunden")
                    continue

                if stock[0]["quantity"] < quantity:
                    logging.warning(f"Produkt {part} nicht genügend Lagerbestand")
                    continue
            except IndexError:
                logging.warning(f"Kein Lagerbestand für Produkt {part} gefunden")
                continue

            shipment = inventree_request(
                "get",
                "/api/order/so/shipment/",
                additions=f"shiped=false&order={order_inventree_id}",
                page=1,
                limit=10,
            )  # Search for open shipment

            try:
                shipment_id = shipment["results"][0]["pk"]
            except KeyError:
                logging.error(
                    f"Keine offene Lieferung für Bestellung {order_inventree_id} gefunden, bitte manuell prüfen"
                )
                continue

            data = {
                "items": [
                    {
                        "line_item": order_item_id,
                        "quantity": quantity,
                        "stock_item": stock[0]["pk"],
                    }
                ],
                "shipment": shipment_id,
            }

            response = inventree_request(
                "post", f"/api/order/so/{order_inventree_id}/allocate/", data=data
            )  # Alocate stock to order

        counter += 1

    close_db(conn)
    logging.info(
        f"{counter} Bestellungen mit {product_counter} Produkten in Inventree synchronisiert"
    )
