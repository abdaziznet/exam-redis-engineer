import json
import os
import sys

import urllib3
import numpy as np
import redis
from redisvl.index import SearchIndex
from redisvl.schema import IndexSchema
from sentence_transformers import SentenceTransformer

# Suppress warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load local configuration and route references
from config import REDIS_HOST, REDIS_PW
from embeddings.routes import ROUTES

# 1. Initialize Embedding Model
# This model converts text into 384-dimensional vectors
model = SentenceTransformer("all-MiniLM-L6-v2")

# 2. Get Database Connection Info
# Port is written by create_task3_db.py
REDIS_PORT = 12000
port = REDIS_PORT

if REDIS_PW:
    REDIS_URL = f"redis://:{REDIS_PW}@{REDIS_HOST}:{port}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{port}"

# 3. Define Vector Index Schema
schema = IndexSchema.from_dict({
    "index": {
        "name": "semantic-router-index",
        "prefix": "route",
        "storage_type": "hash"
    },
    "fields": [
        {"name": "route_name", "type": "text"},
        {"name": "embedding", "type": "vector", "attrs": {
            "dims": 384,
            "algorithm": "flat",       # Exact search for accuracy
            "distance_metric": "cosine",
            "datatype": "float32"
        }}
    ]
})

def _to_embedding_bytes(vec):
    # Ensure vector is stored as float32 bytes for Redis vector fields
    try:
        return vec.astype(np.float32).tobytes()
    except AttributeError:
        return np.array(vec, dtype=np.float32).tobytes()

def setup_router():
    """Create index and load route reference embeddings"""
    index = SearchIndex(schema, redis_url=REDIS_URL)
    
    # Create index in Redis (requires RediSearch module)
    index.create(overwrite=True)

    client = redis.Redis.from_url(REDIS_URL)
    
    # Process each route's references
    data_to_load = []
    for route_name, references in ROUTES.items():
        # Represent the route by the average or combined embedding of its references
        # For simplicity, we create an entry for each reference sentence
        for ref in references:
            embedding = _to_embedding_bytes(model.encode(ref))
            doc = {
                "route_name": route_name,
                "embedding": embedding
            }
            data_to_load.append(doc)

    pipe = client.pipeline()
    for i, doc in enumerate(data_to_load):
        key = f"route:{i}"
        pipe.hset(key, mapping=doc)
    pipe.execute()

    return index, client

def route_query(client, query: str):
    """Find the best route for a given query"""
    # Convert query to vector
    query_embedding = _to_embedding_bytes(model.encode(query))
    
    # Perform Vector Similarity Search (VSS) via FT.SEARCH
    res = client.execute_command(
        "FT.SEARCH",
        "semantic-router-index",
        "*=>[KNN 1 @embedding $vec AS score]",
        "PARAMS", 2, "vec", query_embedding,
        "RETURN", 1, "route_name",
        "SORTBY", "score",
        "DIALECT", 2
    )

    if res and res[0] > 0:
        fields = res[2]
        route_name = None
        for i in range(0, len(fields), 2):
            if fields[i] == "route_name":
                route_name = fields[i + 1]
                break
        if route_name is not None:
            print(route_name)
        else:
            print("No suitable route found")
    else:
        print("No suitable route found")

if __name__ == "__main__":
    try:
        # Initialize and load data
        idx, client = setup_router()
        
        # Test Queries
        test_queries = [
            "How do I use Python to fine-tune a Llama 3 model?",
            "What are the best movies about dystopian futures and robots?",
            "I want to listen to some symphonies by Beethoven."
        ]
        
        for q in test_queries:
            # print(f"Query: '{q}' -> Route: ", end="")
            route_query(client, q)
            
    except Exception as e:
        print(f"Error in Semantic Router: {e}")
