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
    # Step A: Coba buat role "kosong" dulu untuk melihat schema asli
    test_payload = {
        "name": role_name + "_test",
        "management": "none"
    }
    
    print(f"DEBUG: Probing schema with minimal payload...")
    r_test = requests.post(f"{BASE_URL}/v1/roles", json=test_payload, headers=HEADERS, auth=auth, verify=False)
    
    if r_test.status_code < 300:
        uid = r_test.json()["uid"]
        # Ambil detail role kosong ini untuk melihat field yang tersedia
        r_schema = requests.get(f"{BASE_URL}/v1/roles/{uid}", auth=auth, verify=False)
        print(f"DETECTED SCHEMA for Role {role_name}:", r_schema.text)
        # Hapus role test setelah inspeksi
        requests.delete(f"{BASE_URL}/v1/roles/{uid}", auth=auth, verify=False)

    # Step B: Gunakan struktur yang kita duga paling mungkin untuk 7.4: 'acl_rules' atau 'databases'
    # Berdasarkan pengalaman 7.4, terkadang field-nya adalah 'acl_rules'
    payload = {
        "name": role_name,
        "management": "none",
        "acl_rules": [
            {
                "bdb_uid": db_uid,
                "redis_acl": redis_acl
            }
        ]
    }

    r = requests.post(
        f"{BASE_URL}/v1/roles",
        json=payload,
        headers=HEADERS,
        auth=auth,
        verify=False
    )

    print(f"CREATE ROLE [{role_name}]:", r.status_code)
    if r.status_code >= 400:
        print("ERROR:", r.text)
        # Jika 'acl_rules' gagal, coba 'databases' dengan struktur UID
        print("Trying alternative: 'databases' with 'uid'...")
        alt_payload = {
            "name": role_name,
            "management": "none",
            "databases": [{"uid": db_uid, "redis_acl": redis_acl}]
        }
        r = requests.post(f"{BASE_URL}/v1/roles", json=alt_payload, headers=HEADERS, auth=auth, verify=False)
        print(f"RETRY ROLE [{role_name}]:", r.status_code)
        if r.status_code >= 400:
            print("ERROR RETRY:", r.text)

    r.raise_for_status()
    return r.json()["uid"]


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
    
    if roles:
        # Get details of the first role to see the schema
        detail = requests.get(
            f"{BASE_URL}/v1/roles/{roles[0]['uid']}",
            auth=auth,
            verify=False
        )
        print(f"Role {roles[0]['uid']} Detail Schema:", detail.text)
    
    # Check acl_roles endpoint
    r = requests.get(
        f"{BASE_URL}/v1/acl_roles",
        auth=auth,
        verify=False
    )
    print("ACL Roles Response Status:", r.status_code)
    if r.status_code == 200:
        print("ACL Roles:", r.json())
    
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
