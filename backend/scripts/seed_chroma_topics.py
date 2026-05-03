from __future__ import annotations

import uuid

from app.services.chroma import init_chroma, get_or_create_collection

TOPICS_BY_COMPANY: dict[str, list[str]] = {
    "General": [
        "Should AI replace human jobs in services?",
        "Is remote work sustainable for high-performance teams?",
        "Should governments regulate social media algorithms?",
        "Are startup jobs better than MNC roles for freshers?",
        "Is coding still a must-have skill for all graduates?",
    ],
    "TCS": [
        "Can large IT services firms move from support to innovation-led growth?",
        "How should Indian IT companies prepare for AI-native delivery models?",
        "Is cloud migration value overestimated for traditional enterprises?",
        "Should engineering graduates specialize early or stay broad?",
        "Can process discipline coexist with product-style experimentation?",
    ],
    "Infosys": [
        "Should ethical AI checks be mandatory in enterprise software projects?",
        "How can Indian IT firms improve global consulting credibility?",
        "Is reskilling every 2 years realistic for software professionals?",
        "Do certifications matter more than project outcomes for campus hires?",
        "Can hybrid work preserve mentoring quality for new joiners?",
    ],
    "Deloitte": [
        "Is ESG reporting a compliance exercise or real strategy lever?",
        "Should consulting prioritize impact measurement over slide quality?",
        "Can data-driven policy consulting improve public-sector execution?",
        "Is sustainability profitable in the short term for Indian businesses?",
        "How should firms balance profitability with climate commitments?",
    ],
    "Accenture": [
        "Will generative AI reduce consulting team sizes permanently?",
        "How can enterprises adopt AI without increasing operational risk?",
        "Should digital transformation be centralized or business-led?",
        "Can platform strategy outperform custom software in large enterprises?",
        "Is change management the biggest bottleneck in transformation programs?",
    ],
}


def seed_topics() -> int:
    client = init_chroma()
    collection = get_or_create_collection(client)
    if collection is None:
        print("ChromaDB unavailable. Install chromadb to seed topics.")
        return 0

    inserted = 0
    for company, topics in TOPICS_BY_COMPANY.items():
        ids = [f"topic-{company}-{uuid.uuid4().hex[:10]}" for _ in topics]
        metadatas = [{"company": company, "source": "seed"} for _ in topics]
        collection.add(ids=ids, documents=topics, metadatas=metadatas)
        inserted += len(topics)

    print(f"Seeded {inserted} topics into collection.")
    return inserted


if __name__ == "__main__":
    seed_topics()
