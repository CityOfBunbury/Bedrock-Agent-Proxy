# Bedrock Agent Proxy for OpenWebUI

This application provides a proxy server that translates between the OpenAI API format (which OpenWebUI uses) and the AWS Bedrock Agent API. It allows you to use your AWS Bedrock Agents with OpenWebUI.

## Prerequisites

- Docker and Docker Compose installed on your system
- AWS credentials with access to Bedrock Agent services
- Your Bedrock Agent(s) already set up and configured in AWS

## Configuration

All configuration is managed through environment variables in the `.env` file:

1. Copy the sample `.env` file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file to update your configuration:
   ```
   # AWS Configuration
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your-access-key-id
   AWS_SECRET_ACCESS_KEY=your-secret-access-key
   
   # Server Configuration
   PORT=5000
   HOST=0.0.0.0
   DEBUG=False
   LOG_LEVEL=INFO
   
   # Agent Configuration
   DEFAULT_AGENT=COBWEBAI-ALIAS
   
   # Agent COBWEBAI-ALIAS
   AGENT_COBWEBAI_ALIAS_ID=E2HNPQDLTC
   AGENT_COBWEBAI_ALIAS_ALIAS_ID=1QELVFGOED
   ```

3. To add more agents, follow this pattern in your `.env` file:
   ```
   # Agent MY-SECOND-AGENT
   AGENT_MY_SECOND_AGENT_ID=your-agent-id
   AGENT_MY_SECOND_AGENT_ALIAS_ID=your-alias-id
   ```

## API Key Authentication

This proxy supports API key authentication to match OpenAI API behavior:

1. Configure your API key in the `.env` file:
   ```
   # Set a custom API key
   API_KEY=your-custom-key
   
   # Or disable API key validation
   API_KEY=none
   ```

2. When making requests to the proxy, include the API key in the Authorization header:
   ```
   Authorization: Bearer your-custom-key
   ```

3. When configuring OpenWebUI:
   - Set the API key to match the one in your `.env` file
   - If you've disabled API key validation (`API_KEY=none`), you can use any value in OpenWebUI

The proxy will validate the API key for all endpoints, including `/v1/chat/completions` and `/v1/models`.

## Build and Run with Docker

1. Build the Docker image and start the container:
   ```bash
   docker-compose up -d
   ```

2. To view logs:
   ```bash
   docker-compose logs -f
   ```

3. To stop the service:
   ```bash
   docker-compose down
   ```

## Using with OpenWebUI

Configure OpenWebUI to use this proxy as its OpenAI API endpoint:

1. In OpenWebUI, go to Settings > API Endpoints
2. Set the OpenAI API Base URL to `http://your-server-ip:5000`
3. You may need to set an API key (any value will work as the proxy doesn't validate it)
4. Save settings and restart OpenWebUI if necessary
5. Your Bedrock Agents should now appear as models in the model selection dropdown

## Testing the API

You can test the API endpoints with Postman:

1. GET `http://localhost:5000/v1/models` - Lists available agents as models
2. POST `http://localhost:5000/v1/chat/completions` - Sends a chat completion request

Example chat completion request body:
```json
{
  "model": "COBWEBAI-ALIAS",
  "messages": [
    {
      "role": "user",
      "content": "What information do you have about this topic?"
    }
  ]
}
```

Example request with streaming enabled:
```json
{
  "model": "COBWEBAI-ALIAS",
  "stream": true,
  "messages": [
    {
      "role": "user",
      "content": "What information do you have about this topic?"
    }
  ]
}
```

## Security Considerations

For production deployments, consider these security best practices:

1. Store your `.env` file securely and don't commit it to version control
2. Run the container with limited privileges
3. Set up TLS/HTTPS for the API endpoint
4. Consider using AWS IAM roles instead of hardcoded credentials
5. Implement rate limiting for the API endpoints