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

    try:
        logging.info("Checking environment variables...")
        if not agent_runtime_arn:
            raise Exception("AGENT_RUNTIME environment variable is not set or empty")
        
        aws_region = os.getenv("AWS_REGION")
        if not aws_region:
            raise Exception("AWS_REGION environment variable is not set")
            
        logging.info(f"Using agent runtime ARN: {agent_runtime_arn}")
        logging.info(f"Using AWS region: {aws_region}")

        payload_data = {
            "input": {
                "user_id": conversation_history["userId"],
                "prompt": new_question,
            }
        }
        payload = json.dumps(payload_data)
        logging.info(f"Payload created: {payload}")

        request = {
            "agentRuntimeArn": agent_runtime_arn,
            "payload": payload,
            "runtimeUserId": conversation_history["userId"],
            "runtimeSessionId": conversation_history["conversationId"],
            "contentType": "application/json",
        }
        log.info(request)

        logging.info("Calling invoke_agent_runtime...")
        # Call invoke_agent_runtime
        response = runtime.invoke_agent_runtime(**request)
        logging.info("invoke_agent_runtime call completed")

        # Handle the response
        status_code = response["statusCode"]
        logging.info(f"Status Code: {status_code}")
        if status_code != 200:
            raise Exception(f"Agent runtime returned an http {status_code}")

        # The response body is a StreamingBody object
        logging.info("Reading response body...")
        response_body = response["response"].read().decode("utf-8")
        logging.info(f"Response body length: {len(response_body)}")
        
        response = json.loads(response_body)
        logging.info("Response parsed successfully")
        log.info(response)
        
        output = response["output"]["message"]["content"][0]["text"]
        logging.info(f"Extracted output length: {len(output)}")
        sources = []

        return output, sources
        
    except Exception as e:
        logging.error(f"Error in orchestrate: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        raise
