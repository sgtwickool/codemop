import json
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

def extract_suggestions_from_text(text: str) -> List[Dict[str, Any]]:
    """Fallback method to extract suggestions from plain text response"""
    suggestions = []
    lines = text.split('\n')
    
    current_suggestion = {}
    in_suggestion = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if "line" in line.lower() and "number" in line.lower():
            if current_suggestion:
                suggestions.append(current_suggestion)
            current_suggestion = {"confidence": 0.7}
            in_suggestion = True
            
            # Extract line number
            try:
                line_num = int(''.join(filter(str.isdigit, line)))
                current_suggestion["line_number"] = line_num
            except:
                current_suggestion["line_number"] = 1
        elif in_suggestion and ":" in line and not current_suggestion.get("description"):
            current_suggestion["description"] = line.split(":", 1)[1].strip()
        elif in_suggestion and (line.startswith("Fix:") or line.startswith("fix:")):
            current_suggestion["fix"] = line.split(":", 1)[1].strip()
        elif in_suggestion and line.startswith("File:"):
            current_suggestion["file_path"] = line.split(":", 1)[1].strip()
    
    if current_suggestion:
        suggestions.append(current_suggestion)
    
    return suggestions

def parse_ai_response(content: str) -> List[Dict[str, Any]]:
    """Parse AI response and extract suggestions"""
    try:
        suggestions_data = json.loads(content)
        suggestions = suggestions_data.get("suggestions", [])
        
        # Validate and normalize suggestions
        validated_suggestions = []
        for suggestion in suggestions:
            validated_suggestion = {
                "line_number": suggestion.get("line_number", 1),
                "file_path": suggestion.get("file_path", "unknown.py"),
                "description": suggestion.get("description", "No description"),
                "fix": suggestion.get("fix", "No fix provided"),
                "confidence": float(suggestion.get("confidence", 0.5))
            }
            validated_suggestions.append(validated_suggestion)
        
        return validated_suggestions
        
    except json.JSONDecodeError:
        logger.warning(f"AI response is not valid JSON, trying text extraction")
        return extract_suggestions_from_text(content)
    except Exception as e:
        logger.error(f"Error parsing AI response: {str(e)}")
        return []