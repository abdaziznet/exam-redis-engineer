import requests
from requests.auth import HTTPBasicAuth
from config import BASE_URL, USERNAME, PASSWORD, HEADERS

auth = HTTPBasicAuth(USERNAME, PASSWORD)

def create_database():
    payload = {
        "name": "exam-db",
        "memory_size": 1024,
        "shards_count": 1,
        "replication": False,
        "modules": []
    }
    r = requests.post(f"{BASE_URL}/v1/bdbs", json=payload, headers=HEADERS, auth=auth)
    r.raise_for_status()
    return r.json()["uid"]

def create_user(email, name, role):
    payload = {
        "email": email,
        "name": name,
        "role": role,
        "password": "TempPass123!"
    }
    requests.post(f"{BASE_URL}/v1/users", json=payload, headers=HEADERS, auth=auth)

def list_users():
    r = requests.get(f"{BASE_URL}/v1/users", auth=auth)
    for u in r.json():
        print(f"{u['name']} | {u['role']} | {u['email']}")

def delete_database(db_id):
    requests.delete(f"{BASE_URL}/v1/bdbs/{db_id}", auth=auth)

if __name__ == "__main__":
    db_id = create_database()

    create_user("john.doe@example.com", "John Doe", "db_viewer")
    create_user("mike.smith@example.com", "Mike Smith", "db_member")
    create_user("cary.johnson@example.com", "Cary Johnson", "admin")

    list_users()
    delete_database(db_id)
