from src.utils.ai_model_parser import AgyModelParser


def test_parse_models_output():
    stdout = (
        "\x1b[32m⣾\x1b[0m Gemini 3.5 Flash (High)\n⣽ Gemini 3.5" " Flash (Medium)\n"
    )
    models = AgyModelParser.parse_models_output(stdout)
    assert models == ["Gemini 3.5 Flash (High)", "Gemini 3.5 Flash (Medium)"]


def test_parse_models_output_empty():
    stdout = ""
    models = AgyModelParser.parse_models_output(stdout)
    assert models == []
