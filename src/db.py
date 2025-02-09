import sqlite3

from log_config import setup_logging

logging = setup_logging()


# Function to get the database connection/cursor
def get_db():
    conn = sqlite3.connect("db/database.db")
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
            email TEXT,
            updated BOOLEAN);
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
        address_id INTEGER,
        inventree_state TEXT,
        CONSTRAINT orders_addresses_FK FOREIGN KEY (address_id) REFERENCES addresses(id) ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT orders_customers_FK FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE ON UPDATE CASCADE
    );
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
            active BOOLEAN,
            productNumber TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
	    id INTEGER PRIMARY KEY AUTOINCREMENT,
	    inventree_id TEXT,
        shopware_id TEXT,
        is_in_inventree BOOLEAN,
        is_in_shopware BOOLEAN,
        customer_id INTEGER,
        firstName TEXT,
        lastName TEXT,
        zipcode TEXT,
        city TEXT,
        street TEXT,
        updated BOOLEAN,
        CONSTRAINT addresses_customers_FK FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE ON UPDATE CASCADE
        );
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS "order_position" (
        id INTEGER NOT NULL,
        product_id INTEGER,
        order_id INTEGER,
        count INTEGER,
        CONSTRAINT bestellposition_pk PRIMARY KEY (id),
        CONSTRAINT bestellposition_products_FK FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT bestellposition_orders_FK FOREIGN KEY (order_id) REFERENCES orders(id)
        );
    """)

    conn.commit()
    logging.info("Database tables created")
    close_db(conn)
