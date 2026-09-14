import json
import os

from dotenv import load_dotenv
from groq import Groq

from models import CompanyIntelligence


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

MODEL_NAME = "openai/gpt-oss-20b"

# Groq pricing for openai/gpt-oss-20b
# Price per 1 million tokens

INPUT_COST_PER_MILLION = 0.075
OUTPUT_COST_PER_MILLION = 0.30


# ---------------------------------------------------------
# Environment and client setup
# ---------------------------------------------------------

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError(
        "GROQ_API_KEY is missing. Please check your .env file."
    )

client = Groq(
    api_key=api_key
)


# ---------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------

def calculate_estimated_cost(
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Calculate the estimated Groq API cost in USD.
    """

    input_cost = (
        input_tokens / 1_000_000
    ) * INPUT_COST_PER_MILLION

    output_cost = (
        output_tokens / 1_000_000
    ) * OUTPUT_COST_PER_MILLION

    return input_cost + output_cost


# ---------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------

def extract_company_intelligence(
    company_text: str,
) -> tuple[CompanyIntelligence, dict]:
    """
    Send website and external search evidence to the LLM
    and extract structured company intelligence using
    JSON Schema.

    Returns:

        A tuple containing:

        - validated CompanyIntelligence result
        - token usage and estimated cost information
    """

    prompt = f"""
You are an AI company research and lead enrichment agent.

Analyze the following publicly available company research
evidence and extract structured company intelligence.

The evidence may contain:

1. Direct company website content
2. Publicly discovered contact information
3. Public LinkedIn URLs found on the company website
4. External web search results

Use the direct company website as the primary source.
Use external search evidence only as supplementary evidence,
especially when identifying publicly discoverable leadership
or LinkedIn information that is not available on the company
website.

Extract the following information:

1. Company Overview

   - Give a concise overview in exactly 2 sentences.
   - Prefer information from the company's website.

2. Target Audience / ICP

   - Identify the company's primary customers or ideal
     customer profile.
   - Prefer direct website evidence.
   - Do not guess if the evidence is insufficient.

3. Contact Points

   - Extract only generic/public email addresses explicitly
     found in the provided evidence.
   - Prefer email addresses discovered directly from the
     company website.
   - Never invent an email address.
   - Do not generate an email address based on a person's
     name or company domain.
   - If no public email address is found, return an empty list.

4. Leadership / Team Members

   - Extract important leadership or team members and
     their roles/titles.
   - Prefer leadership information explicitly supported
     by the company website.
   - External search evidence may be used as supplementary
     evidence when appropriate.
   - Include a LinkedIn URL only when the URL is explicitly
     present in the provided evidence.
   - Never invent a person's name.
   - Never invent a person's role.
   - Never invent a LinkedIn URL.
   - Do not use a company LinkedIn page as an individual's
     LinkedIn profile.
   - If a person does not have an explicitly supported
     LinkedIn URL, return an empty string for linkedin_url.
   - If no reliable leadership or team information is found,
     return an empty list.

5. Confidence Score

   - Give a score between 0.0 and 1.0.
   - Higher score means the extracted information is more
     complete, consistent, and directly supported by the
     provided evidence.
   - Lower the score when information is incomplete,
     ambiguous, or supported only by limited external
     evidence.

IMPORTANT RULES:

- Use ONLY information contained in the provided evidence.
- Do not use outside knowledge.
- Do not guess.
- Do not invent information.
- Prefer direct company website evidence over external
  search evidence.
- External search evidence is supplementary only.
- Return every field required by the schema.
- Use empty lists when no contact points or leadership
  members are found.
- Use an empty string for linkedin_url when a LinkedIn URL
  is unavailable or unsupported.
- Return structured JSON matching the provided schema exactly.

PROVIDED COMPANY RESEARCH EVIDENCE:

{company_text}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful company intelligence "
                    "extraction agent. Use only the supplied "
                    "company research evidence. Prefer direct "
                    "company website evidence and use external "
                    "search evidence only as supplementary "
                    "evidence. Never invent information."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "company_intelligence",
                "strict": True,
                "schema": CompanyIntelligence.model_json_schema(),
            },
        },
    )

    # -----------------------------------------------------
    # Extract usage information
    # -----------------------------------------------------

    usage = response.usage

    if usage is None:
        raise ValueError(
            "LLM response did not include token usage information."
        )

    input_tokens = usage.prompt_tokens
    output_tokens = usage.completion_tokens
    total_tokens = usage.total_tokens

    estimated_cost = calculate_estimated_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    usage_info = {
        "model": MODEL_NAME,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(
            estimated_cost,
            8,
        ),
    }

    # -----------------------------------------------------
    # Parse and validate structured output
    # -----------------------------------------------------

    raw_result = response.choices[0].message.content

    if not raw_result:
        raise ValueError(
            "LLM returned an empty response."
        )

    result = json.loads(
        raw_result
    )

    validated_result = CompanyIntelligence.model_validate(
        result
    )

    return (
        validated_result,
        usage_info,
    )


# ---------------------------------------------------------
# Independent test
# ---------------------------------------------------------

if __name__ == "__main__":

    test_text = """
    DIRECT COMPANY WEBSITE EVIDENCE:

    Postman is an API platform that helps developers and teams
    design, build, test and collaborate on APIs.

    Postman is used by software developers, engineering teams,
    API teams and organizations.

    The platform provides tools for API development and testing.


    EXTERNAL SEARCH EVIDENCE:

    Search result:
    Title: Postman
    URL: https://www.linkedin.com/company/postman-platform

    The result identifies Postman as a software development
    company and provides a public company LinkedIn page.
    """

    print(
        "Sending test data to Groq..."
    )

    result, usage = extract_company_intelligence(
        test_text
    )

    print(
        "\n========== AI RESULT =========="
    )

    print(
        result.model_dump_json(
            indent=2
        )
    )

    print(
        "\n========== TOKEN USAGE =========="
    )

    print(
        json.dumps(
            usage,
            indent=2,
        )
    )