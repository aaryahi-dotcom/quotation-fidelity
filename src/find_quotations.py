"""
Find candidate quotations from extracted PDF text for each theme.
"""
import json
import re

THEME_KEYWORDS = {
    "revenue_growth": [
        r"\b(revenue|sales|turnover|income)\b.*\b(increas|grow|rise|higher)\b",
        r"\b(profit|earnings|net income)\b.*\b(increas|grow|rise|higher)\b",
        r"\bgrowth\b.*\b(revenue|sales|earnings|profit)\b",
    ],
    "revenue_decline": [
        r"\b(revenue|sales|turnover|income)\b.*\b(declin|fall|drop|lower|reduc)\b",
        r"\b(profit|earnings|net income)\b.*\b(declin|fall|drop|lower|reduc)\b",
        r"\b(contraction|slowdown|weakness)\b",
    ],
    "asset_quality": [
        r"\b(NPA|non-performing asset|impaired asset|loan loss)\b",
        r"\b(asset quality|credit quality|portfolio quality)\b",
        r"\b(default|delinquent|stressed asset)\b",
    ],
    "regulatory_breach": [
        r"\b(regulatory|compliance|violation|breach|sanction)\b",
        r"\b(audit observation|audit finding|audit qualification)\b",
        r"\b(governance|internal control|audit committee)\b",
    ],
    "cash_flow_pressure": [
        r"\b(cash flow|liquidity|working capital)\b.*\b(pressure|stress|tight|constrain)\b",
        r"\b(debt|borrowing|loan repayment)\b.*\b(challenge|pressure|burden)\b",
        r"\b(cash equivalents|liquid assets)\b.*\b(declin|reduc|lower)\b",
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
