import DOMPurify, { type Config } from "dompurify";

const noteHtmlConfig: Config = {
  ALLOWED_TAGS: [
    "a",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "input",
    "label",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
  ],
  ALLOWED_ATTR: [
    "checked",
    "colspan",
    "data-checked",
    "data-type",
    "disabled",
    "href",
    "rel",
    "rowspan",
    "target",
    "title",
    "type",
  ],
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|\/|#|\.{1,2}\/)/i,
  FORBID_ATTR: ["style"],
  FORBID_TAGS: ["style", "svg", "math", "script", "iframe", "object"],
};

export function sanitizeNoteHtml(value: string) {
  if (typeof window === "undefined") {
    return value.trim();
  }

  return String(DOMPurify.sanitize(value, noteHtmlConfig)).trim();
}

export function htmlToText(value: string) {
  if (typeof document === "undefined") {
    return value
      .replace(/<\/?[^>]+>/g, " ")
      .replace(/&nbsp;/gi, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  const container = document.createElement("div");
  container.innerHTML = sanitizeNoteHtml(value);
  return (container.textContent ?? "").replace(/\s+/g, " ").trim();
}
