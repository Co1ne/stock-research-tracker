def match_business_lines(text: str, lines: list[dict]) -> list[str]:
    result = []
    for line in lines:
        for keyword in (line.get('keywords') or []):
            if keyword and keyword in text:
                result.append(line['name'])
                break
    return result
