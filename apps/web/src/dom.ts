/**
 * Safe transcript rendering — always textContent, never innerHTML.
 */

export function appendTranscriptLine(
  el: HTMLElement,
  role: string,
  text: string,
  opts: { partial?: boolean } = {},
): void {
  const partial = opts.partial ?? false;
  const lineId = partial ? `partial-${role}` : "";
  let line = lineId ? (el.querySelector(`#${CSS.escape(lineId)}`) as HTMLElement | null) : null;
  if (!line) {
    line = document.createElement("div");
    if (lineId) line.id = lineId;
    el.appendChild(line);
  }
  // textContent only — XSS-hostile strings must not execute.
  line.textContent = `${role}: ${text}`;
  if (!partial && lineId) {
    line.removeAttribute("id");
  }
  el.scrollTop = el.scrollHeight;
}

export function setText(el: HTMLElement, text: string): void {
  el.textContent = text;
}

export function clearChildren(el: HTMLElement): void {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}
