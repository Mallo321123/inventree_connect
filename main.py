import threading
import os


from auth import auth_job, check_tokens
from db import create_tables
from customers import update_customers
from addresses import update_addresses
from log_config import setup_logging

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
    
    customers_thread = threading.Thread(target=update_customers)
    address_thread = threading.Thread(target=update_addresses)
    
    #customers_thread.start()
    address_thread.start()