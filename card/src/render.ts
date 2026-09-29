/** From the markdown tree to a lit template — without `unsafeHTML`. */

import { html, TemplateResult, nothing } from "lit";

import { Block, Inline, parseMarkdown } from "./markdown";
import type { MessageBlock, MessageField } from "./types";

export function renderMarkdown(text: string): TemplateResult {
  return html`${parseMarkdown(text).map(renderBlock)}`;
}

/** Plain messages: keep line breaks, interpret nothing else. */
export function renderPlain(text: string): TemplateResult {
  return html`<pre class="plain">${text}</pre>`;
}

/**
 * The blocks below the content, in the sender's order. Text follows the
 * message's format like the content does; a block type this card does not know
 * (sent by a newer integration) is skipped.
 */
export function renderBlocks(blocks: MessageBlock[], plain: boolean): TemplateResult {
  return html`${blocks.map((block) => {
    switch (block.type) {
      case "text":
        return plain ? renderPlain(block.text) : renderMarkdown(block.text);
      case "fields":
        return renderFields(block.rows, plain);
      default:
        return nothing;
    }
  })}`;
}

/**
 * The label/value grid: one block, every row spanning its full width, the
 * columns of a row sharing it evenly. Values follow the message's format,
 * labels are always plain text.
 */
function renderFields(rows: MessageField[][], plain: boolean): TemplateResult {
  return html`<div class="fields">
    ${rows.map(
      (row) =>
        html`<div class="field-row" style=${`--ln-columns:${row.length}`}>
          ${row.map(
            (field) =>
              html`<div class="field">
                ${field.label
                  ? html`<div class="field-label">${field.label}</div>`
                  : nothing}
                ${field.value
                  ? html`<div class="field-value">
                      ${plain
                        ? html`<span class="plain">${field.value}</span>`
                        : renderMarkdown(field.value)}
                    </div>`
                  : nothing}
              </div>`,
          )}
        </div>`,
    )}
  </div>`;
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
