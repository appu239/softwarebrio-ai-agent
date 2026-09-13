from pydantic import BaseModel, Field
from typing import List


class LeadershipMember(BaseModel):
    name: str
    role: str
    linkedin_url: str | None = None


class CompanyIntelligence(BaseModel):
    company_overview: str = Field(
        description="A concise two-sentence overview of the company."
    )

    target_audience: str = Field(
        description="The company's target audience or ideal customer profile."
    )

    contact_points: List[str] = Field(
        default_factory=list,
        description="Generic or public email addresses found on the website."
    )

    leadership: List[LeadershipMember] = Field(
        default_factory=list,
        description="Important leadership or team members discovered."
    )

    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the extracted information, from 0.0 to 1.0."
    )