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
    # If DB with same name exists, delete it first (idempotent)
    r_existing = requests.get(f"{BASE_URL}/v1/bdbs", auth=auth, verify=False)
    if r_existing.status_code == 200:
        for db in r_existing.json():
            if db.get("name") == "exam-db":
                existing_uid = db.get("uid")
                print(f"[DB] Existing database 'exam-db' found (UID: {existing_uid}). Deleting...")
                requests.delete(f"{BASE_URL}/v1/bdbs/{existing_uid}", auth=auth, verify=False)
                # Wait until the DB is gone before recreating
                for _ in range(30):
                    r_check = requests.get(f"{BASE_URL}/v1/bdbs", auth=auth, verify=False)
                    if r_check.status_code == 200:
                        if not any(b.get("uid") == existing_uid for b in r_check.json()):
                            break
                    time.sleep(2)
                break

    payload = {
        "name": "exam-db",
        "type": "redis",
        "memory_size": 1024 * 1024 * 1024,
        "port": 14000,  # 1GB
        "shards_count": 1,
        "replication": False,
        "proxy_policy": "single"
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
                
                # Check and update management if needed
                if r_item.get("management") == "none":
                    # Try to update to db_member management
                    mgmt_level = "db_member" if "member" in role_name else "db_viewer"
                    update_payload = {"management": mgmt_level}
                    r_upd = requests.put(
                        f"{BASE_URL}/v1/roles/{role_uid}",
                        json=update_payload,
                        headers=HEADERS,
                        auth=auth,
                        verify=False
                    )
                    if r_upd.status_code == 200:
                        print(f"[Role] Updated management level to '{mgmt_level}'")
                
                break

    # 3. Create role if not exists
    if not role_uid:
        # Set management based on role name
        mgmt_level = "db_member" if "member" in role_name else "db_viewer"

        payload = {
            "name": role_name,
            "management": mgmt_level  # Change from "none" to specific level
        }
        r = requests.post(f"{BASE_URL}/v1/roles", json=payload, headers=HEADERS, auth=auth, verify=False)
        print(f"[Role] Creating role '{role_name}' with management '{mgmt_level}'... Status: {r.status_code}")
        if r.status_code != 200:
            try:
                print(f"[ERROR] Role creation failed: {r.json()}")
            except:
                print(f"[ERROR] Role creation raw: {r.text}")
        
        r.raise_for_status()
        role_uid = r.json()["uid"]

    # 4. Link Role to Database (BDB) with Retry Logic for 409 Conflicts
    max_retries = 3
    for attempt in range(max_retries):
        r_db = requests.get(f"{BASE_URL}/v1/bdbs/{db_uid}", auth=auth, verify=False)
        db_data = r_db.json()
        
        current_permissions = db_data.get("roles_permissions", [])
        
        # Check if this role is already linked
        is_linked = any(p.get("role_uid") == role_uid for p in current_permissions)
        
        if is_linked:
            print(f"[Link] Role '{role_name}' already linked to DB {db_uid}")
            break
            
        current_permissions.append({
            "role_uid": role_uid,
            "redis_acl_uid": acl_uid
        })
        
        update_payload = {"roles_permissions": current_permissions}
        r_update = requests.put(f"{BASE_URL}/v1/bdbs/{db_uid}", json=update_payload, headers=HEADERS, auth=auth, verify=False)
        
        if r_update.status_code == 409:
            print(f"[Link] DB is busy (409). Retrying in 5s... (Attempt {attempt + 1}/{max_retries})")
            time.sleep(5)
            continue
            
        print(f"[Link] Linking role '{role_name}' to DB {db_uid}... Status: {r_update.status_code}")
        r_update.raise_for_status()
        break
    else:
        raise Exception(f"Failed to link role {role_name} after {max_retries} attempts due to 409 Conflict.")

    return role_uid

def create_new_user(email, name, role_uid):
    """Create a new cluster user and assign a role"""
    # If user already exists, delete it before re-creating
    r_existing = requests.get(f"{BASE_URL}/v1/users", auth=auth, verify=False)
    if r_existing.status_code == 200:
        for u in r_existing.json():
            if u.get("email") == email:
                existing_uid = u.get("uid")
                print(f"[User] User '{name}' ({email}) exists (UID: {existing_uid}). Deleting...")
                requests.delete(f"{BASE_URL}/v1/users/{existing_uid}", auth=auth, verify=False)
                # Wait until the user is gone before recreating
                for _ in range(30):
                    r_check = requests.get(f"{BASE_URL}/v1/users", auth=auth, verify=False)
                    if r_check.status_code == 200:
                        if not any(x.get("uid") == existing_uid for x in r_check.json()):
                            break
                    time.sleep(2)
                break

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

def list_users_2():
    """List all current users in the cluster"""
    print("\n" + "="*50)
    print("CURRENT CLUSTER USERS")
    print("="*50)
    r = requests.get(f"{BASE_URL}/v1/users", auth=auth, verify=False)
    
    for u in r.json():
        print(f"\n[DEBUG] Full user object for {u['email']}:")
        print(f"  {u}")  # Print full object to see all fields
        print(f"Name: {u['name']:<15} | Role UIDs: {str(u['role_uids']):<10} | Email: {u['email']}")
    print("="*50 + "\n")

# Tambahkan ini di awal script untuk debugging
def check_existing_databases():
    """Check what databases already exist"""
    r = requests.get(f"{BASE_URL}/v1/bdbs", auth=auth, verify=False)
    print(f"[Debug] Existing databases:")
    print(r.json())
    

def list_all_roles():
    """Debug: List all available roles in the cluster"""
    print("\n[DEBUG] All available roles:")
    r = requests.get(f"{BASE_URL}/v1/roles", auth=auth, verify=False)
    if r.status_code == 200:
        for role in r.json():
            print(f"  UID: {role['uid']}, Name: {role['name']}, Management: {role.get('management', 'N/A')}")
    print()

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
        list_users_2()

        # 5. Cleanup (Commented as per request to keep the result visible)
        # delete_database(db_uid)
        print("Script execution completed successfully.")

    except Exception as e:
        print(f"\n[ERROR] Script failed: {e}")
