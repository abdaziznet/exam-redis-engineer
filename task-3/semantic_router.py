import json
import os
import sys

import urllib3
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
default_port = 12000
db_info_path = os.path.join(os.path.dirname(__file__), "db_info.json")
port = default_port
if os.path.exists(db_info_path):
    with open(db_info_path, "r") as f:
        port = json.load(f).get("port", default_port)

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
            "distance_metric": "cosine"
        }}
    ]
})

def setup_router():
    """Create index and load route reference embeddings"""
    index = SearchIndex(schema, redis_url=REDIS_URL)
    
    # Create index in Redis (requires RediSearch module)
    index.create(overwrite=True)
    
    # Process each route's references
    data_to_load = []
    for route_name, references in ROUTES.items():
        # Represent the route by the average or combined embedding of its references
        # For simplicity, we create an entry for each reference sentence
        for ref in references:
            embedding = model.encode(ref).tolist()
            data_to_load.append({
                "route_name": route_name,
                "embedding": embedding
            })
    
    index.load(data_to_load)
    return index

def route_query(index, query: str):
    """Find the best route for a given query"""
    # Convert query to vector
    query_embedding = model.encode(query).tolist()
    
    # Perform Vector Similarity Search (VSS)
    results = index.query(
        vector=query_embedding,
        vector_field="embedding",
        return_fields=["route_name"],
        num_results=1
    )
    
    if results.docs:
        # AS PER REQUIREMENT: Show only the name of the route
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
            # print(f"Query: '{q}' -> Route: ", end="")
            route_query(idx, q)
            
    except Exception as e:
        print(f"Error in Semantic Router: {e}")
