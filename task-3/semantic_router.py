from redisvl.index import SearchIndex
from redisvl.schema import IndexSchema
from sentence_transformers import SentenceTransformer
import numpy as np

from embeddings.routes import ROUTES

model = SentenceTransformer("all-MiniLM-L6-v2")

schema = IndexSchema.from_dict({
    "index": {
        "name": "semantic-routes",
        "prefix": "route",
        "storage_type": "hash"
    },
    "fields": [
        {"name": "route", "type": "text"},
        {"name": "embedding", "type": "vector", "attrs": {
            "dims": 384,
            "algorithm": "flat",
            "distance_metric": "cosine"
        }}
    ]
})

index = SearchIndex(schema, redis_url="redis://172.16.22.21:12000")
index.create(overwrite=True)

# Insert routes
for route, refs in ROUTES.items():
    emb = model.encode(" ".join(refs)).tolist()
    index.load([{
        "route": route,
        "embedding": emb
    }])

def route_query(query: str):
    q_emb = model.encode(query).tolist()
    res = index.query(
        vector=q_emb,
        vector_field="embedding",
        return_fields=["route"],
        num_results=1
    )
    print("Best Route:", res.docs[0].route)

if __name__ == "__main__":
    route_query("How do I fine tune a large language model?")
