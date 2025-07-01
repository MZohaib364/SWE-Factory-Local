"""
Hugging Face Inference API model integration using LiteLLM.
"""

import os
import sys
from typing import Literal

import litellm
from litellm.types.utils import Choices, Message, ModelResponse
from openai import BadRequestError
from tenacity import retry, stop_after_attempt, wait_random_exponential

from app.log import log_and_print
from app.model import common
from app.model.common import Model

class HuggingFaceModel(Model):
    """
    Base class for creating Singleton instances of Hugging Face models.
    """
    _instances = {}

    def __new__(cls, *args, **kwargs):
        # Extract name from args or kwargs for singleton key
        name = None
        if args:
            name = args[0]
        elif 'name' in kwargs:
            name = kwargs['name']
        key = (cls, name)
        if key not in cls._instances:
            cls._instances[key] = super().__new__(cls)
            cls._instances[key]._initialized = False
        return cls._instances[key]

    def __init__(self, name: str, cost_per_input: float = 0.0, cost_per_output: float = 0.0, parallel_tool_call: bool = False):
        if getattr(self, '_initialized', False):
            return
        super().__init__(name, cost_per_input, cost_per_output, parallel_tool_call)
        self._initialized = True

    def setup(self) -> None:
        self.check_api_key()

    def check_api_key(self) -> str:
        key_name = "HUGGINGFACE_API_KEY"
        hf_key = os.getenv(key_name)
        if not hf_key:
            print(f"Please set the {key_name} env var")
            sys.exit(1)
        os.environ["HUGGINGFACEHUB_API_TOKEN"] = hf_key
        return hf_key

    def extract_resp_content(self, chat_message: Message) -> str:
        content = chat_message.content
        if content is None:
            return ""
        else:
            return content

    @retry(wait=wait_random_exponential(min=30, max=600), stop=stop_after_attempt(3))
    def call(
        self,
        messages: list[dict],
        top_p=1,
        tools=None,
        response_format: Literal["text", "json_object"] = "text",
        **kwargs,
    ):
        try:
            prefill_content = "{"
            if response_format == "json_object":
                messages.append({"role": "assistant", "content": prefill_content})

            # Convert messages to a single prompt string for HF
            if isinstance(messages, list):
                prompt = ""
                for msg in messages:
                    if isinstance(msg, dict) and "content" in msg:
                        prompt += msg["content"] + "\n"
                    elif isinstance(msg, str):
                        prompt += msg + "\n"
            else:
                prompt = str(messages)

            response = litellm.completion(
                model=self.name,
                messages=[{"role": "user", "content": prompt.strip()}],
                temperature=common.MODEL_TEMP,
                max_tokens=1024,
                top_p=0.95,
                stream=False,
            )
            resp_usage = response.get('usage') if isinstance(response, dict) else getattr(response, 'usage', None)
            input_tokens = int(resp_usage['prompt_tokens']) if resp_usage and 'prompt_tokens' in resp_usage else 0
            output_tokens = int(resp_usage['completion_tokens']) if resp_usage and 'completion_tokens' in resp_usage else 0
            cost = self.calc_cost(input_tokens, output_tokens)

            common.thread_cost.process_cost += cost
            common.thread_cost.process_input_tokens += input_tokens
            common.thread_cost.process_output_tokens += output_tokens

            if isinstance(response, dict):
                first_resp_choice = response['choices'][0]
                resp_msg = first_resp_choice['message']
                content = self.extract_resp_content(resp_msg)
            else:
                # fallback: try to get message from attribute if not dict (should not happen for HF)
                content = ""
            if response_format == "json_object":
                if not content.startswith(prefill_content):
                    content = prefill_content + content
            return content, cost, input_tokens, output_tokens

        except BadRequestError as e:
            print("Hugging Face BadRequestError:", e)
            if hasattr(e, 'response'):
                print("HF API response:", getattr(e, 'response', None))
            if hasattr(e, 'message'):
                print("HF API message:", getattr(e, 'message', None))
            if hasattr(e, 'body'):
                print("HF API body:", getattr(e, 'body', None))
            if hasattr(e, 'args'):
                print("HF API args:", e.args)
            if hasattr(e, 'error'):
                print("HF API error:", getattr(e, 'error', None))
            if hasattr(e, 'status_code'):
                print("HF API status_code:", getattr(e, 'status_code', None))
            if hasattr(e, 'text'):
                print("HF API text:", getattr(e, 'text', None))
            if hasattr(e, 'content'):
                print("HF API content:", getattr(e, 'content', None))
            if hasattr(e, 'data'):
                print("HF API data:", getattr(e, 'data', None))
            raise e
        except Exception as e:
            import traceback
            print("Hugging Face APIError or other Exception:", e)
            traceback.print_exc()
            if hasattr(e, 'response'):
                print("HF API response:", getattr(e, 'response', None))
            if hasattr(e, 'message'):
                print("HF API message:", getattr(e, 'message', None))
            if hasattr(e, 'body'):
                print("HF API body:", getattr(e, 'body', None))
            if hasattr(e, 'args'):
                print("HF API args:", e.args)
            if hasattr(e, 'error'):
                print("HF API error:", getattr(e, 'error', None))
            if hasattr(e, 'status_code'):
                print("HF API status_code:", getattr(e, 'status_code', None))
            if hasattr(e, 'text'):
                print("HF API text:", getattr(e, 'text', None))
            if hasattr(e, 'content'):
                print("HF API content:", getattr(e, 'content', None))
            if hasattr(e, 'data'):
                print("HF API data:", getattr(e, 'data', None))
            raise e

# Example concrete model class for Llama-3 8B Chat
class Llama3_8B_HF(HuggingFaceModel):
    def __init__(self):
        super().__init__("meta-llama/Meta-Llama-3-8B-Instruct")
        self.note = "Meta Llama-3 8B Instruct (Hugging Face Inference API)"

class Gemma2B_HF(HuggingFaceModel):
    def __init__(self):
        super().__init__("huggingface/google/gemma-2b-it")
        self.note = "Google Gemma 2B Instruct (Hugging Face Inference API)"

class Mistral7BInstruct_HF(HuggingFaceModel):
    def __init__(self):
        super().__init__("huggingface/mistralai/Mistral-7B-Instruct-v0.2")
        self.note = "Mistral 7B Instruct (Hugging Face Inference API)"

class Zephyr7B_HF(HuggingFaceModel):
    def __init__(self):
        super().__init__("huggingface/HuggingFaceH4/zephyr-7b-beta")
        self.note = "Zephyr 7B Beta (Hugging Face Inference API)" 