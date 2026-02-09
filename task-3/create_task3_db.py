import requests
import json
import time
import sys
import os

from config import BASE_URL, USERNAME, PASSWORD, HEADERS

import urllib3

# Suppress warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Update headers to include Accept
HEADERS["Accept"] = "application/json"

auth = (USERNAME, PASSWORD)

def check_available_modules():
    """Discover available modules on the cluster"""
    print("[Task 3] Checking available modules on cluster...")
    r = requests.get(f"{BASE_URL}/v1/modules", auth=auth, verify=False)
    if r.status_code == 200:
        modules = r.json()
        print(f"DEBUG Modules Response: {modules}")
        try:
            # Try different possible key names or formats
            if isinstance(modules, list):
                return [m.get('module_name') or m.get('name') for m in modules if (m.get('module_name') or m.get('name'))]
            return []
        except Exception as e:
            print(f"Parsing error: {e}")
            return []
    else:
        print(f"[Task 3] Could not fetch modules: {r.status_code} - {r.text}")
        return []

def create_search_db():
    """Create a single shard DB with Search and Query enabled"""
    available = check_available_modules()
    
    # RediSearch could be named 'search' or 'RediSearch'
    module_name = "search"
    if "RediSearch" in available:
        module_name = "RediSearch"
    elif "search" not in available and available:
        # If 'search' is not found, use the first one that looks like search
        for m in available:
            if "search" in m.lower():
                module_name = m
                break

    payload = {
        "name": "semantic-db",
        "type": "redis",
        "memory_size": 536870912,  # 512MB
        "shards_count": 1,
        "replication": False,
        "module_list": [
            {"name": module_name}
        ]
    }
    
    print(f"[Task 3] Creating Database 'semantic-db' using module '{module_name}'...")
    r = requests.post(f"{BASE_URL}/v1/bdbs", json=payload, headers=HEADERS, auth=auth, verify=False)
    
    if r.status_code >= 400:
        print(f"[DEBUG] Error {r.status_code}: {r.text}")
    
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
