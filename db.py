import sqlite3

from log_config import setup_logging
logging = setup_logging()

# Function to get the database connection/cursor
def get_db():
    conn = sqlite3.connect("database.db")
    return conn, conn.cursor()

# Function to close the database connection
def close_db(conn):
    conn.close()
    
# Function to create the database tables
def create_tables():
    logging.info("Creating database tables")
    conn, cursor = get_db()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventree_id TEXT,
            shopware_id TEXT,
            is_in_inventree BOOLEAN,
            is_in_shopware BOOLEAN,
            firstName TEXT,
            lastName TEXT,
            email TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventree_id TEXT,
            shopware_id TEXT,
            is_in_inventree BOOLEAN,
            is_in_shopware BOOLEAN,
            shopware_order_number TEXT,
            inventree_order_number TEXT,
            creation_date TEXT,
            shipping_date TEXT,
            customer_id INTEGER,
            paid BOOLEAN,
            shipped BOOLEAN,
            shippment_number TEXT,
            state TEXT,
            products TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventree_id TEXT,
            shopware_id TEXT,
            is_in_inventree BOOLEAN,
            is_in_shopware BOOLEAN,
            name TEXT,
            description TEXT,
            active BOOLEAN
        )
    """)
    
    conn.commit()
    logging.info("Database tables created")
    close_db(conn)