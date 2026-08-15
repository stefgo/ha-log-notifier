/**
 * Parser for the Discord subset of Markdown.
 *
 * The result is a tree, not an HTML string: `render.ts` turns it into a lit
 * template. Foreign text therefore cannot inject markup structurally — there is
 * no place where raw text would be interpreted as HTML.
 *
 * Supported: **bold**, *italic* / _italic_, __underline__, ~~strikethrough~~,
 * `code`, ```code block```, > quote, ||spoiler||, lists, # headings,
 * [text](url) and bare URLs.
 */

export type Inline =
  | { type: "text"; value: string }
  | { type: "code"; value: string }
  | { type: "link"; href: string; children: Inline[] }
  | {
      type: "bold" | "italic" | "underline" | "strike" | "spoiler";
      children: Inline[];
    };

export type Block =
  | { type: "paragraph"; children: Inline[] }
  | { type: "heading"; level: 1 | 2 | 3; children: Inline[] }
  | { type: "quote"; children: Block[] }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "code"; lang: string | null; value: string };

const HEADING = /^(#{1,3})\s+(.*)$/;
const QUOTE = /^>\s?(.*)$/;
const BULLET = /^[-*]\s+(.*)$/;
const ORDERED = /^\d+[.)]\s+(.*)$/;
const FENCE = /^```(\w*)\s*$/;
const LINK = /^\[([^\]]*)\]\(([^\s)]+)\)/;

/** Only these schemes get linked — no javascript:, no data:. */
const SAFE_LINK = /^(https?:\/\/|mailto:)/i;

export function parseMarkdown(text: string): Block[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  return parseBlocks(lines);
}

function parseBlocks(lines: string[]): Block[] {
  const blocks: Block[] = [];
  let index = 0;

  const flushParagraph = (buffer: string[]) => {
    if (buffer.length) {
      blocks.push({ type: "paragraph", children: parseInline(buffer.join("\n")) });
      buffer.length = 0;
    }
  };

  const paragraph: string[] = [];

  while (index < lines.length) {
    const line = lines[index];
    const fence = FENCE.exec(line.trim());

    if (fence) {
      flushParagraph(paragraph);
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1; // skip the closing line (if absent, the block ends here)
      blocks.push({
        type: "code",
        lang: fence[1] || null,
        value: body.join("\n"),
      });
      continue;
    }

    if (!line.trim()) {
      flushParagraph(paragraph);
      index += 1;
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      flushParagraph(paragraph);
      blocks.push({
        type: "heading",
        level: heading[1].length as 1 | 2 | 3,
        children: parseInline(heading[2]),
      });
      index += 1;
      continue;
    }

    if (QUOTE.test(line)) {
      flushParagraph(paragraph);
      const quoted: string[] = [];
      while (index < lines.length) {
        const match = QUOTE.exec(lines[index]);
        if (!match) break;
        quoted.push(match[1]);
        index += 1;
      }
      blocks.push({ type: "quote", children: parseBlocks(quoted) });
      continue;
    }

    if (BULLET.test(line) || ORDERED.test(line)) {
      flushParagraph(paragraph);
      const ordered = ORDERED.test(line);
      const items: Inline[][] = [];
      while (index < lines.length) {
        const match = ordered
          ? ORDERED.exec(lines[index])
          : BULLET.exec(lines[index]);
        if (!match) break;
        items.push(parseInline(match[1]));
        index += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    paragraph.push(line);
    index += 1;
  }

  flushParagraph(paragraph);
  return blocks;
}

interface Delimiter {
  marker: string;
  type: "bold" | "italic" | "underline" | "strike" | "spoiler";
}

// The order is binding: the longer marker first, otherwise `*` eats half of a
// `**`.
const DELIMITERS: Delimiter[] = [
  { marker: "**", type: "bold" },
  { marker: "__", type: "underline" },
  { marker: "~~", type: "strike" },
  { marker: "||", type: "spoiler" },
  { marker: "*", type: "italic" },
  { marker: "_", type: "italic" },
];

export function parseInline(text: string): Inline[] {
  const nodes: Inline[] = [];
  let buffer = "";
  let index = 0;

  const flush = () => {
    if (buffer) {
      nodes.push({ type: "text", value: buffer });
      buffer = "";
    }
  };

  while (index < text.length) {
    const char = text[index];

    // Escape: \* stays an asterisk.
    if (char === "\\" && index + 1 < text.length) {
      buffer += text[index + 1];
      index += 2;
      continue;
    }

    if (char === "`") {
      const end = text.indexOf("`", index + 1);
      if (end > index + 1) {
        flush();
        nodes.push({ type: "code", value: text.slice(index + 1, end) });
        index = end + 1;
        continue;
      }
    }

    if (char === "[") {
      const match = LINK.exec(text.slice(index));
      if (match && SAFE_LINK.test(match[2])) {
        flush();
        nodes.push({
          type: "link",
          href: match[2],
          children: parseInline(match[1]),
        });
        index += match[0].length;
        continue;
      }
    }

    if (char === "h" || char === "m") {
      const url = matchAutolink(text, index);
      if (url) {
        flush();
        nodes.push({ type: "link", href: url, children: [{ type: "text", value: url }] });
        index += url.length;
        continue;
      }
    }

    const delimiter = DELIMITERS.find((candidate) =>
      text.startsWith(candidate.marker, index),
    );
    if (delimiter) {
      const start = index + delimiter.marker.length;
      const end = findClosing(text, delimiter.marker, start);
      // Without a counterpart it is not markup but simply a character —
      // unfinished formatting must not swallow the rest of the message.
      if (end > start) {
        flush();
        nodes.push({
          type: delimiter.type,
          children: parseInline(text.slice(start, end)),
        });
        index = end + delimiter.marker.length;
        continue;
      }
    }

    buffer += char;
    index += 1;
  }

  flush();
  return nodes;
}

function findClosing(text: string, marker: string, from: number): number {
  let index = from;
  while (index < text.length) {
    if (text[index] === "\\") {
      index += 2;
      continue;
    }
    if (text.startsWith(marker, index)) {
      // For a longer run (`***italic bold***`) the end of the run belongs to
      // the outer marker — otherwise an asterisk would be left in the text and
      // the inner formatting would fall away.
      let end = index;
      while (end < text.length && text[end] === marker[0]) end += 1;
      const runLength = end - index;
      return runLength > marker.length ? end - marker.length : index;
    }
    index += 1;
  }
  return -1;
}

function matchAutolink(text: string, index: number): string | null {
  const rest = text.slice(index);
  const match = /^(https?:\/\/|mailto:)[^\s<>()]+/i.exec(rest);
  if (!match) return null;
  // Trailing punctuation belongs to the sentence, not to the URL.
  return match[0].replace(/[.,;:!?]+$/, "");
}

/** Boil a message down to one line — for previews and the badge tooltip. */
export function toPlainText(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_~|>#]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
