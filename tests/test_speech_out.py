"""The browser fallback voice must still speak when the browser has no voice for the language."""
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "app" / "static" / "speech-out.js"

# A fake browser: speaking with any language set fails, as when no voice is installed for it.
DRIVER = """
globalThis.window = globalThis;
globalThis.Audio = class { pause() {} };
const spoken = [];
globalThis.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
globalThis.speechSynthesis = {
  cancel() {},
  speak(u) {
    setTimeout(() => {
      if (u.lang) return u.onerror({ error: "language-unavailable" });
      spoken.push(u.text);
      u.onstart(); u.onend();
    }, 0);
  },
};
const { Player } = await import(process.argv[2]);
const player = new Player({ onStart() {}, onIdle() { console.log(JSON.stringify(spoken)); } });
player.lang = "es-ES";
player.enqueue("Hola");
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_language_with_no_browser_voice_is_still_spoken(tmp_path):
    driver = tmp_path / "driver.mjs"
    driver.write_text(DRIVER)
    result = subprocess.run(
        ["node", str(driver), SCRIPT.as_uri()], capture_output=True, text=True, timeout=20
    )
    assert result.stdout.strip() == '["Hola"]', result.stderr
