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
    payload = {
        "name": role_name,
        "management": "none",
        "roles_permissions": [
            {
                "database_uid": db_uid,
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
    print("Existing roles:", r.json())
    
    # Check what fields are accepted
    r = requests.options(
        f"{BASE_URL}/v1/roles",
        auth=auth,
        verify=False
    )
    print("OPTIONS:", r.headers)


if __name__ == "__main__":

    check_api_schema()

    db_uid = create_database()

    wait_db_ready(db_uid, 60)

    # Create roles
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

    list_users()
    delete_database(db_uid)
