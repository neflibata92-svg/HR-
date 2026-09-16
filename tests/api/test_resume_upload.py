def test_upload_txt_resume(client, auth_headers, tmp_path) -> None:
    file_path = tmp_path / "cv.txt"
    file_path.write_text("熟悉 Python 与招聘系统", encoding="utf-8")
    with file_path.open("rb") as handle:
        response = client.post(
            "/api/resumes/upload",
            headers=auth_headers,
            files={"file": ("cv.txt", handle, "text/plain")},
            data={"source": "upload"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["parse_status"] == "ok"
    assert "Python" in body["parsed_text"]
    assert body["source"] == "upload"


def test_upload_image_skipped(client, auth_headers, tmp_path) -> None:
    file_path = tmp_path / "cv.png"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    with file_path.open("rb") as handle:
        response = client.post(
            "/api/resumes/upload",
            headers=auth_headers,
            files={"file": ("cv.png", handle, "image/png")},
            data={"source": "upload"},
        )
    assert response.status_code == 200
    assert response.json()["parse_status"] == "skipped_image"
