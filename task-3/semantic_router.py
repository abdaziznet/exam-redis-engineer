import json
import os
import sys

import urllib3
import numpy as np
from redisvl.index import SearchIndex
from redisvl.schema import IndexSchema
from redisvl.redis.utils import array_to_buffer
from sentence_transformers import SentenceTransformer
from redis import Redis

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
REDIS_PORT = 10218
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
    # Official RedisVL helper to store vector bytes in HASH storage
    return array_to_buffer(vec, dtype="float32")

def setup_router():
    """Create index and load route reference embeddings"""
    index = SearchIndex(schema, redis_url=REDIS_URL)
    
    # Create index in Redis (requires RediSearch module)
    index.create(overwrite=True)

    # Load data manually via Redis client to avoid the list conversion issue
    redis_client = Redis.from_url(REDIS_URL, decode_responses=False)
    
    pipe = redis_client.pipeline()
    doc_id = 0
    
    for route_name, references in ROUTES.items():
        for ref in references:
            # Encode reference to embedding
            embedding = model.encode(ref)
            # Convert to bytes format that Redis accepts
            embedding_bytes = array_to_buffer(embedding, dtype="float32")
            
            # Store as HASH with proper key prefix
            key = f"route:{doc_id}"
            pipe.hset(key, mapping={
                "route_name": route_name,
                "embedding": embedding_bytes
            })
            doc_id += 1
    
    # Execute all commands
    pipe.execute()
    redis_client.close()
    
    return index

def route_query(index, query: str):
    """Find the best route for a given query"""
    # Convert query to vector (as numpy array first, then to bytes)
    query_embedding = model.encode(query)
    query_embedding_bytes = array_to_buffer(query_embedding, dtype="float32")
    
    # Perform Vector Similarity Search via RedisVL
    results = index.search(
        query_embedding_bytes,
        vector_field_name="embedding",
        return_fields=["route_name"],
        num_results=1
    )
    
    if results.docs:
        print(results.docs[0].route_name)
    else:
        print("No suitable route found")

if __name__ == "__main__":
    try:
        # Initialize and load data
        idx = setup_router()
        
        # Test Queries
        test_queries = [
            "How do I use Python to fine-tune a Llama 3 model?",
            "What are the best movies about dystopian futures and robots?",
            "I want to listen to some symphonies by Beethoven."
        ]
        
        for q in test_queries:
            route_query(idx, q)
            
    except Exception as e:
        print(f"Error in Semantic Router: {e}")
