# Introduction

This Project is made for syncing Orders from a Shopware Instance to a Inventree Instance.

# Configuraton

docker compose example File:

```
services:
  sync:
    image: ghcr.io/mallo321123/inventree_connect:latest
    volumes:
      - ./logs:/app/logs
      - ./db:/app/db
    environment:
      - SLEEP_TIME=240
      - SHOPWARE_URL=https://shop.url.com
      - INVENTREE_URL=https://inventree.url.com
      - SHOPWARE_ACCESS_KEY=Access_key
      - SHOPWARE_SECRET_KEY=Secret_key
      - INVENTREE_USER=shop
      - INVENTREE_PASSWORD=passwd123

```
