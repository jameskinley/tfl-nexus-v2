import requests
import json
from dotenv import load_dotenv
import os
from logging import getLogger

load_dotenv()

class OpenRouterClient:
    def __init__(self):
        self.api_endpoint = os.getenv("LLM_API_ENDPOINT")
        self.api_key = os.getenv("LLM_API_KEY")
        self.model = os.getenv("LLM_MODEL", "openai/gpt-oss-20b:free")
        self.reasoning_enabled = os.getenv("LLM_REASONING_ENABLED", "false").lower() == "true" 

        self.logger = getLogger(__name__)
        self.logger.info("OpenRouterClient initialized with model: %s", self.model)

    def chat(self, prompt: str) -> str:
        if not self.api_endpoint or not self.api_key:
            raise ValueError("LLM API endpoint and key must be configured")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = json.dumps({
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that generates concise summaries of transit network reports. "
                               "Focus on key insights and actionable information. "
                               "Output should be clear and easy to understand, in plaintext format, and no more than 150 words. "
                               "It should follow a report-style format, with a brief headline followed by bullet points of key details. "
                               "Pay special attention to the 'disruption_details' field which contains specific information about each disruption, "
                               "including summaries, descriptions, and affected lines."
                },
                {
                    "role": "user",
                    "content": f"Generate a plaintext (no markdown), conversational but precise transit network status report summary from this data:\n\n{prompt}"
                }
            ]
        })

        response = requests.post(self.api_endpoint, headers=headers, data=data).json()

        # Extract text content from OpenAI-compatible response format
        if 'choices' in response and len(response['choices']) > 0:
            message = response['choices'][0].get('message', {})
            content = message.get('content', '')
            if content:
                return content
        
        # Fallback: if response format is unexpected, return error message
        raise ValueError(f"Unexpected LLM response format: {response}")



