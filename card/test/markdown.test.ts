import { describe, expect, it } from "vitest";

import { Inline, parseInline, parseMarkdown, toPlainText } from "../src/markdown";

/** Turn the tree back into text — shorter than any structural assertion. */
const flatten = (nodes: Inline[]): string =>
  nodes
    .map((node) => {
      switch (node.type) {
        case "text":
          return node.value;
        case "code":
          return `<code>${node.value}</code>`;
        case "link":
          return `<a:${node.href}>${flatten(node.children)}</a>`;
        default:
          return `<${node.type}>${flatten(node.children)}</${node.type}>`;
      }
    })
    .join("");

describe("inline formatting", () => {
  it("recognizes bold, italic, underline, strikethrough, spoiler", () => {
    expect(flatten(parseInline("**a**"))).toBe("<bold>a</bold>");
    expect(flatten(parseInline("*a*"))).toBe("<italic>a</italic>");
    expect(flatten(parseInline("_a_"))).toBe("<italic>a</italic>");
    expect(flatten(parseInline("__a__"))).toBe("<underline>a</underline>");
    expect(flatten(parseInline("~~a~~"))).toBe("<strike>a</strike>");
    expect(flatten(parseInline("||a||"))).toBe("<spoiler>a</spoiler>");
  });

  it("nests correctly", () => {
    expect(flatten(parseInline("**bold and *italic***"))).toBe(
      "<bold>bold and <italic>italic</italic></bold>",
    );
  });

  it("does not let * take apart a **", () => {
    expect(flatten(parseInline("**a** and *b*"))).toBe(
      "<bold>a</bold> and <italic>b</italic>",
    );
  });

  it("treats unfinished formatting as text", () => {
    expect(flatten(parseInline("**open"))).toBe("**open");
    expect(flatten(parseInline("2 * 3 * 4 is not italic"))).toBe(
      "2 <italic> 3 </italic> 4 is not italic",
    );
    expect(flatten(parseInline("exit_code_2"))).toBe("exit<italic>code</italic>2");
  });

  it("respects escapes", () => {
    expect(flatten(parseInline("\\*not italic\\*"))).toBe("*not italic*");
  });

  it("keeps inline code raw", () => {
    expect(flatten(parseInline("`**raw**`"))).toBe("<code>**raw**</code>");
  });

  it("recognizes links and bare URLs", () => {
    expect(flatten(parseInline("[HA](https://ha.io)"))).toBe(
      "<a:https://ha.io>HA</a>",
    );
    expect(flatten(parseInline("See https://ha.io/docs."))).toBe(
      "See <a:https://ha.io/docs>https://ha.io/docs</a>.",
    );
  });

  it("does not link dangerous schemes", () => {
    // javascript: links must never become an <a>.
    expect(flatten(parseInline("[click](javascript:alert(1))"))).toContain("[click]");
  });
});

describe("blocks", () => {
  it("recognizes code blocks with a language", () => {
    const blocks = parseMarkdown("```bash\nexit 2\n```");
    expect(blocks).toEqual([{ type: "code", lang: "bash", value: "exit 2" }]);
  });

  it("copes with an unclosed code block", () => {
    const blocks = parseMarkdown("```\ntruncated");
    expect(blocks[0]).toMatchObject({ type: "code", value: "truncated" });
  });

  it("recognizes headings, quotes and lists", () => {
    const blocks = parseMarkdown("# Title\n> quoted\n- one\n- two");
    expect(blocks[0]).toMatchObject({ type: "heading", level: 1 });
    expect(blocks[1]).toMatchObject({ type: "quote" });
    expect(blocks[2]).toMatchObject({ type: "list", ordered: false });
    expect((blocks[2] as { items: Inline[][] }).items).toHaveLength(2);
  });

  it("recognizes numbered lists", () => {
    const blocks = parseMarkdown("1. one\n2. two");
    expect(blocks[0]).toMatchObject({ type: "list", ordered: true });
  });

  it("splits paragraphs at blank lines", () => {
    const blocks = parseMarkdown("first line\nstill here\n\nsecond paragraph");
    expect(blocks).toHaveLength(2);
  });

  it("interprets nothing inside a code block", () => {
    const blocks = parseMarkdown("```\n# not a title\n- not a list\n```");
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ type: "code" });
  });
});

describe("preview text", () => {
  it("strips formatting for the channel list", () => {
    expect(toPlainText("**Backup**\n```\nexit 2\n```\nfailed")).toBe(
      "Backup failed",
    );
    expect(toPlainText("[HA](https://ha.io) is online")).toBe("HA is online");
  });
});
