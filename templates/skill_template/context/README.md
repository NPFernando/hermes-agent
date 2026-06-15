# Hermes Skill Template

This template provides a starting point for creating new Hermes skills with best practices.

## How to Use This Template

1. **Copy the template** 
   Duplicate this directory to a new location under `skills/` or `optional-skills/` with your desired skill name, e.g.:
   ```bash
   cp -r projects/hermes-agent/templates/skill_template skills/my-new-skill
   ```

2. **Rename the skill** 
   Update `skill.json` and `manifest.yaml` with your skill’s name, description, version, and author.

3. **Implement your skill** 
   - Edit `scripts/sample_skill.py` to implement the actual skill logic, or replace it with your own scripts.
   - Add any required `SKILL.md` following the [Skill authoring guide](../developer-guide/creating-skills.md).
   - Add unit tests in `tests/` that exercise your skill’s functionality.
   - Adjust linting configuration in `.flake8` if needed.

4. **Run tests** 
   From the skill directory, run:
   ```bash
   pytest
   ```

5. **Lint your code** 
   Run:
   ```bash
   flake8
   ```

6. **Build and publish** 
   Follow the standard Hermes skill publishing process:
   ```bash
   hermes skills publish path/to/skill --to github --repo owner/repo
   ```

## Template Contents

- `skill.json`: Basic skill metadata.
- `manifest.yaml`: Defines toolsets, context files, and the skill identifier.
- `context/README.md`: This file.
- `tests/`: Contains example unit tests using pytest.
- `scripts/`: Placeholder for skill‑specific scripts.
- `.flake8`: Flake8 configuration for consistent code style.
- `pyproject.toml`: Project configuration, dependencies, and test settings.
- `docs/`: Additional documentation examples.

## Best Practices

- Keep skill logic in scripts or external tools; avoid complex Python in `SKILL.md`.
- Use environment variables for secrets (`required_environment_variables` in `SKILL.md`).
- Use config entries for non‑secret configuration (`metadata.hermes.config` in `SKILL.md`).
- Write unit tests that invoke the skill via the Hermes agent or directly test helper functions.
- Follow the [Skill Rulebook](../developer-guide/creating-skills.md#skill‑rulebook) for clarity, safety, and usability.