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

    order_count = 10    # Anzahl der Bestellungen, die rückläufig abgerufen werden sollen
    
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
        cursor.execute("""SELECT id FROM orders WHERE shopware_id = ?""", (order["id"],))
        
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
                try:
                    product_id = cursor.fetchone()[0]
                except TypeError:
                    logging.warning(f"Produkt {item['productId']} nicht in Datenbank gefunden")
                    continue
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

# Updates the status of the orders
def update_order_status():
    conn, cursor = get_db()
    
    cursor.execute("""SELECT inventree_id, shopware_id, inventree_state FROM orders WHERE state != 'Abgeschlossen'""")
    orders = cursor.fetchall()
    
    for order in orders:
        
        response = shopware_request("get", f"/api/order/{order[1]}", additions="associations[stateMachineState][]")
        
        state = response["stateMachineState"]["name"]
        
        response = inventree_request("get", f"/api/order/so/{order[0]}/")
        
        state_inventree = response["status_text"]
        
        if state == "In Bearbeitung" and state_inventree == "Pending":
            response = inventree_request("post", f"/api/order/so/{order[0]}/issue/")
            
            if response is not None:
                cursor.execute("""UPDATE orders SET inventree_state = 'In Progress' WHERE shopware_id = ?""", (order[1],))
                conn.commit()
                continue
            else:
                continue
        
        elif state == "offen":
            cursor.execute("""UPDATE orders SET inventree_state = 'Pending' WHERE shopware_id = ?""", (order[1],))
            continue
            
        elif state == "Abgeschlossen" and state_inventree == "In Progress":
            response = inventree_request("post", f"/api/order/so/{order[0]}/complete/")

            if response is not None:
                cursor.execute(
                    """UPDATE orders SET inventree_state = 'Complete' WHERE shopware_id = ?""",
                    (order[1],),
                )
                conn.commit()
                continue
            else:
                logging.warning(f"Bestellung {order[1]} wurde in Shopware als abgeschlossen markiert, konnte aber nicht in Inventree abgeschlossen werden, bitte manuell überprüfen")
                
        elif state == "Abgeschlossen" and state_inventree == "Pending":
            response = inventree_request("post", f"/api/order/so/{order[0]}/issue/")

            if response is not None:
                cursor.execute(
                    """UPDATE orders SET inventree_state = 'In Progress' WHERE shopware_id = ?""",
                    (order[1],),
                )
                conn.commit()
                response = inventree_request("post", f"/api/order/so/{order[0]}/complete/")
                
                if response is not None:
                    cursor.execute(
                        """UPDATE orders SET inventree_state = 'Complete' WHERE shopware_id = ?""",
                        (order[1],),
                    )
                    conn.commit()
                    continue
                else:
                    logging.warning(f"Bestellung {order[1]} wurde in Shopware als abgeschlossen markiert, konnte aber nicht in Inventree abgeschlossen werden, bitte manuell überprüfen")
            else:
                continue
        
        else:
            logging.error(f"Unerwartete Bestellstatus Kombination: Shopware: {state}, Inventree: {state_inventree}")
    
# Synchronizes the orders with Inventree
def sync_orders_inventree():
    conn, cursor = get_db()
    
    cursor.execute("""SELECT shopware_order_number, creation_date, customer_id, products, address_id, id FROM orders WHERE is_in_inventree = 0 OR is_in_inventree IS NULL""")
    
    orders = cursor.fetchall()
    
    counter = 0
    product_counter = 0
    
    for order in orders:
        
        creation_date = order[1].split("T")[0]
        
        try:
            cursor.execute(
                """SELECT inventree_id FROM customers WHERE id = ?""", (order[2],)
            )
            customer_id = cursor.fetchone()[0]
            if customer_id is None:
                raise TypeError
        except TypeError:
            logging.warning(f"Kunde {order[2]} ist noch nicht in Inventree")
            customer_id = create_customer_inventree(order[2])

            if customer_id is None:
                logging.error(
                    f"Kunde {order[2]} konnte nicht in Inventree erstellt werden"
                )
                continue
        
        try:
            cursor.execute("""SELECT inventree_id FROM addresses WHERE id = ?""", (order[4],))
            address_id = cursor.fetchone()[0] 
            if address_id is None:
                raise TypeError
        except TypeError:
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
        
        response = inventree_request("post", "/api/order/so/", data=data)
        
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
            
            response = inventree_request("post", "/api/order/so-line/", data=data)
            
            product_counter += 1
            
            stock = inventree_request("get", "/api/stock/", additions=f"available=true&part={inventree_product_id}")
            
            try:
                if stock is None:
                    logging.warning(f"Kein Lagerbestand für Produkt {inventree_product_id} gefunden")
                    continue
                
                if stock[0]["quantity"] < quantity:
                    logging.warning(f"Produkt {inventree_product_id} nicht genügend Lagerbestand")
                    continue
            except IndexError:
                logging.warning(f"Kein Lagerbestand für Produkt {inventree_product_id} gefunden")
                continue
            
            data = {
                0: {
                    "line_item": response["pk"],
                    "quantity": quantity,
                    "stock_item": stock[0]["pk"],
                }
            }
            response = inventree_request("POST", "/api/order/so-line/", data=data)
        
        counter += 1
    
    close_db(conn)
    logging.info(f"{counter} Bestellungen mit {product_counter} Produkten in Inventree synchronisiert")