"""
Find candidate quotations from extracted PDF text for each theme.
"""
import json
import re

THEME_KEYWORDS = {
    "auditor qualifications and emphases of matter": [
        r"qualified opinion|emphasis of matter|qualification|adverse opinion|disclaimer of opinion|modified opinion",
    ],
    "related-party transactions": [
        r"related part(y|ies)",
    ],
    "promoter share pledging": [
        r"pledg",
    ],
    "going-concern disclosures": [
        r"going concern",
    ],
    "contingent liabilities and guarantees": [
        r"contingent liabilit|guarantee",
    ],
}

def find_sentences_for_theme(text, theme, limit=5):
    """Find sentence candidates for a given theme."""
    candidates = []
    sentences = re.split(r'[.!?]+', text)

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 20 or len(sentence) > 300:
            continue

        for pattern in THEME_KEYWORDS[theme]:
            if re.search(pattern, sentence, re.IGNORECASE):
                candidates.append(sentence)
                break

    # Remove duplicates and return top N
    unique = list(dict.fromkeys(candidates))
    return unique[:limit]

def main():
    with open("../data/all_text.json") as f:
        all_text = json.load(f)

    suggestions = {}
    for company, data in all_text.items():
        suggestions[company] = {}
        for theme in THEME_KEYWORDS.keys():
            candidates = find_sentences_for_theme(data["text"], theme, limit=3)
            suggestions[company][theme] = candidates
        print(f"✓ {company}: found candidates across all themes")

    with open("../data/quotation_suggestions.json", "w") as f:
        json.dump(suggestions, f, indent=2)

    print("\nSuggestions saved → data/quotation_suggestions.json")
    print(f"Total companies analyzed: {len(suggestions)}")

if __name__ == "__main__":
    main()
