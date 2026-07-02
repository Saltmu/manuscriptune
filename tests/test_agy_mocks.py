from src.utils.ai_client import AgyClient


def test_mock_agy_client(mock_agy_client):
    # AgyClient.generate() がモックされているか検証
    client = AgyClient()
    response = client.generate("hello")
    assert response == "Mocked Response"

    # AgyClient.list_models() がモックされているか検証
    models = AgyClient.list_models()
    assert "Mocked Model" in models
