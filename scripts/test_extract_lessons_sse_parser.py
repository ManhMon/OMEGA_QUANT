import json

from extract_lessons import _parse_chat_completions_response_text


standard_response = json.dumps(
    {
        "choices": [
            {
                "message": {
                    "content": '{"symptom":"s","root_cause":"r","fix_pattern":"f"}'
                }
            }
        ]
    }
)
assert _parse_chat_completions_response_text(standard_response)["choices"][0]["message"]["content"] == '{"symptom":"s","root_cause":"r","fix_pattern":"f"}'


sse_response = "\n".join(
    [
        'data: {"choices":[{"delta":{"content":"{"}}]}',
        'data: {"choices":[{"delta":{"content":"\\"symptom\\":\\"s\\","}}]}',
        'data: {"choices":[{"delta":{"content":"\\"root_cause\\":\\"r\\","}}]}',
        'data: {"choices":[{"delta":{"content":"\\"fix_pattern\\":\\"f\\"}"}}]}',
        'data: [DONE]',
    ]
)
assert _parse_chat_completions_response_text(sse_response)["choices"][0]["message"]["content"] == '{"symptom":"s","root_cause":"r","fix_pattern":"f"}'
