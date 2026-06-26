import requests
import json

doi = "10.3390/a17110521"

url = f"https://api.openalex.org/works?filter=doi:{doi}"

data = requests.get(url).json()

paper = data["results"][0]

print(json.dumps(
    {
        "title": paper["title"],
        "cited_by_count": paper.get("cited_by_count"),
        "referenced_works_count": paper.get("referenced_works_count"),
        "fwci": paper.get("fwci"),
        "doi": paper.get("doi"),
        "id": paper.get("id")
    },
    indent=4,
    ensure_ascii=False
))