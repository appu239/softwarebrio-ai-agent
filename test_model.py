from models import CompanyIntelligence


data = CompanyIntelligence(
    company_overview="This is a software company that provides developer tools.",
    target_audience="Software developers and engineering teams.",
    contact_points=["hello@example.com"],
    leadership=[],
    confidence_score=0.90
)

print(data.model_dump_json(indent=2))