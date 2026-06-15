# Usage Example: Creating a “Greeter” Skill

This example shows how to use the skill template to create a simple skill that greets the user.

## Step 1: Copy the Template
```bash
cp -r projects/hermes-agent/templates/skill_template skills/greeter
```

## Step 2: Update Metadata
Edit `skills/greeter/skill.json`:
```json
{
  "name": "greeter",
  "description": "A simple skill that greets the user.",
  "version": "1.0.0",
  "author": "Your Name"
}
```
Edit `skills/greeter/manifest.yaml` similarly.

## Step 3: Implement the Skill
Replace `skills/greeter/scripts/sample_skill.py` with:
```python
#!/usr/bin/env python3
import os

def main():
    name = os.environ.get("GREETING_NAME", "World")
    print(f"Hello, {name}! Welcome to Hermes.")
    return 0

if __name__ == "__main__":
    main()
```
Add an environment variable definition in `SKILL.md` (see below).

## Step 4: Add SKILL.md
Create `skills/greeter/SKILL.md`:
```markdown
---
name: greeter
description: Greets the user with a customizable message.
version: 1.0.0
author: Your Name
required_environment_variables:
  - name: GREETING_NAME
    prompt: "What name should the greeter use?"
    default: "World"
    help: "The name to include in the greeting."
---

# Greeter Skill

This skill prints a friendly greeting.

## When to Use
Use this skill whenever you want a friendly greeting.

## Quick Reference
- No special commands; the skill runs automatically when loaded.

## Procedure
The skill reads the `GREETING_NAME` environment variable and prints a greeting.

## Verification
The agent will observe the printed greeting in the terminal output.
```

## Step 5: Test and Lint
```bash
cd skills/greeter
pytest
flake8
```

## Step 6: Load the Skill
In a Hermes session, run:
```bash
/hermes skills load greeter
```
Or restart Hermes with the skill enabled via `hermes skills enable`.

## Step 7: Publish (Optional)
When ready, publish to the Skills Hub:
```bash
hermes skills publish skills/greeter --to github --repo yourusername/greeter-skill
```
```