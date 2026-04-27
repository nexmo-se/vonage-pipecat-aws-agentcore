#!/usr/bin/env python3
"""
Bedrock-Pipecat Transport Integration Module

Provides LLM conversation capabilities via AWS Bedrock Nova Sonic
integrated into the Pipecat transport pipeline.

Usage:
    llm = BedrockLLMIntegration(model_id, region, profile_name)
    response = await llm.invoke(user_text, system_prompt)
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class BedrockLLMIntegration:
    """Wraps AWS Bedrock Nova Sonic for Pipecat LLM integration."""

    def __init__(
        self,
        model_id: str = "amazon.nova-2-sonic-v1:0",
        region: str = "us-east-1",
        profile_name: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        session_token: Optional[str] = None,
    ):
        """
        Initialize Bedrock LLM integration.

        Args:
            model_id: Bedrock model ID (default: Nova Sonic)
            region: AWS region
            profile_name: AWS profile name (preferred for credentials)
            access_key_id: AWS access key (fallback if no profile)
            secret_access_key: AWS secret key (fallback if no profile)
            session_token: AWS session token (optional, for temporary credentials)
        """
        self.model_id = model_id
        self.region = region
        self.profile_name = profile_name
        self._client = None

    @property
    def client(self):
        """Lazy-load Bedrock runtime client."""
        if self._client is None:
            try:
                import boto3
            except ImportError as e:
                raise ImportError(f"boto3 not installed: {e}") from e

            if self.profile_name:
                session = boto3.Session(
                    profile_name=self.profile_name,
                    region_name=self.region,
                )
            else:
                session = boto3.Session(region_name=self.region)

            self._client = session.client("bedrock-runtime")
            logger.debug(f"Initialized Bedrock client for {self.model_id} in {self.region}")

        return self._client

    async def invoke(
        self,
        user_text: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 150,
        temperature: float = 0.7,
    ) -> str:
        """
        Invoke Bedrock Nova Sonic with user text.

        Args:
            user_text: User message to send to LLM
            system_prompt: Optional system context (prepended to user message)
            max_tokens: Maximum response tokens
            temperature: Response temperature (0.0-1.0)

        Returns:
            LLM response text

        Raises:
            Exception: On Bedrock API errors
        """
        # Build messages list
        messages = []
        if system_prompt:
            messages.append({
                "role": "user",
                "content": [{"text": system_prompt}]
            })

        messages.append({
            "role": "user",
            "content": [{"text": user_text}]
        })

        request_body = {
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }

        try:
            logger.debug(f"Invoking {self.model_id} with: {user_text[:100]}...")
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            reply = result["output"]["message"]["content"][0]["text"]
            logger.debug(f"LLM response: {reply[:100]}...")
            return reply
        except Exception as e:
            logger.error(f"Bedrock invocation failed: {e}")
            raise


class BedrockEchoContextManager:
    """Context manager for Bedrock LLM in echo scenario."""

    def __init__(self, llm: BedrockLLMIntegration):
        self.llm = llm
        self.message_history = []

    async def process_user_text(self, user_text: str) -> str:
        """
        Process user text through LLM and maintain context.

        Args:
            user_text: Transcribed user speech

        Returns:
            LLM-processed response (for echo scenario: LLM sees user message,
            responds in same turn)
        """
        # For echo scenario: treat each message independently
        system_prompt = (
            "You are a helpful echo agent. Respond conversationally and briefly "
            "in 1-2 sentences."
        )

        response = await self.llm.invoke(
            user_text=user_text,
            system_prompt=system_prompt,
            max_tokens=100,
            temperature=0.5,
        )

        # Log conversation history (for debugging)
        self.message_history.append({
            "role": "user",
            "text": user_text,
        })
        self.message_history.append({
            "role": "assistant",
            "text": response,
        })

        return response

    def get_history(self):
        """Return conversation history."""
        return self.message_history

    def clear_history(self):
        """Clear conversation history."""
        self.message_history = []
