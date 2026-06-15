# Implementation Plan: Project Template System for Workspace

## Summary of the change
This feature adds a workspace capability that provides predefined project templates (e.g., web development, data analysis, DevOps) with pre-configured skills, context files, and toolsets. Users can select a template when starting a new project, reducing setup time and ensuring best practices.

## Files to modify
- `/srv/projects/hermes-agent/skills/workspace/template_skill/` (new directory)
- `/srv/projects/hermes-agent/skills/workspace/template_skill/SKILL.md`
- `/srv/projects/hermes-agent/skills/workspace/template_skill/templates/` (directory with template files)
- `/srv/projects/hermes-agent/config/workspace_templates.yaml` (new configuration file)
- `/srv/projects/hermes-agent/hermes/cli.py` (to add a new command for template selection)
- `/srv/projects/hermes-agent/hermes/commands/template.py` (new command implementation)

## Step‑by‑step implementation instructions
1. Create the skill directory for the template skill under `skills/workspace/template_skill/`.
2. Write the SKILL.md for the template skill, describing how to provide and apply templates.
3. Create the `templates/` subdirectory and add sample template files for web development, data analysis, and DevOps.
4. Create `config/workspace_templates.yaml` to define the available templates and their properties.
5. Modify `hermes/cli.py` to add a new `template` command group and subcommands like `list`, `use`, `create`.
6. Implement the command logic in `hermes/commands/template.py` to handle template listing, selection, and application.
7. Update the skill loader to automatically load the new template skill.
8. Test the feature by creating a new project using a template and verifying that the pre-configured skills and files are applied.
9. Document the feature in the workspace documentation.

## Test cases to verify
- Test that `hermes template list` shows the available templates.
- Test that `hermes template use <template_name>` applies the template to the current workspace.
- Test that after applying a template, the expected skills are available and the template files are present.
- Test that the template does not overwrite existing user files unless explicitly configured.
- Test that the template skill can be loaded and unloaded without errors.

## Rollback procedure
To rollback the changes:
1. Remove the `skills/workspace/template_skill/` directory.
2. Delete the `config/workspace_templates.yaml` file.
3. Remove the template-related code from `hermes/cli.py` and delete `hermes/commands/template.py`.
4. Remove any references to the template skill from the skill loader configuration.
5. Restart the Hermes agent to ensure the changes are fully reverted.
