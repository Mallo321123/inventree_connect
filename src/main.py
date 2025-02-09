import threading
import os

#from dotenv import load_dotenv

from auth import auth_job, check_tokens
from db import create_tables
from customers import update_customers
from addresses import update_addresses
from log_config import setup_logging
from orders import update_orders
from products import update_products
from clean import clean
import time

logging = setup_logging()
#load_dotenv()

if os.path.exists("db/database.db"):
    logging.info("Database file found")
else:
    create_tables()
    logging.info("Database file created")

check_tokens()

auth_thread = threading.Thread(target=auth_job)
auth_thread.start()

update_customers()
update_addresses()
update_products()

while True:
    check_tokens()
    
    try:
        update_orders()      # This function is not threaded because it depends on the customers and addresses tables
    except Exception as e:
        logging.error(f"Error updating orders: {e}")
        
    #try:
    #    clean()
    #except Exception as e:
    #    logging.error(f"Error cleaning database: {e}")
    
    time.sleep(int(os.getenv("SLEEP_TIME", 60)))