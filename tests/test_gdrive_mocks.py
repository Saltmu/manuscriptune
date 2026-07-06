def test_mock_gdrive_build(mock_gdrive_build):
    # googleapiclient.discovery.build がモックされているか検証
    from googleapiclient.discovery import build

    service = build("drive", "v3", credentials=None)

    assert service is not None

    # files().list().execute() がモック経由で動作することを確認
    service.files().list().execute.return_value = {
        "files": [{"id": "123", "name": "test.txt", "mimeType": "text/plain"}]
    }
    res = service.files().list().execute()
    assert res["files"][0]["name"] == "test.txt"
