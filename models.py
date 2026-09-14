from pydantic import BaseModel, ConfigDict, Field


class LeadershipMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description="Full name of the leadership or team member."
    )

    role: str = Field(
        description="Job title or role of the leadership or team member."
    )

    linkedin_url: str = Field(
        description=(
            "LinkedIn profile URL if explicitly found in the website content. "
            "Use an empty string if unavailable."
        )
    )


class CompanyIntelligence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_overview: str = Field(
        description="A concise two-sentence overview of the company."
    )

    target_audience: str = Field(
        description="The company's target audience or ideal customer profile."
    )

    contact_points: list[str] = Field(
        description=(
            "Generic or public email addresses explicitly found "
            "in the website content."
        )
    )

    leadership: list[LeadershipMember] = Field(
        description=(
            "Important leadership or team members discovered "
            "in the website content."
        )
    )

    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence in the extracted information, from 0.0 to 1.0."
        )
    )