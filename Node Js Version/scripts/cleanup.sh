#!/bin/bash
# Clear uploads older than 30 days
find ./uploads -type f -mtime +30 -exec rm -f {} \;

# Clear old caches
rm -rf .next/cache
