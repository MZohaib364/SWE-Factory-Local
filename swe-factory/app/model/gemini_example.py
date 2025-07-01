"""
Example usage of Gemini15Pro LLM model.
Fill in your own BASE_URL, API_KEY, and MODEL_NAME.
"""

import os
from app.model.gemini import Gemini15Pro

# === FILL THESE IN YOURSELF ===
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
API_KEY = "AIzaSyDKBkp_HUgYQMgZbdmQdAKfnMTm3Kee6eo"
MODEL_NAME = "google/gemini-2.5-flash"  # e.g., "gemini-1.5-pro-preview-0409"
# =============================


# Instantiate the model (uses singleton pattern)
gemini = Gemini15Pro()

# Example prompt
messages = [
    {"role": "user", "content": "Tell me a joke about AI."}
]

# Call the model
try:
    response, cost, input_tokens, output_tokens = gemini.call(messages)
    print("Response:", response)
    print(f"Cost: {cost}, Input tokens: {input_tokens}, Output tokens: {output_tokens}")
except Exception as e:
    print("Error during Gemini call:", e) 