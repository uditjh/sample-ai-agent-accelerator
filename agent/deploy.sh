#!/bin/bash
set -e

REPO_NAME=$1
KB=$2

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY=${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com

# create ecr repo if needed
aws ecr describe-repositories --repository-names ${REPO_NAME} || aws ecr create-repository --repository-name ${REPO_NAME}
REGISTRY=$(aws ecr describe-repositories --repository-names ${REPO_NAME} | jq '.repositories[0].repositoryUri' -r)

# login to ecr
echo "logging into ecr: ${REGISTRY}"
aws ecr get-login-password | docker login --username AWS --password-stdin ${REGISTRY}

# build and push image
export VERSION=$(cat /dev/urandom | LC_ALL=C tr -dc 'a-zA-Z0-9' | fold -w 50 | head -n 1)
IMAGE=${REGISTRY}:${VERSION}
echo ""
echo "building and pushing image: ${IMAGE}"
docker buildx build --platform linux/arm64 -t ${IMAGE} --push .

# create agent runtime
python -u deploy.py --account ${ACCOUNT} --app ${REPO_NAME} --image ${IMAGE} --kb ${KB}
