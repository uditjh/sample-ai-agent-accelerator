from os import getenv
import logging
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime
from strands import Agent
from strands_tools import retrieve
from memoryhook import MemoryHookProvider
from bedrock_agentcore.memory import MemoryClient


class InvocationResponse(BaseModel):
    output: Dict[str, Any]


# Enables Strands debug log level
logging.getLogger("strands").setLevel(logging.DEBUG)

# Sets the logging format and streams logs to stderr
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

# print envvars
region = getenv("AWS_REGION")
logging.warning(f"AWS_REGION = {region}")

app_name = getenv("APP_NAME")
logging.warning(f"APP_NAME = {app_name}")

kb_id = getenv("KNOWLEDGE_BASE_ID")
logging.warning(f"KNOWLEDGE_BASE_ID = {kb_id}")

memory_id = getenv("MEMORY_ID")
logging.warning(f"MEMORY_ID = {memory_id}")

# Initialize Memory Client
# it's using west-2 for some reason when not specifying region
# even though AWS_REGION is set
# https://github.com/aws/bedrock-agentcore-sdk-python/blob/main/src/bedrock_agentcore/memory/client.py#L43
memory_client = MemoryClient(region_name=region)

app = FastAPI(title="AI Chat Accelerator Agent", version="1.0.0")

system_prompt = """
Your name as the AI is "AI Chatbot" and you have been created by AnyCompany as an expert in their business.
Use only the knowledge base tool when answering the user's questions.
If the knowledge base does provide information about a question, you should say you do not know the answer.
You should try to completely avoid outputting bulleted lists and sub lists, unless it's absolutely necessary.
"""

# we have a single stateful agent per container session id
strands_agent = None


@app.post("/invocations", response_model=InvocationResponse)
async def invoke_agent(request: Request):
    global strands_agent
    try:
        # validate input
        req = await request.json()
        invoke_input = req["input"]
        prompt = invoke_input["prompt"]
        if not prompt:
            raise HTTPException(
                status_code=400,
                detail="No prompt found in input. Please provide a 'prompt' key in the input."
            )
        user_id = invoke_input["user_id"]
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="No user_id found in input. Please provide a 'user_id' key in the input."
            )
        session_id = request.headers.get(
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id")
        if not session_id:
            raise HTTPException(
                status_code=400,
                detail="Missing header X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"
            )

        # initialize a new agent for each new runtime container session
        # conversation state will be persisted to agentcore memory
        if strands_agent is None:
            logging.warning("agent initializing")

            # for resumed sessions, conversation history from
            # agentcore memory will be appended to the system prompt
            # (this will be fixed in the future)
            strands_agent = Agent(
                # model="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
                model="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                system_prompt=system_prompt,
                tools=[retrieve],
                hooks=[MemoryHookProvider(
                    memory_client,
                    memory_id,
                    user_id,
                    session_id
                )],
            )

        # invoke the agent
        # conversation history should be persisted in
        # local memory and agentcore memory
        result = strands_agent(prompt=prompt)

        # send response to client
        response = {
            "message": result.message,
            "timestamp": datetime.utcnow().isoformat(),
            "model": "strands-agent",
        }
        return InvocationResponse(output=response)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Agent processing failed: {str(e)}")


@app.get("/ping")
async def ping():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
