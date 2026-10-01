/** From the markdown tree to a lit template — without `unsafeHTML`. */

import { html, TemplateResult, nothing } from "lit";

import { formatValue } from "./format";
import { fieldSpans } from "./grid";
import { Block, Inline, parseInline, parseMarkdown } from "./markdown";
import type { MessageBlock, MessageField, TableColumn } from "./types";

/** The only values that reach a cell's `text-align` — never foreign CSS. */
const ALIGNS = new Set(["left", "center", "right"]);

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
 * (sent by a newer integration) is skipped. `locale` is the viewer's language,
 * for values with a format.
 */
export function renderBlocks(
  blocks: MessageBlock[],
  plain: boolean,
  locale: string,
): TemplateResult {
  return html`${blocks.map((block) => {
    switch (block.type) {
      case "text":
        return plain ? renderPlain(block.text) : renderMarkdown(block.text);
      case "fields":
        return renderFields(block.rows, plain, locale);
      case "table":
        return renderTable(block.columns, block.rows, plain, locale);
      default:
        return nothing;
    }
  })}`;
}

/**
 * The label/value grid: one block, every row spanning its full width, the
 * columns of a row sharing it evenly. A row has as many columns as the spans
 * of its fields add up to, so rows with the same sum line up. Values follow
 * the message's format, labels are always plain text; a value with a format of
 * its own is plain text too, once it could be formatted.
 */
function renderFields(
  rows: MessageField[][],
  plain: boolean,
  locale: string,
): TemplateResult {
  return html`<div class="fields">
    ${rows.map((row) => {
      const spans = fieldSpans(row);
      const columns = spans.reduce((sum, span) => sum + span, 0);
      return html`<div class="field-row" style=${`--ln-columns:${columns}`}>
        ${row.map((field, index) => {
          const formatted = field.value
            ? formatValue(field.value, field.format, locale)
            : null;
          return html`<div
            class="field"
            style=${spans[index] > 1 ? `grid-column:span ${spans[index]}` : nothing}
          >
            ${field.label
              ? html`<div class="field-label">${field.label}</div>`
              : nothing}
            ${formatted !== null
              ? html`<div class="field-value formatted">${formatted}</div>`
              : field.value
                ? html`<div class="field-value">
                    ${plain
                      ? html`<span class="plain">${field.value}</span>`
                      : renderMarkdown(field.value)}
                  </div>`
                : nothing}
          </div>`;
        })}
      </div>`;
    })}
  </div>`;
}

/**
 * A table with a shared head. Cells follow the message's format, but only as
 * inline markdown — a list or code block has no place in a cell; a column's
 * own format turns a fitting cell into plain text. The head is
 * always plain text and left out when no column has a label. The table spans
 * the full width; the wrapper scrolls sideways so a wide one does not stretch
 * the card.
 */
function renderTable(
  columns: TableColumn[],
  rows: string[][],
  plain: boolean,
  locale: string,
): TemplateResult {
  const align = (index: number): string | typeof nothing => {
    const value = columns[index]?.align;
    return value && ALIGNS.has(value) ? `text-align:${value}` : nothing;
  };
  return html`<div class="table-wrap">
    <table>
      ${columns.some((column) => column.label)
        ? html`<thead>
            <tr>
              ${columns.map(
                (column, index) => html`<th style=${align(index)}>${column.label}</th>`,
              )}
            </tr>
          </thead>`
        : nothing}
      <tbody>
        ${rows.map(
          (row) =>
            html`<tr>
              ${row.map((cell, index) => {
                const formatted = cell
                  ? formatValue(cell, columns[index]?.format, locale)
                  : null;
                // No whitespace around the cell: plain cells keep theirs.
                return formatted !== null
                  ? html`<td class="formatted" style=${align(index)}>${formatted}</td>`
                  : html`<td class=${plain ? "plain" : nothing} style=${align(index)}
                      >${plain ? cell : parseInline(cell).map(renderInline)}</td
                    >`;
              })}
            </tr>`,
        )}
      </tbody>
    </table>
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
