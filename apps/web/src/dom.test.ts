import { describe, expect, it } from "vitest";

import { appendTranscriptLine, clearChildren, setText } from "./dom";

describe("transcript XSS safety", () => {
  it("renders hostile strings via textContent only", () => {
    const el = document.createElement("div");
    const hostile = `<img src=x onerror="window.__xss=1">`;
    appendTranscriptLine(el, "caller", hostile, { partial: false });
    expect(el.querySelector("img")).toBeNull();
    expect(el.textContent).toContain(hostile);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((window as any).__xss).toBeUndefined();
  });

  it("setText never interprets HTML", () => {
    const el = document.createElement("div");
    setText(el, "<b>bold</b>");
    expect(el.querySelector("b")).toBeNull();
    expect(el.textContent).toBe("<b>bold</b>");
    clearChildren(el);
    expect(el.childNodes.length).toBe(0);
  });
});
