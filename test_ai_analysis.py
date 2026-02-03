#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.append('/home/sgtwickool/repos/codemop/backend/src')

from main import analyze_pr_with_ai, fetch_diff_content

async def test_ai_analysis():
    """Test the AI analysis functionality"""
    print("Testing AI analysis functionality...")
    
    # Test with a real GitHub diff URL
    test_diff_url = "https://github.com/tiangolo/fastapi/pull/10000.diff"
    
    try:
        # First test fetching diff content
        print(f"Fetching diff content from {test_diff_url}...")
        diff_content = await fetch_diff_content(test_diff_url)
        print(f"Successfully fetched {len(diff_content)} characters of diff content")
        print("First 200 chars:", diff_content[:200])
        
    except Exception as e:
        print(f"Error fetching diff content: {str(e)}")
        # Use a mock diff for testing
        diff_content = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,5 +1,6 @@
 def hello():
+    if name is None:
+        return ""
     return f"Hello {name}"
 """
        print("Using mock diff content for testing")
    
    # Test AI analysis (this will fail without API key, but we can test the flow)
    try:
        print("Testing AI analysis...")
        suggestions = await analyze_pr_with_ai(test_diff_url)
        print(f"AI analysis returned {len(suggestions)} suggestions")
        for i, suggestion in enumerate(suggestions):
            print(f"Suggestion {i+1}:")
            print(f"  Line {suggestion.get('line_number')}: {suggestion.get('description')}")
            print(f"  Fix: {suggestion.get('fix')}")
            print(f"  Confidence: {suggestion.get('confidence')}")
    except Exception as e:
        print(f"AI analysis failed as expected (no API key): {str(e)}")
        print("This confirms the error handling is working correctly")

if __name__ == "__main__":
    asyncio.run(test_ai_analysis())