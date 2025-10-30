"""
Base Agent Class with Claude Sonnet Integration
Provides LLM-powered analysis capabilities for all trading agents
"""

# Defer hard failure on optional dependency to runtime with a clear message
try:
    import anthropic  # type: ignore
    _ANTHROPIC_IMPORT_ERROR = None
except Exception as _e:  # ImportError or environment-specific SSL issues
    anthropic = None  # type: ignore
    _ANTHROPIC_IMPORT_ERROR = _e
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime


class BaseAgent:
    """
    Base class for all trading agents with Claude Sonnet integration
    """

    def __init__(self,
                 agent_name: str,
                 api_key: str,
                 model: str = "claude-sonnet-4-20250514",
                 max_tokens: int = 4096,
                 temperature: float = 0.3):
        """
        Initialize the base agent with Claude Sonnet

        Args:
            agent_name: Name of the agent (e.g., "MarketSentiment")
            api_key: Anthropic API key
            model: Claude model to use
            max_tokens: Maximum tokens for response
            temperature: Temperature for LLM (0.0-1.0)
        """
        self.agent_name = agent_name
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Validate anthropic dependency availability
        if anthropic is None:
            msg = (
                "anthropic package is not available. Install dependencies and retry. "
                "Run: pip install -r requirements.txt. Original error: "
                f"{_ANTHROPIC_IMPORT_ERROR}"
            )
            raise ImportError(msg)

        # Initialize Claude client
        self.client = anthropic.Anthropic(api_key=api_key)

        # Setup logging
        self.logger = logging.getLogger(f"Agent.{agent_name}")

        # Track agent calls
        self.total_calls = 0
        self.total_tokens = 0

        self.logger.info(f"{agent_name} agent initialized with model {model}")

    def analyze(self, data: Dict[str, Any], context: str = "") -> Dict[str, Any]:
        """
        Analyze data using Claude Sonnet
        Must be implemented by child classes

        Args:
            data: Input data for analysis
            context: Additional context for the LLM

        Returns:
            Analysis results as dictionary
        """
        raise NotImplementedError("Child classes must implement analyze()")

    def _call_claude(self,
                    system_prompt: str,
                    user_message: str,
                    response_format: str = "json") -> Dict[str, Any]:
        """
        Call Claude Sonnet API with structured prompts

        Args:
            system_prompt: System instructions for Claude
            user_message: User message/query
            response_format: Expected response format ("json" or "text")

        Returns:
            Parsed response from Claude
        """
        try:
            self.total_calls += 1

            # Add JSON instruction if needed
            if response_format == "json":
                system_prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanations."

            # Call Claude API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )

            # Track tokens
            self.total_tokens += message.usage.input_tokens + message.usage.output_tokens

            # Extract response
            response_text = message.content[0].text

            # Parse response
            if response_format == "json":
                try:
                    result = json.loads(response_text)
                    result["_meta"] = {
                        "agent": self.agent_name,
                        "timestamp": datetime.now().isoformat(),
                        "tokens_used": message.usage.input_tokens + message.usage.output_tokens
                    }
                    return result
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON parse error: {e}")
                    self.logger.error(f"Response text: {response_text}")
                    return {
                        "error": "Invalid JSON response",
                        "raw_response": response_text
                    }
            else:
                return {
                    "response": response_text,
                    "_meta": {
                        "agent": self.agent_name,
                        "timestamp": datetime.now().isoformat(),
                        "tokens_used": message.usage.input_tokens + message.usage.output_tokens
                    }
                }

        except Exception as e:
            self.logger.error(f"Claude API call failed: {str(e)}")
            return {
                "error": str(e),
                "agent": self.agent_name
            }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get agent statistics

        Returns:
            Statistics dictionary
        """
        return {
            "agent_name": self.agent_name,
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "avg_tokens_per_call": self.total_tokens / max(1, self.total_calls)
        }

    def format_data_for_llm(self, data: Dict[str, Any]) -> str:
        """
        Format data dictionary into readable string for LLM

        Args:
            data: Data dictionary

        Returns:
            Formatted string
        """
        lines = []
        for key, value in data.items():
            if isinstance(value, (int, float)):
                lines.append(f"{key}: {value:.2f}" if isinstance(value, float) else f"{key}: {value}")
            elif isinstance(value, dict):
                lines.append(f"{key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  {sub_key}: {sub_value}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
