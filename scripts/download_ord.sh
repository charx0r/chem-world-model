#!/usr/bin/env bash
# Download Open Reaction Database data via git LFS (~2-5 GB)
set -euo pipefail

DATA_DIR="${1:-data/ord-data}"

if [ -d "$DATA_DIR" ]; then
    echo "ORD data already exists at $DATA_DIR"
    echo "To re-download, remove the directory first: rm -rf $DATA_DIR"
    exit 0
fi

echo "Cloning ORD data repository into $DATA_DIR ..."
git clone https://github.com/open-reaction-database/ord-data.git "$DATA_DIR"

echo "Pulling LFS objects ..."
cd "$DATA_DIR" && git lfs pull

FILE_COUNT=$(find data -name '*.pb.gz' 2>/dev/null | wc -l | tr -d ' ')
echo "Downloaded $FILE_COUNT dataset files"
