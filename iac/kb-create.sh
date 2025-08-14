#!/bin/bash
set -e

# create s3 vector bucket
echo "Creating S3 vector bucket..."
VECTOR_BUCKET_NAME="${NAME}-vectors"
aws s3vectors create-vector-bucket \
  --vector-bucket-name "$VECTOR_BUCKET_NAME"

# get the vector bucket ARN
VECTOR_BUCKET_ARN=$(aws s3vectors get-vector-bucket \
  --vector-bucket-name "$VECTOR_BUCKET_NAME" \
  --query 'vectorBucket.vectorBucketArn' \
  --output text)

echo "Created vector bucket: $VECTOR_BUCKET_ARN"

# create s3 vector index
echo "Creating S3 vector index..."
S3_INDEX_NAME="${NAME}-index"
aws s3vectors create-index \
  --vector-bucket-name "$VECTOR_BUCKET_NAME" \
  --index-name "$S3_INDEX_NAME" \
  --data-type "float32" \
  --dimension 1024 \
  --distance-metric "cosine" \
  --metadata-configuration '{"nonFilterableMetadataKeys":["AMAZON_BEDROCK_TEXT","AMAZON_BEDROCK_METADATA"]}'

# get the vector index ARN
S3_INDEX_ARN=$(aws s3vectors get-index \
  --vector-bucket-name "$VECTOR_BUCKET_NAME" \
  --index-name "$S3_INDEX_NAME" \
  --query 'index.indexArn' \
  --output text)

echo "Created vector index: $S3_INDEX_ARN"

# create kb with retry logic for IAM propagation
echo "Creating Bedrock knowledge base..."
for i in {1..3}; do
  echo "Attempt $i of 3..."
  json=$(aws bedrock-agent create-knowledge-base \
    --name "${NAME}" \
    --description "${DESCRIPTION}" \
    --role-arn "${KB_ROLE_ARN}" \
    --knowledge-base-configuration "$(cat <<EOF
{
  "type": "VECTOR",
  "vectorKnowledgeBaseConfiguration": {
    "embeddingModelArn": "${EMBEDDING_MODEL}"
  }
}
EOF
    )" \
    --storage-configuration "$(cat <<EOF
{
  "type": "S3_VECTORS",
  "s3VectorsConfiguration": {
    "indexArn": "$S3_INDEX_ARN",
    "vectorBucketArn": "$VECTOR_BUCKET_ARN"
  }
}
EOF
    )" 2>&1)

  if [[ $? -eq 0 ]]; then
    echo "Knowledge base created successfully"
    break
  elif [[ $i -eq 3 ]]; then
    echo "Failed to create knowledge base after 3 attempts"
    echo "$json"
    exit 1
  else
    echo "Attempt $i failed, retrying in 15 seconds..."
    echo "$json"
    sleep 15
  fi
done

# write kb values to files for use in other scripts

arn=$(echo $json | jq '.knowledgeBase.knowledgeBaseArn' -r)
echo -n $arn > kb-arn.txt

id=$(echo $json | jq '.knowledgeBase.knowledgeBaseId' -r)
echo -n $id > kb-id.txt
