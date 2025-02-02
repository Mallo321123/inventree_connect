from dotenv import load_dotenv
import os
import requests
import datetime
import json
import time

from log_config import setup_logging
logging = setup_logging()

# Authenticates against Shopware and saves the token in a file
def shopware_auth():
    load_dotenv()

    base_url = os.getenv("SHOPWARE_URL")
    access_key = os.getenv("SHOPWARE_ACCESS_KEY")
    secret_key = os.getenv("SHOPWARE_SECRET_KEY")

    auth_data = {
        "grant_type": "client_credentials",
        "client_id": access_key,
        "client_secret": secret_key,
    }

    try:
        auth_response = requests.post(
            f"{base_url}/api/oauth/token",
            headers={"Content-Type": "application/json"},
            json=auth_data,
            timeout=10,  # 10 Sekunden Timeout
        )

        if auth_response.status_code != 200:
            logging.error(f"Error response body: {auth_response.text}")
            return None

        auth_response.raise_for_status()
        response = auth_response.json()
        
        auth_file = {
            "shopware_token": response["access_token"],
            "shopware_expires": (datetime.datetime.now() + datetime.timedelta(seconds=response["expires_in"])).timestamp(),
        }
        
        if not os.path.exists("auth.json"):
            with open("auth.json", "w") as f:
                json.dump(auth_file, f)
        else:
            # Read existing file
            with open("auth.json", "r") as f:
                existing_data = json.load(f)
            
            # Update only the fields from auth_file
            for key in auth_file:
                existing_data[key] = auth_file[key]
            
            # Write back the updated data
            with open("auth.json", "w") as f:
                json.dump(existing_data, f)

    except requests.exceptions.Timeout:
        logging.error("Request timed out after 10 seconds")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Authentication failed: {e}")
        logging.error(f"Error details: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

# Authenticates against Inventree and saves the token in a file
def inventree_auth():
    load_dotenv()

    base_url = os.getenv("INVENTREE_URL")
    username = os.getenv("INVENTREE_USER")
    password = os.getenv("INVENTREE_PASSWORD")

    try:
        auth_response = requests.get(
            f"{base_url}/api/user/token/",
            auth=(username, password),  # Basic Authentication
            timeout=10,  # 10 Sekunden Timeout
        )

        if auth_response.status_code != 200:
            logging.error(f"Error response body: {auth_response.text}")
            return None

        auth_response.raise_for_status()
        response = auth_response.json()

        auth_file = {
            "inventree_token": response["token"],
            "inventree_expires": response["expiry"],
        }

        if not os.path.exists("auth.json"):
            with open("auth.json", "w") as f:
                json.dump(auth_file, f)
        else:
            # Read existing file
            with open("auth.json", "r") as f:
                existing_data = json.load(f)

            # Update only the fields from auth_file
            for key in auth_file:
                existing_data[key] = auth_file[key]

            # Write back the updated data
            with open("auth.json", "w") as f:
                json.dump(existing_data, f)

    except requests.exceptions.Timeout:
        logging.error("Request timed out after 10 seconds")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Authentication failed: {e}")
        logging.error(f"Error details: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

# Checks if the shopware token is still valid
def check_shopware_token():
    if not os.path.exists("auth.json"):
        return False
    
    with open("auth.json", "r") as f:
        data = json.load(f)
    
    if "shopware_token" in data and "shopware_expires" in data:
        # Add 15 seconds buffer before expiration
        if data["shopware_expires"] > (datetime.datetime.now() + datetime.timedelta(seconds=25)).timestamp():
            return True
    
    return False

# Checks if the inventree token is still valid
def check_inventree_token():
    if not os.path.exists("auth.json"):
        return False
    
    with open("auth.json", "r") as f:
        data = json.load(f)
    
    if "inventree_token" in data and "inventree_expires" in data:
        expiry_date = datetime.datetime.strptime(data["inventree_expires"], "%Y-%m-%d")
        if expiry_date.timestamp() > datetime.datetime.now().timestamp():
            return True
    
    return False

def check_tokens():
    if not check_shopware_token():
        logging.info("Shopware token invalid, refreshing")
        shopware_auth()
        logging.info("Shopware token refreshed")
            
    if not check_inventree_token():
        logging.info("Inventree token invalid, refreshing")
        inventree_auth()
        logging.info("Inventree token refreshed")

# Checks all tokens every second if they are still valid
def auth_job():  
    logging.debug("Starting authentication job")  
    while True:        
        if not check_shopware_token():
            logging.info("Shopware token invalid, refreshing")
            shopware_auth()
            logging.info("Shopware token refreshed")
            
        if not check_inventree_token():
            logging.info("Inventree token invalid, refreshing")
            inventree_auth()
            logging.info("Inventree token refreshed")
            
        time.sleep(1)