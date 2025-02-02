from db import get_db, close_db
import os
from dotenv import load_dotenv
import json
import requests

def delete():
    load_dotenv()
    db, cursor = get_db()
    
    cursor.execute("SELECT inventree_id FROM customers WHERE is_in_inventree = 1")
    
    customers = cursor.fetchall()
    
    base_url = os.getenv("INVENTREE_URL")
    
    for customer in customers:
        with open("auth.json", "r") as f:
            auth_data = json.load(f)

        access_token = auth_data["inventree_token"]

        auth_headers = {
            "Accept": "application/json",
            "Authorization": f"Token {access_token}",
            "Content-Type": "application/json",
        }

        response = requests.delete(
            f"{base_url}/api/company/{customer[0]}/",
            headers=auth_headers,
            timeout=10,  # 10 Sekunden Timeout
        )
        
        cursor.execute("UPDATE customers SET is_in_inventree = ? WHERE inventree_id = ?", (False, customer[0]))
        
        print(f"Customer {customer[0]} deleted")
        
        db.commit()
        
    close_db(cursor)
    print("All customers deleted")