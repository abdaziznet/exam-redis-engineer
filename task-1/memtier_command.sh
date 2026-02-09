#!/bin/bash

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
