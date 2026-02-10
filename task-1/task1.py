import redis

# Connect to databases
source = redis.Redis(host='172.16.22.21', port=12000, decode_responses=True)
replica = redis.Redis(host='172.16.22.22', port=13000, decode_responses=True)

# Insert values 1-100 into source-db
print("Inserting values 1-100 into source-db...")
for i in range(1, 101):
    source.set(str(i), i)  # Atau gunakan f"key:{i}" sebagai key
    if i % 10 == 0:
        print(f"Inserted {i} keys...")

print("Insert completed!")

# Wait for replication (optional but recommended)
import time
time.sleep(2)

# Read and print in reverse order from replica-db
print("\nReading values in reverse order from replica-db:")
for i in range(100, 0, -1):
    value = replica.get(str(i))
    print(f"Key: {i}, Value: {value}")