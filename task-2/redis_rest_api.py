import time
import requests
from requests.auth import HTTPBasicAuth
from config import BASE_URL, USERNAME, PASSWORD, HEADERS

auth = HTTPBasicAuth(USERNAME, PASSWORD)

def create_database():
    payload = {
        "name": "exam-db",
        "type": "redis",
        "memory_size": 1024 * 1024 * 1024,
        "shards_count": 1,
        "replication": False
    }
    r = requests.post(f"{BASE_URL}/v1/bdbs", json=payload, headers=HEADERS, auth=auth,  verify=False)

    print("STATUS:", r.status_code)
    print("RESPONSE:", r.text)
    
    r.raise_for_status()
    return r.json()["uid"]


def create_new_user(email, name, role_uid):
    payload = {
        "email": email,
        "name": name,
        "password": "TempPass123!",
        "role_uids": [role_uid]
    }

    r = requests.post(
        f"{BASE_URL}/v1/users",
        json=payload,
        headers=HEADERS,
        auth=auth,
        verify=False
    )

    print(r.status_code, r.text)
    r.raise_for_status()

def list_users():
    r = requests.get(f"{BASE_URL}/v1/users", auth=auth, verify=False)
    for u in r.json():
        print(f"{u['name']} | {u['role_uids']} | {u['email']}")

def wait_db_ready(db_uid, timeout=60):
    print("Waiting DB to become active...")
    start = time.time()

    while time.time() - start < timeout:
        r = requests.get(
            f"{BASE_URL}/v1/bdbs/{db_uid}",
            auth=auth,
            verify=False
        )
        status = r.json()["status"]
        print("DB status:", status)

        if status == "active":
            return

        time.sleep(2)

    raise TimeoutError("Database not ready in time")

def create_role(db_uid, role_name, redis_acl):
    # Step 1: Dapatkan ACL UID (Default atau cari dari list)
    # Di Redis Enterprise 7.x, kita perlu UID dari ACL Rule.
    # Kita akan mencoba mencari ACL yang cocok atau menggunakan default '1' (All) atau '2' (Read-Only) jika tersedia.
    acl_uid = 1 # Default to All
    if "+@read -@write" in redis_acl:
        # Biasanya read-only rule ada di daftar, kita coba cari
        r_acls = requests.get(f"{BASE_URL}/v1/acl_rules", auth=auth, verify=False)
        if r_acls.status_code == 200:
            for rule in r_acls.json():
                if rule.get("rule") == redis_acl or "read" in rule.get("name", "").lower():
                    acl_uid = rule["uid"]
                    break
    
    # Step 1: Cek apakah role sudah ada (Idempotency)
    r_existing = requests.get(f"{BASE_URL}/v1/roles", auth=auth, verify=False)
    if r_existing.status_code == 200:
        for r_item in r_existing.json():
            if r_item["name"] == role_name:
                print(f"Role [{role_name}] already exists with UID {r_item['uid']}. Reusing...")
                return r_item["uid"]

    # Step 2: Buat role minimal jika belum ada
    payload = {
        "name": role_name,
        "management": "none"
    }
    
    r = requests.post(f"{BASE_URL}/v1/roles", json=payload, headers=HEADERS, auth=auth, verify=False)
    print(f"CREATE ROLE BASE [{role_name}]:", r.status_code)
    r.raise_for_status()
    role_uid = r.json()["uid"]

    # Step 3: Update Database (BDB)
    r_db = requests.get(f"{BASE_URL}/v1/bdbs/{db_uid}", auth=auth, verify=False)
    db_data = r_db.json()
    
    current_permissions = db_data.get("roles_permissions", [])
    current_permissions.append({
        "role_uid": role_uid,
        "redis_acl_uid": acl_uid  # Menggunakan UID sesuai permintaan error
    })

    update_payload = {
        "roles_permissions": current_permissions
    }

    print(f"LINKING ROLE {role_name} (ACL UID {acl_uid}) TO DB {db_uid}...")
    r_update = requests.put(
        f"{BASE_URL}/v1/bdbs/{db_uid}",
        json=update_payload,
        headers=HEADERS,
        auth=auth,
        verify=False
    )
    
    print(f"LINK ROLE STATUS:", r_update.status_code)
    if r_update.status_code >= 400:
        print("LINK ERROR:", r_update.text)
    
    r_update.raise_for_status()
    return role_uid


def delete_database(db_id):
    requests.delete(f"{BASE_URL}/v1/bdbs/{db_id}", auth=auth,  verify=False)

def check_api_schema():
    """Get role schema to see available fields"""
    r = requests.get(
        f"{BASE_URL}/v1/roles",
        auth=auth,
        verify=False
    )
    roles = r.json()
    print("Existing roles summary:", roles)
    
    # Check what fields are accepted
    r = requests.options(
        f"{BASE_URL}/v1/roles",
        auth=auth,
        verify=False
    )
    print("OPTIONS ROLES:", r.headers)


if __name__ == "__main__":

    check_api_schema()

    db_uid = create_database()

    wait_db_ready(db_uid, 60)

    # Create roles
    try:
        viewer_role = create_role(
            db_uid,
            "db_viewer",
            "+@read -@write"
        )

        member_role = create_role(
            db_uid,
            "db_member",
            "+@all"
        )
        
        # Create users
        create_new_user("john.doe@example.com", "John Doe", viewer_role)
        create_new_user("mike.smith@example.com", "Mike Smith", member_role)
        create_new_user("cary.johnson@example.com", "Cary Johnson", 1)

    except Exception as e:
        print(f"FAILED TO COMPLETE STEPS: {e}")

    list_users()
    #delete_database(db_uid)
