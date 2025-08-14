#!/bin/bash
set -e

# delete s3 vector resources
echo "Deleting S3 vector index..."
S3_INDEX_NAME="${NAME}-index"
VECTOR_BUCKET_NAME="${NAME}-vectors"

# delete vector index first
aws s3vectors delete-index \
  --vector-bucket-name "$VECTOR_BUCKET_NAME" \
  --index-name "$S3_INDEX_NAME" || echo "Index may not exist or already deleted"

echo "Deleted vector index: $S3_INDEX_NAME"

# delete vector bucket
aws s3vectors delete-vector-bucket \
  --vector-bucket-name "$VECTOR_BUCKET_NAME"

echo "Deleted vector bucket: $VECTOR_BUCKET_NAME"

# lookup kb id by name
id=$(cat kb-id.txt)

# delete kb
aws bedrock-agent delete-knowledge-base --knowledge-base-id ${id}
