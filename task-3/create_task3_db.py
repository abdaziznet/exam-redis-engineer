import requests
import json
import time
import sys
import os

from config import BASE_URL, USERNAME, PASSWORD, HEADERS

auth = (USERNAME, PASSWORD)

def create_search_db():
    """Create a single shard DB with Search and Query enabled"""
    payload = {
        "name": "semantic-db",
        "type": "redis",
        "memory_size": 1024 * 1024 * 512,  # 512MB is enough
        "shards_count": 1,
        "replication": False,
        "module_list": [
            {"name": "search"}  # CRITICAL: Enabling RediSearch
        ],
        "resp3": True
    }
    
    print("[Task 3] Creating Database 'semantic-db' with Search enabled...")
    r = requests.post(f"{BASE_URL}/v1/bdbs", json=payload, headers=HEADERS, auth=auth, verify=False)
    
    if r.status_code == 409:
        print("[Task 3] Database already exists. Fetching info...")
        r_list = requests.get(f"{BASE_URL}/v1/bdbs", auth=auth, verify=False)
        for db in r_list.json():
            if db['name'] == "semantic-db":
                return db['uid'], db['port']
                
    r.raise_for_status()
    db_info = r.json()
    return db_info["uid"], db_info.get("port", 0)

def wait_and_get_port(db_uid):
    print(f"[Task 3] Waiting for DB {db_uid} to become active...")
    while True:
        r = requests.get(f"{BASE_URL}/v1/bdbs/{db_uid}", auth=auth, verify=False)
        data = r.json()
        if data["status"] == "active":
            print(f"[Task 3] DB is ACTIVE on port: {data['port']}")
            return data["port"]
        time.sleep(2)

if __name__ == "__main__":
    try:
        uid, port = create_search_db()
        if port == 0:
            port = wait_and_get_port(uid)
        
        # Save connection info for semantic_router.py
        with open('db_info.json', 'w') as f:
            json.dump({"port": port}, f)
            
    except Exception as e:
        print(f"Error: {e}")
