import requests
from dotenv import load_dotenv
import os
from typing import Optional, Any
from log_config import setup_logging
import json

logging = setup_logging()


def shopware_request(
    method: str,
    endpoint: str,
    data: Optional[tuple[Any, ...]] = None,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    additions: Optional[str] = None,
    timeout: Optional[int] = 10,
):
    load_dotenv()
    base_url = os.getenv("SHOPWARE_URL")

    try:
        with open("auth.json", "r") as f:
            auth_data = json.load(f)

        access_token = auth_data["shopware_token"]

        auth_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    except Exception as e:
        logging.error(f"Failed to load auth data: {e}")
        return None

    url_param = ""

    if page is not None and limit is not None:
        url_param = f"?page={page}&limit={limit}"

    if additions is not None:
        if url_param != "":
            url_param = f"{url_param}&{additions}"
        else:
            url_param = f"?{additions}"

    url = f"{base_url}{endpoint}{url_param}"

    try:
        if method == "get":
            if data is not None:
                response = requests.get(
                    url, headers=auth_headers, json=data, timeout=timeout
                )
            else:
                response = requests.get(url, headers=auth_headers, timeout=timeout)

        elif method == "post":
            if data is not None:
                response = requests.post(
                    url, headers=auth_headers, json=data, timeout=timeout
                )
            else:
                response = requests.post(url, headers=auth_headers, timeout=timeout)

        else:
            logging.error(f"Invalid method: {method}")
            return None

    except requests.exceptions.Timeout:
        logging.error("request timed out")
        return
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error: {e}")
        logging.error(f"Datails: {str(e)}")
        return
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

    if response.status_code != 200 and response.status_code != 201:
        logging.error(f"Request failed with status code {response.status_code}")
        logging.error(f"Details: {response.text}")
        return None

    response_data = response.json()

    try:
        return response_data["data"], response_data["total"]

    except KeyError:
        return response_data["data"]


def inventree_request(
    method: str,
    endpoint: str,
    data: Optional[tuple[Any, ...]] = None,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    additions: Optional[str] = None,
    timeout: Optional[int] = 10,
):
    load_dotenv()
    base_url = os.getenv("INVENTREE_URL")

    try:
        # Token bei jedem Request neu einlesen
        with open("auth.json", "r") as f:
            auth_data = json.load(f)

        access_token = auth_data["inventree_token"]

        auth_headers = {
            "Accept": "application/json",
            "Authorization": f"Token {access_token}",
            "Content-Type": "application/json",
        }

    except Exception as e:
        logging.error(f"Failed to load auth data: {e}")
        return None

    url_param = ""

    if page is not None and limit is not None:
        url_param = f"?page={page}&limit={limit}"

    if additions is not None:
        if url_param != "":
            url_param = f"{url_param}&{additions}"
        else:
            url_param = f"?{additions}"

    url = f"{base_url}{endpoint}{url_param}"

    try:
        if method == "get":
            if data is not None:
                response = requests.get(
                    url, headers=auth_headers, json=data, timeout=timeout
                )
            else:
                response = requests.get(url, headers=auth_headers, timeout=timeout)

        elif method == "post":
            if data is not None:
                response = requests.post(
                    url, headers=auth_headers, json=data, timeout=timeout
                )
            else:
                response = requests.post(url, headers=auth_headers, timeout=timeout)

        elif method == "delete":
            if data is not None:
                response = requests.delete(
                    url, headers=auth_headers, json=data, timeout=timeout
                )
            else:
                response = requests.delete(url, headers=auth_headers, timeout=timeout)

        else:
            logging.error(f"Invalid method: {method}")
            return None

    except requests.exceptions.Timeout:
        logging.error("request timed out")
        return
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error: {e}")
        logging.error(f"Datails: {str(e)}")
        return
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

    if response.status_code != 200 and response.status_code != 201 and response.status_code != 204:
        logging.error(f"Request failed with status code {response.status_code}")
        logging.error(f"Details: {response.text}")
        if data is not None:
            logging.error(f"Data: {data}")
        return None

    return response.json()
