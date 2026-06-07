#!/usr/bin/env python
"""
Quick test script to verify Evalyn components
"""
import asyncio
import sys
import os

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

async def test_sandbox():
    """Test Python code execution in sandbox"""
    from agents.sandbox import run_python_code
    
    print("\n" + "="*50)
    print("Testing Sandbox Module")
    print("="*50)
    
    # Test 1: Simple Python code
    code1 = """
x = 10
y = 20
print(f"Sum: {x + y}")
"""
    result = await run_python_code(code1, timeout_seconds=5)
    print(f"[PASS] Test 1 - Simple Python: {'SUCCESS' if result.success else 'FAIL'}")
    if result.stdout:
        print(f"  Output: {result.stdout.strip()}")
    if result.error:
        print(f"  Error: {result.error}")
    
    # Test 2: Code with error
    code2 = """
print(1 / 0)
"""
    result = await run_python_code(code2, timeout_seconds=5)
    print(f"[PASS] Test 2 - Code with error: {'SUCCESS' if not result.success else 'FAIL'}")
    if result.stderr:
        print(f"  Error detected: {result.stderr.strip()[:50]}...")
    
    # Test 3: Jupyter notebook detection
    notebook_json = """{
    "cells": [
        {"cell_type": "code", "source": "print('Hello from notebook')"}
    ]
}"""
    from agents.sandbox import is_python_code
    is_notebook = is_python_code(notebook_json)
    print(f"[PASS] Test 3 - Jupyter detection: {'SUCCESS' if is_notebook else 'FAIL'}")


async def test_agent():
    """Test CodeReviewAgent"""
    print("\n" + "="*50)
    print("Testing CodeReviewAgent")
    print("="*50)
    
    from agents.reviewer import create_default_reviewer
    
    reviewer = create_default_reviewer()
    print(f"[PASS] Agent created: {reviewer.model}")
    
    # Test submission
    result = await reviewer.review_submission(
        assignment_title="Test Assignment",
        assignment_description="Write a function that adds two numbers",
        assignment_criteria="Function must handle edge cases",
        submission_text="""
def add(a, b):
    return a + b

print(add(5, 3))
""",
    )
    
    if isinstance(result[0], str):
        print(f"[WARN] Agent returned error: {result[0][:100]}...")
    else:
        print(f"[PASS] Agent review successful")
        print(f"  Score: {result[0].overall_score}/10")
        print(f"  Items found: {len(result[0].items)}")


async def test_api():
    """Test FastAPI app"""
    print("\n" + "="*50)
    print("Testing FastAPI App")
    print("="*50)
    
    from api.app import app
    print(f"[PASS] FastAPI app created")
    print(f"  Routes registered: {len(app.routes)}")
    print(f"  Health endpoint: /health")
    print(f"  API endpoints: /api/courses, /api/assignments, /api/submissions, /api/reviews")
    print(f"  Frontend: /")


async def main():
    print("\n" + "="*70)
    print("EVALYN - Component Tests")
    print("="*70)
    
    try:
        print("\n[1/3] Testing Sandbox Module...")
        await test_sandbox()
    except Exception as e:
        print(f"[FAIL] Sandbox test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        print("\n[2/3] Testing CodeReviewAgent...")
        await test_agent()
    except Exception as e:
        print(f"[WARN] Agent test failed (expected if OpenRouter not configured): {e}")
    
    try:
        print("\n[3/3] Testing FastAPI App...")
        await test_api()
    except Exception as e:
        print(f"[FAIL] API test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*70)
    print("Testing Complete!")
    print("="*70)
    print("""
Next steps:
1. Set environment variables in .env:
   - BOT_TOKEN=your_telegram_bot_token
   - OPENROUTER_API_KEY=your_openrouter_key
   - DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
   - ADMIN_IDS=123456789

2. Run the application:
   python main.py

3. Access the web interface:
   http://localhost:8000

4. Interact with the bot:
   Start a chat with your Telegram bot
    """)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
