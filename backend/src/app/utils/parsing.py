import json
from typing import List, Dict, Any, Optional
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
            # (no digits means no line number; the suggestion is then dropped as incomplete)
            digits = ''.join(filter(str.isdigit, line))
            if digits:
                current_suggestion["line_number"] = int(digits)
        elif in_suggestion and ":" in line and not current_suggestion.get("description"):
            current_suggestion["description"] = line.split(":", 1)[1].strip()
        elif in_suggestion and (line.startswith("Fix:") or line.startswith("fix:")):
            current_suggestion["fix"] = line.split(":", 1)[1].strip()
        elif in_suggestion and line.startswith("File:"):
            current_suggestion["file_path"] = line.split(":", 1)[1].strip()
    
    if current_suggestion:
        suggestions.append(current_suggestion)
    
    return suggestions

def normalize_suggestion(suggestion: Any) -> Optional[Dict[str, Any]]:
    """
    A suggestion in the shape that's stored, or None if it doesn't say where (file and line)
    and what (description). Missing locations aren't made up; the suggestion is dropped.
    """
    if not isinstance(suggestion, dict):
        return None
    line_number = suggestion.get("line_number")
    file_path = suggestion.get("file_path")
    description = suggestion.get("description")
    if not isinstance(line_number, int) or not file_path or not description:
        return None
    
    confidence = suggestion.get("confidence")
    try:
        confidence = 0.5 if confidence is None else float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5
    
    return {
        "line_number": line_number,
        "file_path": str(file_path),
        "description": str(description),
        "fix": suggestion.get("fix") or "No fix provided",
        "confidence": confidence,
    }

def parse_ai_response(content: str) -> List[Dict[str, Any]]:
    """Parse an AI response into complete suggestions, dropping incomplete ones"""
    try:
        data = json.loads(content)
        raw_suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
    except json.JSONDecodeError:
        logger.warning("AI response is not valid JSON, trying text extraction")
        raw_suggestions = extract_suggestions_from_text(content)
    if not isinstance(raw_suggestions, list):
        raw_suggestions = []
    
    suggestions = [s for s in map(normalize_suggestion, raw_suggestions) if s is not None]
    if len(suggestions) < len(raw_suggestions):
        logger.warning(f"Dropped {len(raw_suggestions) - len(suggestions)} incomplete suggestions from the AI response")
    return suggestions
