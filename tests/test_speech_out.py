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


# A fake browser where the audio for the sentence arrives late, as Abena's often does.
WAITING = """
globalThis.window = globalThis;
const log = [];
globalThis.Audio = class { pause() {} play() { log.push("play"); this.onplaying(); this.onended(); return Promise.resolve(); } };
globalThis.speechSynthesis = { cancel() {}, speak() { log.push("browser voice"); } };
const { Player } = await import(process.argv[2]);
const player = new Player({
  onStart() { log.push("start waiting=" + player.waiting); },
  onIdle() { console.log(JSON.stringify(log)); },
  onWait() { log.push("wait waiting=" + player.waiting); },
});
player.enqueue("Me ho ye.", new Promise((deliver) => setTimeout(deliver, 300, { audio: "AAAA", mime: "audio/wav" })));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_slow_abena_audio_is_waited_for_and_the_page_is_told(tmp_path):
    driver = tmp_path / "driver.mjs"
    driver.write_text(WAITING)
    result = subprocess.run(
        ["node", str(driver), SCRIPT.as_uri()], capture_output=True, text=True, timeout=40
    )
    assert result.stdout.strip() == '["wait waiting=true","play","start waiting=false"]', result.stderr
