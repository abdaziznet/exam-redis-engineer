#!/usr/bin/env python3
"""
Redis Professional Services Challenge - Exercise 1 (FIXED)
Author: Technical Challenge Candidate
Date: 2026-01-30

Task:
- Insert values 1-100 into source-db as INDIVIDUAL KEYS
- Read and print them in reverse order from replica-db

Fix: Using individual keys (num:1, num:2, ..., num:100) 
     instead of a single list to meet grading requirements
"""

import redis
import time
import sys

# Configuration
SOURCE_HOST = 'redis-12000.re-cluster1.ps-redislabs.org'
SOURCE_PORT = 12000
REPLICA_HOST = 'redis-13000.re-cluster1.ps-redislabs.org'
REPLICA_PORT = 13000

print("=" * 70)
print("Redis Challenge: Insert 1-100 as Individual Keys")
print("=" * 70)

# Step 1: Connect to source-db
print("\n[Step 1] Connecting to source-db...")
try:
    source_db = redis.Redis(
        host=SOURCE_HOST,
        port=SOURCE_PORT,
        decode_responses=True,
        socket_connect_timeout=5
    )
    source_db.ping()
    print(f"✓ Connected to source-db at {SOURCE_HOST}:{SOURCE_PORT}")
except Exception as e:
    print(f"✗ Failed to connect to source-db: {e}")
    sys.exit(1)

# Step 2: Connect to replica-db
print("\n[Step 2] Connecting to replica-db...")
try:
    replica_db = redis.Redis(
        host=REPLICA_HOST,
        port=REPLICA_PORT,
        decode_responses=True,
        socket_connect_timeout=5
    )
    replica_db.ping()
    print(f"✓ Connected to replica-db at {REPLICA_HOST}:{REPLICA_PORT}")
except Exception as e:
    print(f"✗ Failed to connect to replica-db: {e}")
    sys.exit(1)

# Step 3: Insert values 1-100 as INDIVIDUAL KEYS into source-db
print("\n[Step 3] Inserting values 1-100 as individual keys into source-db...")
print("Using key pattern: num:1, num:2, ..., num:100")

try:
    # Clear existing keys with num: pattern
    existing_keys = source_db.keys("num:*")
    if existing_keys:
        source_db.delete(*existing_keys)
        print(f"Cleared {len(existing_keys)} existing keys")
    
    # Insert values 1-100 as individual keys
    inserted_count = 0
    for i in range(1, 101):
        key = f"num:{i}"
        source_db.set(key, i)
        inserted_count += 1
        
        if i % 20 == 0:
            print(f"  Inserted up to num:{i}...")
    
    # Verify insertion
    final_count = len(source_db.keys("num:*"))
    print(f"\n✓ Successfully inserted {inserted_count} individual keys")
    print(f"✓ Verification: {final_count} keys exist in source-db")
    
    if final_count != 100:
        print(f"⚠ Warning: Expected 100 keys, but found {final_count}")
        
except Exception as e:
    print(f"✗ Error inserting data: {e}")
    sys.exit(1)

# Step 4: Wait for replication
print("\n[Step 4] Waiting for replication to replica-db...")
max_wait = 30  # seconds
waited = 0

while waited < max_wait:
    try:
        replica_count = len(replica_db.keys("num:*"))
        if replica_count == 100:
            print(f"✓ Replication complete: {replica_count} keys replicated")
            break
        print(f"   Waiting... (replica has {replica_count}/100 keys)")
        time.sleep(2)
        waited += 2
    except:
        time.sleep(2)
        waited += 2

if waited >= max_wait:
    replica_count = len(replica_db.keys("num:*"))
    print(f"⚠ Replication status: {replica_count}/100 keys, continuing...")

# Step 5: Read values in REVERSE order from replica-db
print("\n[Step 5] Reading values in reverse order from replica-db...")

try:
    # Get all num:* keys from replica
    keys = replica_db.keys("num:*")
    
    if not keys:
        print("✗ No data found in replica-db")
        sys.exit(1)
    
    # Extract numbers from keys and sort
    # keys format: ['num:1', 'num:2', ..., 'num:100']
    numbers = []
    for key in keys:
        num = int(key.split(':')[1])
        value = replica_db.get(key)
        numbers.append((num, value))
    
    # Sort by number
    numbers.sort(key=lambda x: x[0])
    
    # Reverse to get descending order
    numbers.reverse()
    
    print(f"✓ Successfully read {len(numbers)} keys from replica-db")
    print("\n" + "=" * 70)
    print("VALUES IN REVERSE ORDER (100 down to 1):")
    print("=" * 70)
    
    # Print all values in reverse order
    # Format: 10 values per line for readability
    values_only = [v for _, v in numbers]
    
    for i in range(0, len(values_only), 10):
        line_values = values_only[i:i+10]
        print(" ".join(f"{v:>3}" for v in line_values))
    
    print("=" * 70)
    print(f"\n✓ Challenge completed successfully!")
    print(f"   - Inserted: 100 individual keys into source-db")
    print(f"   - Read: {len(numbers)} keys from replica-db in reverse order")
    print("=" * 70)
    
    # Show database statistics
    print("\n--- Final Statistics ---")
    source_total_keys = source_db.dbsize()
    replica_total_keys = replica_db.dbsize()
    print(f"Source DB total keys: {source_total_keys}")
    print(f"Replica DB total keys: {replica_total_keys}")
    print(f"Keys with 'num:*' pattern in source: {len(source_db.keys('num:*'))}")
    print(f"Keys with 'num:*' pattern in replica: {len(replica_db.keys('num:*'))}")
    
except Exception as e:
    print(f"✗ Error reading data from replica-db: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
