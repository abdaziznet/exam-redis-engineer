Redis Professional Services Consultant Technical Challenge

A little bit about this environment:
![A little bit about this environment](image.png)

Overview
This repository contains solutions for three exercises:
- Exercise 1: Redis database replication + data verification
- Exercise 2: Redis Enterprise REST API automation
- Exercise 3: Semantic routing app

Environment Notes
- Redis Enterprise nodes: re-n1, re-n2, re-n3
- Web UI credentials: admin@rl.org / 9Ng2OSr
- Bastion access: term / 9Ng2OSr, then `su` and `su labuser`
- Load node for memtier: `ssh load`
- Use IP address if hostnames do not resolve

Exercise 1: Building and Synchronizing Redis Databases

Goal
Create `source-db` and `replica-db`, load data, and verify replication by reading values in reverse from replica.

Step 1: Create source-db
- Single shard
- No password
- Memory limit: 2GB
- Name: `source-db`

Step 2: Create replica-db
- Single shard
- No password
- Memory limit: 2GB
- Name: `replica-db`
- Replica Of: `source-db`

Step 3: Load data with memtier-benchmark (on load node)
Run on the load node, then store the command used to `/tmp/memtier_benchmark.txt`.

Example command:
```bash
/opt/redislabs/bin/memtier_benchmark \
  -s re-n1 \
  -p 12000 \
  --protocol=redis \
  --key-pattern=R:R \
  --data-size=128 \
  --ratio=1:1 \
  --threads=2 \
  --clients=10 \
  --requests=10000
```

Save the command you executed:
```bash
cat > /tmp/memtier_benchmark.txt << 'EOF'
/opt/redislabs/bin/memtier_benchmark \
  -s re-n1 \
  -p 12000 \
  --protocol=redis \
  --key-pattern=R:R \
  --data-size=128 \
  --ratio=1:1 \
  --threads=2 \
  --clients=10 \
  --requests=10000
EOF
```

Step 4: Insert 1-100 and read reverse from replica
Use `task-1/task1.py` (LIST-based implementation).

```bash
python task-1/task1.py
```

Exercise 1: Data Structure Discussion
Possible Redis structures for values 1-100:
- List (LPUSH/RPUSH + LRANGE): preserves order, easy reverse on client
- Sorted Set (ZADD + ZREVRANGE): natural reverse order using score
- String keys (num:1 ... num:100): simple to insert, reverse ordering done by sorting keys

Chosen approach in `task-1/task1.py`: List. It preserves insertion order and is the most direct fit for sequential values and reverse reads.

Exercise 2: Working with Redis REST API

Goal
Create a database, create roles and users, list users, then delete the database.

Files
- `task-2/config.py`: API endpoint and credentials
- `task-2/redis_rest_api.py`: automation script

Run
```bash
python task-2/redis_rest_api.py
```

Notes
- The script creates `exam-db`, creates roles, creates three users, lists users, and can delete the DB.
- SSL verification is disabled for lab usage.
- Ensure the endpoint in `task-2/config.py` is correct.

Exercise 3: Working with Semantic Routers

Goal
Route input to one of three semantic routes:
- GenAI programming topics
- Science fiction entertainment
- Classical music

Files
- `task-3/semantic_router.py`
- `task-3/requirements.txt`

Steps
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r task-3/requirements.txt
python task-3/semantic_router.py
```

Troubleshooting
- If hostnames fail, use the database IP address from the UI.
- If replication seems slow, add a small delay before reading from replica.
- Ensure DB ports match the ones used in your scripts.
