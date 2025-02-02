import threading
import os
import time


from auth import auth_job, check_tokens
from db import create_tables
from customers import update_customers
from log_config import setup_logging
logging = setup_logging()

#from test import delete


if __name__ == "__main__":
    if os.path.exists("database.db"):
        logging.info("Database file found")
    else:
        create_tables()
        logging.info("Database file created")
        
    check_tokens()
    
    auth_thread = threading.Thread(target=auth_job)
    auth_thread.start()
    
    #delete()
    
    update_customers()
