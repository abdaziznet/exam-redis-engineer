import time
import requests
import urllib3
from requests.auth import HTTPBasicAuth
from config import BASE_URL, USERNAME, PASSWORD, HEADERS

# Disable SSL warnings for cleaner output in exam environment
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

auth = HTTPBasicAuth(USERNAME, PASSWORD)

def create_database():
    """Create a new Redis database (BDB)"""
    payload = {
        "name": "exam-db",
        "type": "redis",
        "memory_size": 1024 * 1024 * 1024,  # 1GB
        "shards_count": 1,
        "replication": False
    }
    r = requests.post(f"{BASE_URL}/v1/bdbs", json=payload, headers=HEADERS, auth=auth, verify=False)
    
    print(f"[DB] Creating database 'exam-db'... Status: {r.status_code}")
    r.raise_for_status()
    return r.json()["uid"]

def wait_db_ready(db_uid, timeout=60):
    """Wait for the database to move from pending to active status"""
    print(f"[DB] Waiting for database {db_uid} to become active...")
    start = time.time()

    while time.time() - start < timeout:
        r = requests.get(f"{BASE_URL}/v1/bdbs/{db_uid}", auth=auth, verify=False)
        status = r.json()["status"]

        if status == "active":
            print(f"[DB] Database is now active.")
            return

        time.sleep(2)

    raise TimeoutError("Database not ready in time")

def create_role(db_uid, role_name, redis_acl):
    """
    Create a role and associate it with a specific database and ACL.
    In Redis Enterprise 7.4, permissions are managed via BDB roles_permissions.
    """
    # 1. Resolve ACL Rule UID from the cluster
    acl_uid = 1  # Default to 'Full Access' (all keys, all commands)
    
    # Try to find a matching ACL rule or a read-only one if requested
    r_acls = requests.get(f"{BASE_URL}/v1/acl_rules", auth=auth, verify=False)
    if r_acls.status_code == 200:
        for rule in r_acls.json():
            # Match by exact ACL string or specific keywords for role names
            if rule.get("rule") == redis_acl:
                acl_uid = rule["uid"]
                break
            elif "+@read" in redis_acl and "read" in rule.get("name", "").lower():
                acl_uid = rule["uid"]
                break

    # 2. Check if the Role already exists (Idempotency)
    role_uid = None
    r_existing = requests.get(f"{BASE_URL}/v1/roles", auth=auth, verify=False)
    if r_existing.status_code == 200:
        for r_item in r_existing.json():
            if r_item["name"] == role_name:
                role_uid = r_item["uid"]
                print(f"[Role] Reusing existing role '{role_name}' (UID: {role_uid})")
                break

    # 3. Create role if not exists
    if not role_uid:
        payload = {
            "name": role_name,
            "management": "none"
        }
        r = requests.post(f"{BASE_URL}/v1/roles", json=payload, headers=HEADERS, auth=auth, verify=False)
        print(f"[Role] Creating role '{role_name}'... Status: {r.status_code}")
        r.raise_for_status()
        role_uid = r.json()["uid"]

    # 4. Link Role to Database (BDB)
    r_db = requests.get(f"{BASE_URL}/v1/bdbs/{db_uid}", auth=auth, verify=False)
    db_data = r_db.json()
    
    current_permissions = db_data.get("roles_permissions", [])
    
    # Check if this role is already linked to avoid duplicates
    is_linked = any(p.get("role_uid") == role_uid for p in current_permissions)
    
    if not is_linked:
        current_permissions.append({
            "role_uid": role_uid,
            "redis_acl_uid": acl_uid
        })
        update_payload = {"roles_permissions": current_permissions}
        r_update = requests.put(f"{BASE_URL}/v1/bdbs/{db_uid}", json=update_payload, headers=HEADERS, auth=auth, verify=False)
        print(f"[Link] Linking role '{role_name}' to DB {db_uid}... Status: {r_update.status_code}")
        r_update.raise_for_status()
    else:
        print(f"[Link] Role '{role_name}' already linked to DB {db_uid}")

    return role_uid

def create_new_user(email, name, role_uid):
    """Create a new cluster user and assign a role"""
    payload = {
        "email": email,
        "name": name,
        "password": "TempPass123!",
        "role_uids": [role_uid]
    }

    r = requests.post(f"{BASE_URL}/v1/users", json=payload, headers=HEADERS, auth=auth, verify=False)
    print(f"[User] Creating user '{name}' ({email})... Status: {r.status_code}")
    r.raise_for_status()

def list_users():
    """List all current users in the cluster"""
    print("\n" + "="*50)
    print("CURRENT CLUSTER USERS")
    print("="*50)
    r = requests.get(f"{BASE_URL}/v1/users", auth=auth, verify=False)
    for u in r.json():
        print(f"Name: {u['name']:<15} | Roles: {str(u['role_uids']):<10} | Email: {u['email']}")
    print("="*50 + "\n")

def delete_database(db_id):
    """Delete the specified database"""
    print(f"[Clean] Deleting database {db_id}...")
    requests.delete(f"{BASE_URL}/v1/bdbs/{db_id}", auth=auth, verify=False)

if __name__ == "__main__":
    try:
        # 1. Database Creation
        db_uid = create_database()
        wait_db_ready(db_uid, 60)

        # 2. Role Creation & Linking
        viewer_role = create_role(db_uid, "db_viewer", "+@read -@write")
        member_role = create_role(db_uid, "db_member", "+@all")

        # 3. User Creation
        create_new_user("john.doe@example.com", "John Doe", viewer_role)
        create_new_user("mike.smith@example.com", "Mike Smith", member_role)
        create_new_user("cary.johnson@example.com", "Cary Johnson", 1)  # Admin role

        # 4. Results
        list_users()

        # 5. Cleanup (Commented as per request to keep the result visible)
        # delete_database(db_uid)
        print("Script execution completed successfully.")

    except Exception as e:
        print(f"\n[ERROR] Script failed: {e}")
