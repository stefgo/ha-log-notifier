/** From the markdown tree to a lit template — without `unsafeHTML`. */

import { html, TemplateResult, nothing } from "lit";

import { Block, Inline, parseMarkdown } from "./markdown";

export function renderMarkdown(text: string): TemplateResult {
  return html`${parseMarkdown(text).map(renderBlock)}`;
}

/** Plain messages: keep line breaks, interpret nothing else. */
export function renderPlain(text: string): TemplateResult {
  return html`<pre class="plain">${text}</pre>`;
}

function renderBlock(block: Block): TemplateResult {
  switch (block.type) {
    case "heading":
      return block.level === 1
        ? html`<h1>${block.children.map(renderInline)}</h1>`
        : block.level === 2
          ? html`<h2>${block.children.map(renderInline)}</h2>`
          : html`<h3>${block.children.map(renderInline)}</h3>`;
    case "quote":
      return html`<blockquote>${block.children.map(renderBlock)}</blockquote>`;
    case "code":
      return html`<pre class="code"><code data-lang=${block.lang ?? nothing}
>${block.value}</code></pre>`;
    case "list":
      return block.ordered
        ? html`<ol>
            ${block.items.map((item) => html`<li>${item.map(renderInline)}</li>`)}
          </ol>`
        : html`<ul>
            ${block.items.map((item) => html`<li>${item.map(renderInline)}</li>`)}
          </ul>`;
    default:
      return html`<p>${block.children.map(renderInline)}</p>`;
  }
}

function renderInline(node: Inline): TemplateResult | string {
  switch (node.type) {
    case "text":
      return node.value;
    case "code":
      return html`<code>${node.value}</code>`;
    case "bold":
      return html`<strong>${node.children.map(renderInline)}</strong>`;
    case "italic":
      return html`<em>${node.children.map(renderInline)}</em>`;
    case "underline":
      return html`<span class="underline">${node.children.map(renderInline)}</span>`;
    case "strike":
      return html`<s>${node.children.map(renderInline)}</s>`;
    case "spoiler":
      // Only visible on click — just like in Discord.
      return html`<span
        class="spoiler"
        @click=${(event: Event) =>
          (event.currentTarget as HTMLElement).classList.add("revealed")}
        >${node.children.map(renderInline)}</span
      >`;
    case "link":
      return html`<a href=${node.href} target="_blank" rel="noopener noreferrer"
        >${node.children.map(renderInline)}</a
      >`;
  }
}
