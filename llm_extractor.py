import os
import json

from dotenv import load_dotenv
from groq import Groq

from models import CompanyIntelligence


# Load variables from .env
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError(
        "GROQ_API_KEY is missing. Please check your .env file."
    )


# Create Groq client
client = Groq(api_key=api_key)


def extract_company_intelligence(company_text):
    """
    Send cleaned website text to the LLM
    and extract structured company intelligence.
    """

    prompt = f"""
You are an AI company research and lead enrichment agent.

Analyze the following publicly available company website content.

Extract the following information:

1. Company Overview
   - Give a concise overview in exactly 2 sentences.

2. Target Audience / ICP
   - Identify the company's primary customers or ideal customer profile.

3. Contact Points
   - Extract only generic/public email addresses explicitly found
     in the provided content.
   - Never invent an email address.

4. Leadership / Team Members
   - Extract important people and their roles/titles.
   - Include LinkedIn URLs only if they are explicitly present.
   - Never invent names or LinkedIn URLs.

5. Confidence Score
   - Give a score between 0.0 and 1.0.
   - Higher score means the information is more complete and reliable.

IMPORTANT RULES:
- Use ONLY information provided in the website content.
- Do not guess.
- Do not invent information.
- If information is unavailable, use an empty list where appropriate.
- Return structured JSON matching the provided schema.

WEBSITE CONTENT:
{company_text}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful company intelligence "
                    "extraction agent. Never invent information."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "company_intelligence",
                "strict": False,
                "schema": CompanyIntelligence.model_json_schema()
            }
        }
    )

    # Get the model's JSON response
    raw_result = response.choices[0].message.content

    # Convert JSON text into Python dictionary
    result = json.loads(raw_result)

    # Validate the result using Pydantic
    validated_result = CompanyIntelligence.model_validate(result)

    return validated_result


# Test the LLM independently
if __name__ == "__main__":

    test_text = """
    Postman is an API platform that helps developers and teams
    design, build, test and collaborate on APIs.

    Postman is used by software developers, engineering teams,
    API teams and organizations.

    The platform provides tools for API development and testing.
    """

    print("Sending test data to Groq...")

    result = extract_company_intelligence(test_text)

    print("\n========== AI RESULT ==========")

    print(result.model_dump_json(indent=2))