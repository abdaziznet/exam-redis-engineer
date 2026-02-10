# Redis Enterprise API Configuration for Task 3
BASE_URL = "https://re-cluster1.ps-redislabs.org:9443"
USERNAME = "admin@rl.org"
PASSWORD = "9Ng2OSr"

HEADERS = {
    "Content-Type": "application/json"
}

# Redis Data Access - Connection Details
# These will be used for connecting to the Redis DB once created
REDIS_HOST = "172.16.22.23"
REDIS_PW = ""  # For simplicity, unauthenticated access is allowed
