import redis
import time

SOURCE_DB = {
    "host": "172.16.22.21",
    "port": 12000,
    "decode_responses": True
}

REPLICA_DB = {
    "host": "172.16.22.22",
    "port": 13000,
    "decode_responses": True
}

def main():
    source = redis.Redis(**SOURCE_DB)
    replica = redis.Redis(**REPLICA_DB)

    key = "numbers"

    # Insert 1–100 using LIST
    source.delete(key)
    for i in range(1, 101):
        source.rpush(key, i)

    print("Inserted values 1-100 into source-db")

    # Wait for replication
    time.sleep(2)

    # Read from replica in reverse
    values = replica.lrange(key, 0, -1)
    reversed_values = list(reversed(values))

    print("Read from replica-db (reverse order):")
    for v in reversed_values:
        print(v)

if __name__ == "__main__":
    main()
