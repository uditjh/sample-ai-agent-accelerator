#!/bin/bash
set -e

# Parse command line arguments
REPO_NAME=$1

if [ -z "$REPO_NAME" ]; then
    echo "Usage: $0 <app-name>"
    echo "Example: $0 my_agent"
    exit 1
fi

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

echo "Deleting AgentCore resources for app: $REPO_NAME"
echo "Account: $ACCOUNT"
echo "Region: $REGION"
echo ""

# Function to get agent runtime ID by name
get_agent_runtime_id() {
    local name=$1
    aws bedrock-agentcore-control list-agent-runtimes --region $REGION --query "agentRuntimes[?agentRuntimeName=='$name'].agentRuntimeId" --output text
}

# 1. Delete the agent runtime
echo "1. Deleting agent runtime: $REPO_NAME"
RUNTIME_ID=$(get_agent_runtime_id $REPO_NAME)

if [ -n "$RUNTIME_ID" ] && [ "$RUNTIME_ID" != "None" ]; then
    echo "   Found agent runtime ID: $RUNTIME_ID"
    aws bedrock-agentcore-control delete-agent-runtime --agent-runtime-id $RUNTIME_ID --region $REGION
    echo "   ✓ Agent runtime deleted"
else
    echo "   ⚠ Agent runtime '$REPO_NAME' not found"
fi

# 2. Delete IAM role and policy (only if no other agent runtimes exist)
echo ""
echo "2. Checking if IAM role should be deleted..."
ROLE_NAME=${REPO_NAME}-"AgentRuntimeRole"

# Check if there are any other agent runtimes
OTHER_RUNTIMES=$(aws bedrock-agentcore-control list-agent-runtimes --region $REGION --query 'length(agentRuntimes)' --output text)

if [ "$OTHER_RUNTIMES" = "0" ]; then
    echo "   No other agent runtimes found. Deleting IAM role: $ROLE_NAME"

    # Delete the inline policy first
    if aws iam get-role-policy --role-name $ROLE_NAME --policy-name BedrockAgentCoreRuntimePolicy >/dev/null 2>&1; then
        aws iam delete-role-policy --role-name $ROLE_NAME --policy-name BedrockAgentCoreRuntimePolicy
        echo "   ✓ Deleted inline policy: BedrockAgentCoreRuntimePolicy"
    fi

    # Delete the role
    if aws iam get-role --role-name $ROLE_NAME >/dev/null 2>&1; then
        aws iam delete-role --role-name $ROLE_NAME
        echo "   ✓ Deleted IAM role: $ROLE_NAME"
    else
        echo "   ⚠ IAM role '$ROLE_NAME' not found"
    fi
else
    echo "   ⚠ Found $OTHER_RUNTIMES other agent runtime(s). Keeping IAM role: $ROLE_NAME"
fi

# 3. Delete agentcore memories
echo ""
echo "3. Deleting agentcore memories..."
MEMORIES=$(aws bedrock-agentcore-control list-memories --region ${REGION} --query 'memories[*].id' --output text)

if [ -n "$MEMORIES" ] && [ "$MEMORIES" != "None" ]; then
    echo "   Found memories to delete:"
    for memory_id in $MEMORIES; do
        echo "   - Memory ID: $memory_id"
    done
    echo ""
    read -p "   Do you want to delete all agentcore memories? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for memory_id in $MEMORIES; do
            if aws bedrock-agentcore-control delete-memory --memory-id "$memory_id" --region ${REGION} >/dev/null 2>&1; then
                echo "   ✓ Deleted memory: $memory_id"
            else
                echo "   ⚠ Failed to delete memory: $memory_id (may already be deleted or not accessible)"
            fi
        done
    else
        echo "   ⚠ Skipped memory deletion"
    fi
else
    echo "   ⚠ No agentcore memories found"
fi

# 4. Clean up local files
echo ""
echo "4. Cleaning up local files..."
if [ -f "agent_runtime_arn" ]; then
    rm -f agent_runtime_arn
    echo "   ✓ Deleted agent_runtime_arn file"
else
    echo "   ⚠ agent_runtime_arn file not found"
fi

# 5. Optional: Clean up CloudWatch log groups
echo ""
echo "5. Checking for CloudWatch log groups..."
LOG_GROUP_PREFIX="/aws/bedrock-agentcore/runtimes"
LOG_GROUPS=$(aws logs describe-log-groups --region $REGION --log-group-name-prefix $LOG_GROUP_PREFIX --query 'logGroups[*].logGroupName' --output text)

if [ -n "$LOG_GROUPS" ]; then
    echo "   Found log groups related to bedrock-agentcore:"
    for log_group in $LOG_GROUPS; do
        echo "   - $log_group"
    done
    echo ""
    read -p "   Do you want to delete these log groups? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for log_group in $LOG_GROUPS; do
            aws logs delete-log-group --log-group-name "$log_group" --region $REGION
            echo "   ✓ Deleted log group: $log_group"
        done
    else
        echo "   ⚠ Skipped log group deletion"
    fi
else
    echo "   ⚠ No bedrock-agentcore log groups found"
fi

echo ""
echo "🎉 Cleanup completed for app: $REPO_NAME"
echo ""
echo "Summary of actions taken:"
echo "- Deleted agent runtime (if found)"
echo "- Deleted IAM role and policy (if no other runtimes exist)"
echo "- Deleted agentcore memories (if confirmed)"
echo "- Cleaned up local agent_runtime_arn file"
echo "- Optionally deleted CloudWatch log groups"
