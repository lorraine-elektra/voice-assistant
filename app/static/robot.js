// The two robots: one for you, one for the assistant. Plain SVG, no images.
// Colours and movement come from style.css, so the shapes here only say who is who.
// role: "you" or "assistant". gender: "woman" or "man" (a bow and lashes, or an antenna and brows).

const EYES = '<circle class="r-eye" cx="46" cy="62" r="6"/><circle class="r-eye" cx="74" cy="62" r="6"/>';

const WOMAN = `
  <g class="r-line"><path d="M38 55l-3-5M46 54v-6M54 55l3-5M66 55l3-5M74 54v-6M82 55l3-5"/></g>
  <circle class="r-cheek" cx="36" cy="74" r="4"/><circle class="r-cheek" cx="84" cy="74" r="4"/>
  <path class="r-accent" d="M60 27L38 14q-5 14 0 26zM60 27l22-13q5 14 0 26z"/>
  <circle class="r-accent" cx="60" cy="27" r="6"/>`;

const MAN = `
  <g class="r-line thick"><path d="M38 52l16-3M82 52l-16-3"/></g>
  <path class="r-stem" d="M60 28V14"/><circle class="r-accent" cx="60" cy="11" r="5"/>
  <circle class="r-accent" cx="14" cy="64" r="2.5"/><circle class="r-accent" cx="106" cy="64" r="2.5"/>`;

export function robot(role, gender) {
  const wrap = document.createElement("div");
  wrap.className = `robot ${role}`;
  wrap.dataset.gender = gender;
  wrap.innerHTML = `
    <svg viewBox="0 0 120 124" role="img" aria-hidden="true" focusable="false">
      <rect class="r-body" x="32" y="98" width="56" height="22" rx="9"/>
      <circle class="r-accent r-chest" cx="60" cy="109" r="4"/>
      <rect class="r-ear" x="8" y="52" width="10" height="26" rx="5"/>
      <rect class="r-ear" x="102" y="52" width="10" height="26" rx="5"/>
      <rect class="r-head" x="16" y="28" width="88" height="68" rx="22"/>
      <rect class="r-screen" x="26" y="42" width="68" height="44" rx="15"/>
      ${EYES}
      <rect class="r-mouth" x="50" y="73" width="20" height="5" rx="2.5"/>
      ${gender === "woman" ? WOMAN : MAN}
    </svg>`;
  return wrap;
}

// Swap the gender look of a robot that is already on the page.
export function restyle(el, gender) {
  const fresh = robot(el.classList.contains("you") ? "you" : "assistant", gender);
  el.dataset.gender = gender;
  el.replaceChildren(...fresh.childNodes);
}
