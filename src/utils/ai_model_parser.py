import re


class AgyModelParser:
    """Parses output from agy models command."""

    @staticmethod
    def parse_models_output(stdout: str) -> list[str]:
        """Cleans and parses the output of `agy models`."""
        # Clean up output: remove ANSI escape codes, braille characters (spinners), etc.
        clean_stdout = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", stdout)
        lines = clean_stdout.strip().split("\n")
        models = []
        for line in lines:
            # Remove braille symbols (U+2800 - U+28FF)
            line_clean = re.sub(r"[\u2800-\u28ff]", "", line).strip()
            if line_clean:
                models.append(line_clean)
        return models
