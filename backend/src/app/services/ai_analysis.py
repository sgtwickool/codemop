import logging
from typing import List, Dict, Any
from app.config import settings
from app.utils import http
from app.utils.parsing import parse_ai_response

logger = logging.getLogger(__name__)

async def analyze_diff(diff_content: str) -> List[Dict[str, Any]]:
    """
    Ask the AI model to review a diff, returning its code suggestions
    Uses chat completions API with structured prompting for code analysis
    (Failures propagate; the background job logs them with the PR they were for)
    """
    suggestions = await call_ai_api(create_ai_prompt(diff_content))
    logger.info(f"✅ AI analysis completed: {len(suggestions)} suggestions")
    return suggestions

def create_ai_prompt(diff_content: str) -> str:
    """Create AI prompt for code analysis"""
    # Limit to first 10k characters to avoid token limits
    limited_diff = diff_content[:10000]
    
    return f"""You are an expert code reviewer. Analyze the following code diff and provide specific suggestions for improvements, bug fixes, and best practices.

Requirements:
1. Focus on real issues: bugs, security vulnerabilities, performance problems
2. Provide actionable suggestions with specific line numbers
3. Include confidence scores (0.0-1.0) for each suggestion
4. Return suggestions in JSON format only

Code Diff:
```
{limited_diff}
```

Response Format:
{{
  "suggestions": [
    {{
      "line_number": 42,
      "file_path": "filename.py",
      "description": "Description of the issue",
      "fix": "Suggested fix code",
      "confidence": 0.95
    }}
  ]
}}

Only return valid JSON, no additional text."""

async def call_ai_api(prompt: str) -> List[Dict[str, Any]]:
    """Call AI API and process response"""
    headers = {
        "Authorization": f"Bearer {settings.AI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": settings.AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful code review assistant that provides specific, actionable suggestions for code improvements."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    response = await http.fetch_with_retry(
        settings.AI_API_URL,
        "POST",
        headers=headers,
        json=payload
    )
    
    # Parse the response
    data = response.json()
    
    # Extract the AI's response content
    if 'choices' in data and len(data['choices']) > 0:
        content = data['choices'][0]['message']['content']
        return parse_ai_response(content)
    else:
        logger.warning(f"Unexpected AI API response format: {data}")
        return []