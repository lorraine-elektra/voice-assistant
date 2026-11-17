def test_page_is_served_with_its_controls(client):
    response = client.get("/")
    assert response.status_code == 200
    for needed in ('id="mic"', 'id="status"', 'id="transcript"', 'id="text"', 'id="stop"'):
        assert needed in response.text


def test_scripts_and_styles_are_served(client):
    names = ("app.js", "speech-in.js", "speech-in-deepgram.js", "speech-out.js", "mic.js",
             "pcm-worklet.js", "style.css")
    for name in names:
        assert client.get(f"/static/{name}").status_code == 200


def test_page_never_contains_a_key(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-secret-test-value")
    pages = [client.get("/").text] + [client.get(f"/static/{n}").text for n in ("app.js", "mic.js")]
    assert not any("sk-secret-test-value" in page for page in pages)
