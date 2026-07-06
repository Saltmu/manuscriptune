import os
import re
from typing import Any

import yaml


class SkillValidationError(Exception):
    """Exception raised when skill validation fails."""

    pass


class Skill:
    """Represents a validated skill configuration loaded from a SKILL.md file."""

    def __init__(
        self,
        name: str,
        version: str,
        description: str,
        category: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        dependencies: list[dict[str, Any]] | None = None,
        skill_path: str = "",
    ):
        self.name = name
        self.version = version
        self.description = description
        self.category = category
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.dependencies = dependencies or []
        self.skill_path = skill_path


class SkillValidator:
    """Helper class to validate the format and content of skills."""

    @staticmethod
    def parse_version(version_str: str) -> tuple[int, int, int]:
        """Parses a version string like '1.2.3' into a tuple of (major, minor, patch)."""
        # Remove any leading 'v'
        version_str = version_str.lstrip("v")
        # Split by dots
        parts = version_str.split(".")
        # Fill missing parts with '0'
        while len(parts) < 3:
            parts.append("0")

        try:
            # Parse only digits (ignoring any pre-release suffix like '-beta' for simplicity)
            major = int(re.search(r"\d+", parts[0]).group())  # type: ignore
            minor = int(re.search(r"\d+", parts[1]).group())  # type: ignore
            patch = int(re.search(r"\d+", parts[2]).group())  # type: ignore
            return (major, minor, patch)
        except (ValueError, AttributeError) as e:
            raise SkillValidationError(
                f"Invalid version string format: '{version_str}'. Detail: {e}"
            )

    @staticmethod
    def compare_versions(version_str: str, spec_str: str) -> bool:
        """Checks if version_str satisfies the spec_str (e.g., '>=1.0.0', '^1.2.0', '==2.0.0')."""
        import operator as py_op

        spec_str = spec_str.strip()

        # Determine operator and target version string
        operator = "=="
        target_version_str = spec_str

        for op in [">=", "<=", "==", "^", ">", "<"]:
            if spec_str.startswith(op):
                operator = op
                target_version_str = spec_str[len(op) :].strip()
                break

        v_tuple = SkillValidator.parse_version(version_str)
        spec_tuple = SkillValidator.parse_version(target_version_str)

        if operator == "^":
            # Caret comparison: allows changes that do not modify the left-most non-zero element
            if spec_tuple[0] > 0:
                # ^1.2.3: [1.2.3, 2.0.0)
                upper_bound = (spec_tuple[0] + 1, 0, 0)
            elif spec_tuple[1] > 0:
                # ^0.2.3: [0.2.3, 0.3.0)
                upper_bound = (0, spec_tuple[1] + 1, 0)
            else:
                # ^0.0.3: [0.0.3, 0.0.4)
                upper_bound = (0, 0, spec_tuple[2] + 1)

            return spec_tuple <= v_tuple < upper_bound

        ops = {
            "==": py_op.eq,
            ">=": py_op.ge,
            "<=": py_op.le,
            ">": py_op.gt,
            "<": py_op.lt,
        }

        if operator in ops:
            return bool(ops[operator](v_tuple, spec_tuple))

        return False

    @staticmethod
    def validate_schema(schema: dict[str, Any], field_name: str) -> None:
        """Validates that a schema is a dictionary with a valid 'type' key."""
        if not isinstance(schema, dict):
            raise SkillValidationError(f"Field '{field_name}' must be a dictionary.")
        # We allow empty schemas for developer/generic skills
        if not schema and field_name in ("input_schema", "output_schema"):
            return

        if "type" not in schema:
            raise SkillValidationError(
                f"Schema in '{field_name}' must contain a 'type' field."
            )

        valid_types = {
            "object",
            "array",
            "string",
            "number",
            "integer",
            "boolean",
            "null",
        }
        if schema["type"] not in valid_types:
            raise SkillValidationError(
                f"Schema type '{schema['type']}' in '{field_name}' is invalid. "
                f"Must be one of {valid_types}."
            )

    @staticmethod
    def validate_frontmatter(fm: dict[str, Any]) -> None:
        """Validates that all required fields and correct formats exist in frontmatter."""
        required_fields = ["name", "version", "input_schema", "output_schema"]
        for field in required_fields:
            if field not in fm:
                raise SkillValidationError(
                    f"Missing required field '{field}' in frontmatter."
                )

        if not isinstance(fm["name"], str) or not fm["name"].strip():
            raise SkillValidationError("Field 'name' must be a non-empty string.")

        if not isinstance(fm["version"], str) or not fm["version"].strip():
            raise SkillValidationError("Field 'version' must be a non-empty string.")

        # Parse version just to validate format
        SkillValidator.parse_version(fm["version"])

        # Validate schemas
        SkillValidator.validate_schema(fm["input_schema"], "input_schema")
        SkillValidator.validate_schema(fm["output_schema"], "output_schema")

        # Optional validation
        if "description" in fm and not isinstance(fm["description"], str):
            raise SkillValidationError("Field 'description' must be a string.")

        if "category" in fm and not isinstance(fm["category"], str):
            raise SkillValidationError("Field 'category' must be a string.")

        if "dependencies" in fm:
            if not isinstance(fm["dependencies"], list):
                raise SkillValidationError("Field 'dependencies' must be a list.")
            for dep in fm["dependencies"]:
                if not isinstance(dep, dict):
                    raise SkillValidationError(
                        "Each dependency item must be a dictionary."
                    )
                if "name" not in dep or "version" not in dep:
                    raise SkillValidationError(
                        "Each dependency must contain 'name' and 'version' keys."
                    )
                if not isinstance(dep["name"], str) or not isinstance(
                    dep["version"], str
                ):
                    raise SkillValidationError(
                        "Dependency 'name' and 'version' must be strings."
                    )


class SkillRegistry:
    """Manages parsing, validating, loading and dependency resolving for all skills."""

    def load_skill_from_file(self, skill_md_path: str) -> Skill:
        """Parses and validates a single SKILL.md file, returning a Skill instance."""
        if not os.path.exists(skill_md_path):
            raise SkillValidationError(f"SKILL.md not found at '{skill_md_path}'")

        try:
            with open(skill_md_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            raise SkillValidationError(f"Failed to read file '{skill_md_path}': {e}")

        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            raise SkillValidationError(
                f"Frontmatter not found (missing --- markers) in '{skill_md_path}'"
            )

        frontmatter_str = match.group(1)
        try:
            fm = yaml.safe_load(frontmatter_str)
        except Exception as e:
            raise SkillValidationError(
                f"Failed to parse frontmatter YAML in '{skill_md_path}': {e}"
            )

        if not isinstance(fm, dict):
            raise SkillValidationError(
                f"Frontmatter is not a dictionary in '{skill_md_path}'"
            )

        SkillValidator.validate_frontmatter(fm)

        return Skill(
            name=fm["name"],
            version=fm["version"],
            description=fm.get("description", ""),
            category=fm.get("category", ""),
            input_schema=fm["input_schema"],
            output_schema=fm["output_schema"],
            dependencies=fm.get("dependencies", []),
            skill_path=os.path.dirname(skill_md_path),
        )

    def load_skills(self, skills_dir: str) -> dict[str, Skill]:
        """Loads and validates all skills under the given skills directory."""
        skills: dict[str, Skill] = {}
        if not os.path.exists(skills_dir) or not os.path.isdir(skills_dir):
            return skills

        for entry in os.scandir(skills_dir):
            if entry.is_dir():
                skill_md_path = os.path.join(entry.path, "SKILL.md")
                if os.path.exists(skill_md_path):
                    try:
                        skill = self.load_skill_from_file(skill_md_path)
                        skills[skill.name] = skill
                    except SkillValidationError as e:
                        raise SkillValidationError(
                            f"Skill validation failed for '{entry.name}': {e}"
                        )
        return skills

    def check_dependencies(self, skills: dict[str, Skill]) -> None:
        """Validates that all loaded skills satisfy their version-controlled dependencies."""
        for skill in skills.values():
            for dep in skill.dependencies:
                dep_name = dep["name"]
                dep_ver_req = dep["version"]

                if dep_name not in skills:
                    raise SkillValidationError(
                        f"Dependency '{dep_name}' not found for skill '{skill.name}'."
                    )

                target_skill = skills[dep_name]
                if not SkillValidator.compare_versions(
                    target_skill.version, dep_ver_req
                ):
                    raise SkillValidationError(
                        f"Version requirement '{dep_ver_req}' for '{dep_name}' not met. "
                        f"Found version '{target_skill.version}' (required by skill '{skill.name}')."
                    )

    def validate_all(self, skills_dir: str) -> tuple[bool, list[str]]:
        """Scans, loads, and checks dependencies for all skills.

        Returns a tuple of (success_boolean, list_of_error_strings).
        """
        errors = []
        try:
            skills = self.load_skills(skills_dir)
            self.check_dependencies(skills)
        except SkillValidationError as e:
            errors.append(str(e))
            return False, errors
        except Exception as e:
            errors.append(f"Unexpected error validating skills: {e}")
            return False, errors

        return True, []
