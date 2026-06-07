# hw_checker setup

## What changed

Assignments now support a rule-engine mode backed by `hw_checker`.
If `check_mode=rule` and `rule_config_json` is set, submissions are executed and validated through `hw_checker` instead of the generic LLM review path.

## Local run

1. Install dependencies:

```powershell
pip install -r requirements.txt
```

2. Apply migrations:

```powershell
alembic upgrade head
```

3. Start the app:

```powershell
python -m main
```

## Configure an assignment rule

Use the API to switch a task to rule mode:

```powershell
curl -X PUT "http://localhost:8000/api/assignments/1/rules" `
  -H "Content-Type: application/json" `
  -d @examples/hw_checker_rule_example.json
```

If you prefer the bot flow, create the assignment normally and then update the rule payload through the API.

## Verify

1. Create or pick an assignment with `check_mode=rule`.
2. Upload a notebook or code submission containing `answer = ...` for the example rule.
3. Submit the work from Telegram.
4. Open the review in the teacher flow and confirm the annotation appears in `ReviewItem`.

## Notes

- Notebook submissions are executed in `hw_checker`'s sandbox path.
- Plain Python text is wrapped into a one-cell notebook for rule-engine checks.
- If `hw_checker` cannot be imported, the app falls back to the LLM review path.
