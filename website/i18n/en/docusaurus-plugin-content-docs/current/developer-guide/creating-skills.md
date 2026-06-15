---
sidebar_position: 1
title: "Creating Skills"
description: "Learn how to create new Hermes skills from scratch or using templates"
---

# Creating Skills

This section guides you through the process of creating new Hermes skills, including using the standardized skill template for consistent development.

## Creating a Skill

There are two main approaches to creating a new Hermes skill:
1. Creating a skill from scratch by following the SKILL.md format and directory structure
2. Using the standardized skill template to ensure best practices and consistency

### Using the Skill Template

The Hermes skill template provides a starting point for creating new skills with built-in testing, linting, and documentation examples. This template lowers the barrier to creating new skills, ensures consistency across skills, and promotes best practices such as testing and linting.

#### Template Location

The skill template is located at:
`projects/hermes-agent/templates/skill_template/`

#### Steps to Use the Template

1. **Copy the template** 
   Duplicate the template directory to a new location under `skills/` or `optional-skills/` with your desired skill name:
   ```bash
   cp -r projects/hermes-agent/templates/skill_template skills/my-new-skill
   ```

2. **Rename the skill** 
   Update `skill.json` and `manifest.yaml` in the copied directory with your skill’s name, description, version, and author.

3. **Implement your skill** 
   - Edit `scripts/sample_skill.py` to implement the actual skill logic, or replace it with your own scripts.
   - Add any required `SKILL.md` following the [Skill authoring guide](./creating-skills.md#skill-md-format).
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

#### Template Contents

- `skill.json`: Basic skill metadata.
- `manifest.yaml`: Defines toolsets, context files, and the skill identifier.
- `context/README.md`: Documentation on how to use the template.
- `tests/`: Contains example unit tests using pytest.
- `scripts/`: Placeholder for skill‑specific scripts.
- `.flake8`: Flake8 configuration for consistent code style.
- `pyproject.toml`: Project configuration, dependencies, and test settings.
- `docs/`: Additional documentation examples.

#### Best Practices

- Keep skill logic in scripts or external tools; avoid complex Python in `SKILL.md`.
- Use environment variables for secrets (`required_environment_variables` in `SKILL.md`).
- Use config entries for non‑secret configuration (`metadata.hermes.config` in `SKILL.md`).
- Write unit tests that invoke the skill via the Hermes agent or directly test helper functions.
- Follow the [Skill Rulebook](./creating-skills.md#skill‑rulebook) for clarity, safety, and usability.

## Creating a Skill from Scratch

If you prefer to create a skill without using the template, follow these guidelines:

### SKILL.md Format

Every skill must have a `SKILL.md` file in its root directory with the following front matter:

```markdown
---
name: my-skill
description: Brief description of what this skill does
version: 1.0.0
author: Your Name
# Optional fields:
# platforms: [macos, linux]     # Restrict to specific OS platforms
# required_environment_variables:
#   - name: API_KEY
#     prompt: "Enter API key"
#     default: ""
#     help: "Description"
---
```

### Skill Directory Structure

A typical skill directory looks like this:

```text
my-skill/
├── SKILL.md               # Main instructions (required)
├── references/            # Additional documentation
├── scripts/               # Helper scripts
├── templates/             # Output formats
└── assets/                # Supplementary files
```

### Implementing Skill Logic

Skill logic can be implemented in:
- Shell commands directly in `SKILL.md` (for simple skills)
- Python scripts in the `scripts/` directory
- External tools and executables

### Testing Your Skill

While not required, it's recommended to test your skill:
- Manually test by loading the skill and invoking its functionality
- For script-based skills, add unit tests in a `tests/` directory
- Use the Hermes agent's testing facilities if available

### Publishing Your Skill

When your skill is ready, you can publish it to the Skills Hub:

```bash
hermes skills publish path/to/skill --to github --repo owner/repo
```

See the [Skills Hub](/docs/user-guide/features/skills#skills-hub) section for more details.