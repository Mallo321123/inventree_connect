import threading
import os


from auth import auth_job, check_tokens
from db import create_tables
from customers import update_customers
from addresses import update_addresses
from log_config import setup_logging
from orders import update_orders
from products import update_products
from clean import clean

logging = setup_logging()


if __name__ == "__main__":
    if os.path.exists("database.db"):
        logging.info("Database file found")
    else:
        create_tables()
        logging.info("Database file created")

    check_tokens()

    auth_thread = threading.Thread(target=auth_job)
    auth_thread.start()
    
    #update_customers()
    #update_addresses()
    #update_products()
    #update_orders()     # This function is not threaded because it depends on the customers and addresses tables
    clean()