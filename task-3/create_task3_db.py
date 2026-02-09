import json
import os
import sys
import time
import tempfile

import requests

from config import BASE_URL, USERNAME, PASSWORD, HEADERS

import urllib3

# Suppress warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Update headers to include Accept
HEADERS["Accept"] = "application/json"

auth = (USERNAME, PASSWORD)

TARGET_REDIS_VERSION = "7.4.0"
DB_NAME = "semantic-db"

def _parse_version(version_str: str):
    try:
        parts = [int(p) for p in version_str.split(".")]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])
    except Exception:
        return (0, 0, 0)

def _is_version_compatible(module_info, target_version: str):
    target = _parse_version(target_version)
    min_v = _parse_version(str(module_info.get("min_redis_version", "0.0.0")))
    max_v_raw = module_info.get("max_redis_version")
    if max_v_raw:
        max_v = _parse_version(str(max_v_raw))
        return min_v <= target <= max_v
    return min_v <= target

def check_available_modules():
    """Discover available modules on the cluster"""
    print("[Task 3] Checking available modules on cluster...")
    r = requests.get(f"{BASE_URL}/v1/modules", auth=auth, verify=False, timeout=30)
    if r.status_code == 200:
        return r.json()
    return []

def _fetch_redis_versions(url: str):
    r = requests.get(url, auth=auth, verify=False, timeout=30)
    if r.status_code == 200:
        return r.json()
    print(f"[Task 3][DEBUG] redis_versions endpoint {url} -> {r.status_code}: {r.text}")
    return None

def get_available_redis_versions():
    """Fetch available Redis versions from the cluster"""
    candidates = [
        f"{BASE_URL}/v1/redis_versions",
        f"{BASE_URL}/v1/redis-versions",
        f"{BASE_URL}/v1/redis/versions",
    ]
    for url in candidates:
        data = _fetch_redis_versions(url)
        if data is not None:
            return data
    return []

def _normalize_versions(available_versions):
    normalized = []
    if isinstance(available_versions, dict):
        # Common patterns: {"versions":[...]} or {"redis_versions":[...]}
        if "versions" in available_versions:
            available_versions = available_versions["versions"]
        elif "redis_versions" in available_versions:
            available_versions = available_versions["redis_versions"]
        else:
            available_versions = list(available_versions.values())

    for v in available_versions:
        if isinstance(v, str):
            normalized.append(v)
        elif isinstance(v, dict):
            if "version" in v:
                normalized.append(str(v["version"]))
            elif "name" in v:
                normalized.append(str(v["name"]))
        else:
            normalized.append(str(v))
    return normalized

def select_redis_version(available_versions, target_version: str):
    """Pick the best Redis version from the cluster list."""
    if not available_versions:
        return target_version

    # Normalize list to strings and prefer exact match
    versions = _normalize_versions(available_versions)
    # De-duplicate while preserving order
    versions = list(dict.fromkeys(versions))
    if target_version in versions:
        return target_version

    # Prefer matching major.minor (e.g., 7.4) if exact patch not available
    target_mm = ".".join(target_version.split(".")[:2])
    for v in versions:
        if v == target_mm:
            return v

    # Otherwise pick the highest version <= target_version
    target_tuple = _parse_version(target_version)
    parsed = [(v, _parse_version(v)) for v in versions]
    parsed.sort(key=lambda x: x[1], reverse=True)
    for v, t in parsed:
        if t <= target_tuple:
            return v

    # Fallback to the highest available
    return parsed[0][0]

def _build_candidate_versions(selected_version: str, target_version: str):
    candidates = []
    if selected_version:
        candidates.append(selected_version)
    if target_version and target_version not in candidates:
        candidates.append(target_version)
    if target_version:
        target_mm = ".".join(target_version.split(".")[:2])
        if target_mm and target_mm not in candidates:
            candidates.append(target_mm)
    # Final fallback: let the server choose default version
    candidates.append(None)
    return candidates

def create_search_db():
    """Create a single shard DB with Search and Query enabled"""
    modules = check_available_modules()
    available_versions = get_available_redis_versions()
    redis_version = select_redis_version(available_versions, TARGET_REDIS_VERSION)
    if redis_version != TARGET_REDIS_VERSION:
        print(f"[Task 3] Using Redis version {redis_version} from cluster (target was {TARGET_REDIS_VERSION})")
    else:
        print(f"[Task 3] Using Redis version {redis_version}")
    if available_versions:
        print(f"[Task 3] Cluster redis_versions: {available_versions}")
    
    # Logic to find the best Search module UID for Redis 7.4.0
    module_uid = None
    for m in modules:
        # Search for module named 'search' and compatible with 7.4.0
        if m.get("module_name") == "search" and _is_version_compatible(m, redis_version):
            module_uid = m.get("uid")
            print(f"[Task 3] Found Search Module compatible with {redis_version} (UID: {module_uid})")
            break
    
    # Fallback to any 'search' module if 7.4 specific not found
    if not module_uid:
        for m in modules:
            if m.get("module_name") == "search":
                module_uid = m.get("uid")
                break

    if not module_uid:
        raise Exception("Search module (RediSearch) not found in cluster modules list.")

    base_payload = {
        "name": DB_NAME,
        "type": "redis",
        "memory_size": 536870912,  # 512MB
        "shards_count": 1,
        "replication": False,
        "module_list": [
            {
                "module_name": "search",
                "module_uid": module_uid,
                "module_args": ""
            }
        ]
    }

    candidates = _build_candidate_versions(redis_version, TARGET_REDIS_VERSION)
    last_error = None
    for version in candidates:
        payload = dict(base_payload)
        if version:
            payload["redis_version"] = version
            print(f"[Task 3] Creating Database '{DB_NAME}' using Redis {version} and module 'search' (UID: {module_uid})...")
        else:
            print(f"[Task 3] Creating Database '{DB_NAME}' using server default Redis version and module 'search' (UID: {module_uid})...")
        r = requests.post(f"{BASE_URL}/v1/bdbs", json=payload, headers=HEADERS, auth=auth, verify=False, timeout=30)

        if r.status_code == 409:
            print("[Task 3] Database already exists. Fetching info...")
            r_list = requests.get(f"{BASE_URL}/v1/bdbs", auth=auth, verify=False, timeout=30)
            for db in r_list.json():
                if db["name"] == DB_NAME:
                    return db["uid"], db["port"]

        if r.status_code >= 400:
            print(f"[DEBUG] Error {r.status_code}: {r.text}")
            last_error = r
            # Try next candidate if invalid_version
            try:
                err = r.json()
            except Exception:
                err = {}
            if err.get("error_code") == "invalid_version":
                continue

        r.raise_for_status()
        db_info = r.json()
        return db_info["uid"], db_info.get("port", 0)

    if last_error is not None:
        last_error.raise_for_status()
    raise Exception("Failed to create DB with available Redis versions.")

def wait_and_get_port(db_uid):
    print(f"[Task 3] Waiting for DB {db_uid} to become active...")
    attempts = 0
    max_attempts = 60
    while True:
        r = requests.get(f"{BASE_URL}/v1/bdbs/{db_uid}", auth=auth, verify=False, timeout=30)
        data = r.json()
        if data.get("status") == "active":
            port = _extract_port_from_bdb(data)
            if port:
                print(f"[Task 3] DB is ACTIVE on port: {port}")
                return port
            print("[Task 3] DB is ACTIVE but port is 0, retrying...")
        attempts += 1
        if attempts >= max_attempts:
            print("[Task 3][WARN] Timed out waiting for port assignment.")
            return 0
        time.sleep(2)

def resolve_port_from_list(db_uid):
    r_list = requests.get(f"{BASE_URL}/v1/bdbs", auth=auth, verify=False, timeout=30)
    if r_list.status_code == 200:
        for db in r_list.json():
            if db.get("uid") == db_uid:
                return _extract_port_from_bdb(db)
    return 0

def _extract_port_from_bdb(bdb_info):
    # Common field
    port = bdb_info.get("port", 0)
    if port:
        return port
    # Some APIs use endpoints list
    endpoints = bdb_info.get("endpoints") or bdb_info.get("endpoint")
    if isinstance(endpoints, list):
        for ep in endpoints:
            p = ep.get("port") or ep.get("tcp_port") or ep.get("ssl_port")
            if p:
                return p
    if isinstance(endpoints, dict):
        p = endpoints.get("port") or endpoints.get("tcp_port") or endpoints.get("ssl_port")
        if p:
            return p
    # Another common field name
    p = bdb_info.get("proxy_port") or bdb_info.get("external_port")
    if p:
        return p
    return 0

def find_db_uid_by_name(db_name: str):
    r_list = requests.get(f"{BASE_URL}/v1/bdbs", auth=auth, verify=False, timeout=30)
    if r_list.status_code == 200:
        for db in r_list.json():
            if db.get("name") == db_name:
                return db.get("uid")
    return None

def delete_db_if_exists(db_name: str):
    uid = find_db_uid_by_name(db_name)
    if not uid:
        return
    print(f"[Task 3] Deleting existing DB '{db_name}' (UID: {uid})...")
    r = requests.delete(f"{BASE_URL}/v1/bdbs/{uid}", auth=auth, verify=False, timeout=30)
    if r.status_code >= 400:
        print(f"[DEBUG] Error {r.status_code}: {r.text}")
        r.raise_for_status()
    # Wait until deletion is reflected in list
    for _ in range(30):
        if not find_db_uid_by_name(db_name):
            print(f"[Task 3] DB '{db_name}' deleted.")
            return
        time.sleep(2)
    print(f"[Task 3][WARN] DB '{db_name}' delete not confirmed yet, proceeding anyway.")

if __name__ == "__main__":
    try:
        delete_db_if_exists(DB_NAME)
        uid, port = create_search_db()
        if port == 0:
            port = wait_and_get_port(uid)
        if port == 0:
            port = resolve_port_from_list(uid)
        
        # Save connection info for semantic_router.py
        db_info_path = os.path.join(os.path.dirname(__file__), "db_info.json")
        try:
            with open(db_info_path, "w") as f:
                json.dump({"port": port}, f)
            print(f"[Task 3] Saved DB info to {db_info_path}")
        except OSError as e:
            print(f"[Task 3][WARN] Failed to write {db_info_path}: {e}")
            # Fallback to temp folder
            temp_path = os.path.join(tempfile.gettempdir(), "db_info.json")
            try:
                with open(temp_path, "w") as f:
                    json.dump({"port": port}, f)
                print(f"[Task 3] Saved DB info to {temp_path}")
            except OSError as e2:
                print(f"[Task 3][WARN] Failed to write {temp_path}: {e2}")
                print(f"[Task 3][WARN] DB port is {port}. Update task-3/db_info.json manually if needed.")
            
    except Exception as e:
        print(f"Error: {e}")
