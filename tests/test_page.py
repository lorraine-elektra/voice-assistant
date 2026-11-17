def test_page_is_served_with_its_controls(client):
    response = client.get("/")
    assert response.status_code == 200
    for needed in ('id="mic"', 'id="status"', 'id="transcript"', 'id="text"', 'id="stop"'):
        assert needed in response.text


def test_scripts_and_styles_are_served(client):
    names = ("app.js", "speech-in.js", "speech-in-whisper.js", "speech-out.js", "mic.js",
             "pcm-worklet.js", "style.css", "choices.js")
    for name in names:
        assert client.get(f"/static/{name}").status_code == 200


def test_page_never_contains_a_key(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "sk-secret-test-value")
    pages = [client.get("/").text] + [client.get(f"/static/{n}").text for n in ("app.js", "mic.js")]
    assert not any("sk-secret-test-value" in page for page in pages)


def test_page_has_the_state_strip_and_latency_bar(client):
    page = client.get("/").text
    for needed in ('id="wave"', 'id="latency-bar"', 'id="latency-text"'):
        assert needed in page


def test_fonts_are_served_from_the_app(client):
    css = client.get("/static/style.css").text
    assert "fonts.googleapis.com" not in css
    for name in ("familjen-grotesk-latin-400-normal.woff2", "familjen-grotesk-latin-500-normal.woff2",
                 "familjen-grotesk-latin-700-normal.woff2", "young-serif-latin-400-normal.woff2"):
        assert name in css
        assert client.get(f"/static/fonts/{name}").status_code == 200


def test_page_has_the_setup_form_and_both_robots(client):
    page = client.get("/").text
    for needed in ('id="name"', 'name="gender"', 'value="woman"', 'value="man"', 'id="you-robot"', 'id="bot-robot"'):
        assert needed in page
    assert client.get("/static/robot.js").status_code == 200


def test_page_has_the_language_and_voice_pickers(client):
    page = client.get("/").text
    assert 'id="language"' in page and 'id="voice"' in page
    # The page sends the choice to the backend, see docs/protocol.md.
    assert '"settings"' in client.get("/static/choices.js").text


def test_page_stores_nothing_in_the_browser(client):
    for name in ("app.js", "choices.js", "mic.js", "speech-out.js", "robot.js"):
        script = client.get(f"/static/{name}").text
        assert "localStorage" not in script and "sessionStorage" not in script
