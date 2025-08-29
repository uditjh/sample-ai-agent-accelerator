#!/bin/bash
set -e

REPO_NAME=$1
KB=$2

# Determine Python and pip commands
PYTHON_CMD=""
PIP_CMD=""

if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "Error: Neither python nor python3 found"
    exit 1
fi

# Check if we can use pip3 or pip
if command -v pip3 &> /dev/null; then
    PIP_CMD="pip3"
elif command -v pip &> /dev/null; then
    PIP_CMD="pip"
else
    echo "Error: Neither pip nor pip3 found"
    exit 1
fi

echo "Using Python: $PYTHON_CMD"
echo "Using pip: $PIP_CMD"

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

# Create and activate virtual environment
VENV_DIR=".deploy_venv"
echo "Creating virtual environment in $VENV_DIR"
$PYTHON_CMD -m venv $VENV_DIR

# Activate virtual environment
source $VENV_DIR/bin/activate

# Install packages in virtual environment
echo "Installing requirements in virtual environment"
$PYTHON_CMD -m pip install -r requirements.txt

# create agent runtime
echo "Running deploy.py"
$PYTHON_CMD -u deploy.py --account ${ACCOUNT} --app ${REPO_NAME} --image ${IMAGE} --kb ${KB}

# Deactivate and cleanup virtual environment
deactivate
echo "Cleaning up virtual environment"
rm -rf $VENV_DIR
