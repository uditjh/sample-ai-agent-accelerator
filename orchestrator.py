import os
import json
import logging
import log
import boto3

runtime = boto3.client("bedrock-agentcore")

agent_runtime_arn = os.getenv("AGENT_RUNTIME")
if agent_runtime_arn == "":
    raise Exception("AGENT_RUNTIME is required")


def orchestrate(conversation_history, new_question):
    """Orchestrates RAG workflow based on conversation history
    and a new question. Returns an answer and a list of
    source documents."""

    payload_data = {
        "input": {
            "user_id": conversation_history["userId"],
            "prompt": new_question,
        }
    }
    payload = json.dumps(payload_data)

    request = {
        "agentRuntimeArn": agent_runtime_arn,
        "payload": payload,
        "runtimeUserId": conversation_history["userId"],
        "runtimeSessionId": conversation_history["conversationId"],
        "contentType": "application/json",
    }
    log.info(request)

    # Call invoke_agent_runtime
    response = runtime.invoke_agent_runtime(**request)

    # Handle the response
    status_code = response["statusCode"]
    logging.info(f"Status Code: {status_code}")
    if status_code != 200:
        raise Exception(f"Agent runtime returned an http {status_code}")

    # The response body is a StreamingBody object
    response_body = response["response"].read().decode("utf-8")
    response = json.loads(response_body)
    logging.info(response)
    output = response["output"]["message"]["content"][0]["text"]
    sources = []

    return output, sources
