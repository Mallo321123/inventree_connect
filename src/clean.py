from db import get_db, close_db
from log_config import setup_logging
from request import inventree_request

logging = setup_logging()

def clean():
    conn, cursor = get_db()
    
    cursor.execute("""SELECT id, inventree_id FROM customers WHERE is_in_shopware = 0""")
    
    customers = cursor.fetchall()
    
    for customer in customers:
        logging.info(f"Deleting customer {customer[0]} from Inventree")
        if customer[1] is None:
            logging.warning(f"Customer {customer[0]} does not have an Inventree ID")
            cursor.execute(
                """DELETE FROM addresses WHERE customer_id = ?""", (customer[0],)
            )
            cursor.execute("""DELETE FROM customers WHERE id = ?""", (customer[0],))
            continue
        
        response = inventree_request("delete", f"/api/company/{customer[1]}/")
        response = "OK"
        
        if response is not None:
            cursor.execute("""DELETE FROM addresses WHERE customer_id = ?""", (customer[0],))
            cursor.execute("""DELETE FROM customers WHERE id = ?""", (customer[0],))
            conn.commit()
            logging.info(f"Deleted customer {customer[0]}")
        
        else:
            logging.error(f"Failed to delete customer {customer[0]} from Inventree")
            continue
        
    
    cursor.execute("""DELETE FROM addresses WHERE is_in_shopware = 0""")
    conn.commit()
    
    logging.info("Cleaned up customers and addresses")
