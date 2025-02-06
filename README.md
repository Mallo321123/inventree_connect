# Configuraton

docker compose example File:

```
services:
  sync:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./logs:/app/logs
      - ./db:/app/db
    environment:
      - SLEEP_TIME=5 
      - SHOPWARE_URL=https://shop.url.com
      - INVENTREE_URL=https://inventree.url.com
      - SHOPWARE_ACCESS_KEY=Access_key
      - SHOPWARE_SECRET_KEY=Secret_key
      - INVENTREE_USER=shop
      - INVENTREE_PASSWORD=passwd123

```