import os
import json
import time
import logging
import re
from flask import Flask, request, jsonify, Response
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load AWS configuration from environment
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")

# Load server configuration
PORT = int(os.environ.get("PORT", 5000))
HOST = os.environ.get("HOST", "0.0.0.0")
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# Load API key configuration - this is the mock API key to accept
API_KEY = os.environ.get("API_KEY", "bedrock-agent-proxy-key")

# Load agent configuration
DEFAULT_AGENT = os.environ.get("DEFAULT_AGENT", "COBWEBAI-ALIAS")

# Dynamically build the AGENTS dictionary from environment variables
AGENTS = {}
agent_pattern = re.compile(r"AGENT_([A-Z0-9_]+)_ID")

for key in os.environ:
    match = agent_pattern.match(key)
    if match:
        agent_name = match.group(1).replace("_", "-")
        agent_id = os.environ[key]
        alias_key = f"AGENT_{match.group(1)}_ALIAS_ID"
        alias_id = os.environ.get(alias_key)
        
        if alias_id:
            AGENTS[agent_name] = {
                "agent_id": agent_id,
                "alias_id": alias_id
            }
            logger.info(f"Loaded agent configuration for {agent_name}")

# Initialize Bedrock client with credentials
bedrock_agent_runtime = boto3.client(
    service_name="bedrock-agent-runtime",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

def validate_api_key():
    """
    Validate the API key from the Authorization header
    Returns True if valid, False otherwise
    """
    auth_header = request.headers.get('Authorization')
    
    # If API_KEY is set to empty string or "none", skip validation
    if not API_KEY or API_KEY.lower() == "none":
        return True
        
    if not auth_header:
        logger.warning("Missing Authorization header")
        return False
        
    # Extract the key from the Authorization header
    # The format is typically "Bearer YOUR_API_KEY"
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        logger.warning("Invalid Authorization header format")
        return False
        
    provided_key = parts[1]
    
    # Validate against our configured API key
    if provided_key != API_KEY:
        logger.warning("Invalid API key provided")
        return False
        
    return True

@app.route("/api/v1/chat/completions", methods=["POST"])
def chat_completions():
    """
    Handle OpenAI-style chat completions API request and proxy to Bedrock Agent
    """
    try:
        data = request.json
        logger.info(f"Received request: {json.dumps(data, indent=2)}")
        
        # Extract messages and model from OpenAI format
        messages = data.get("messages", [])
        model_id = data.get("model", DEFAULT_AGENT)
        stream_mode = data.get("stream", False)  # Check if streaming is requested
        
        # Get agent configuration based on model ID
        agent_config = AGENTS.get(model_id)
        
        # If the model ID doesn't match any agent, use the default
        if not agent_config:
            logger.warning(f"Unknown model ID: {model_id}, using default agent")
            agent_config = AGENTS.get(DEFAULT_AGENT)
            
        agent_id = agent_config["agent_id"]
        alias_id = agent_config["alias_id"]
        
        # Find the last user message
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content")
                break
        
        if not last_user_message:
            last_user_message = messages[-1].get("content", "")
            logger.warning(f"No user message found in conversation, using last message")
        
        # Prepare context from previous messages
        context = "Previous conversation:\n"
        has_previous_messages = False
        
        for i, msg in enumerate(messages[:-1]):  # All but the last message
            role = msg.get("role")
            content = msg.get("content")
            
            if role == "system":
                context += f"System instruction: {content}\n"
                has_previous_messages = True
            elif role == "user":
                context += f"User: {content}\n"
                has_previous_messages = True
            elif role == "assistant":
                context += f"Assistant: {content}\n"
                has_previous_messages = True
        
        # Combine context with the last message
        full_input = last_user_message
        if has_previous_messages:
            full_input = f"{context}\n\nCurrent message: {last_user_message}"
        
        # Extract the session ID from the request or generate a default one
        session_id = data.get("session_id", f"session-{model_id}-{os.urandom(4).hex()}")
        
        # Prepare request to Bedrock Agent
        agent_request = {
            "agentId": agent_id,
            "agentAliasId": alias_id,
            "sessionId": session_id,
            "inputText": full_input,
            "enableTrace": False  # Set to True for debugging
        }
        
        logger.info(f"Calling Bedrock Agent: {agent_id} with alias: {alias_id}")
        
        # Call Bedrock Agent
        response = bedrock_agent_runtime.invoke_agent(**agent_request)
        
        # Generate a response ID
        response_id = f"chatcmpl-{model_id}-{os.urandom(4).hex()}"
        created_time = int(time.time())
        
        # Handle streaming mode
        if stream_mode:
            def generate_stream():
                # Send the initial response with role
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": model_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant"
                            },
                            "finish_reason": None
                        }
                    ]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                
                # Stream each content chunk
                for event in response["completion"]:
                    if "chunk" in event:
                        content = event["chunk"]["bytes"].decode("utf-8")
                        if content:
                            chunk = {
                                "id": response_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": model_id,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {
                                            "content": content
                                        },
                                        "finish_reason": None
                                    }
                                ]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                
                # Send the final chunk with finish_reason
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": model_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }
                    ]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                
                # End the stream
                yield "data: [DONE]\n\n"
            
            # Configure response for proper SSE handling
            return Response(
                generate_stream(), 
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering if you're using it
                    "Transfer-Encoding": "chunked"
                }
            )
        
        # Non-streaming mode - collect the full response
        else:
            # Handle EventStream response
            completion = ""
            for event in response["completion"]:
                if "chunk" in event:
                    completion += event["chunk"]["bytes"].decode("utf-8")
            
            # Map Bedrock Agent response to OpenAI format
            openai_response = {
                "id": response_id,
                "object": "chat.completion",
                "created": created_time,
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": completion
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": -1,  # Not available from Bedrock
                    "completion_tokens": -1,  # Not available from Bedrock
                    "total_tokens": -1  # Not available from Bedrock
                }
            }
            
            logger.info(f"Sending response from agent {model_id}")
            return jsonify(openai_response)

@app.route("/api/v1/models", methods=["GET"])
def list_models():
    """
    Return a list of available Bedrock Agents as models that OpenWebUI can use
    """
    # Check API key for models endpoint too
    if not validate_api_key():
        return jsonify({
            "error": {
                "message": "Invalid API key",
                "type": "invalid_request_error",
                "param": None,
                "code": "invalid_api_key"
            }
        }), 401
        
    models_data = []
    
    # Convert each agent to a model entry
    for model_id, agent_config in AGENTS.items():
        models_data.append({
            "id": model_id,
            "object": "model",
            "created": 1677610602,  # Placeholder timestamp
            "owned_by": "aws-bedrock"
        })
    
    models_response = {
        "object": "list",
        "data": models_data
    }
    
    return jsonify(models_response)

if __name__ == "__main__":
    logger.info(f"Starting Bedrock Agent Proxy on port {PORT}")
    logger.info(f"AWS Region: {AWS_REGION}")
    logger.info(f"Available agents: {list(AGENTS.keys())}")
    logger.info(f"Default agent: {DEFAULT_AGENT}")
    logger.info(f"API Key required: {API_KEY != 'none' and API_KEY != ''}")
    
    app.run(host=HOST, port=PORT, debug=DEBUG)