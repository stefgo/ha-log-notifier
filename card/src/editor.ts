/** Visual editor of the card (ha-form). */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { fetchChannels } from "./api";
import { TextKey, localize } from "./i18n";
import { LEVELS } from "./levels";
import type { ChannelSummary, HomeAssistant, LogNotifierCardConfig } from "./types";

/** Text of each form field's label, by the field's name. */
const LABELS: Readonly<Record<string, TextKey | undefined>> = {
  title: "editor_title",
  channels: "editor_channels",
  sort: "editor_sort",
  levels: "editor_levels",
  layout: "editor_layout",
  height: "editor_height",
  page_size: "editor_page_size",
  mark_read: "editor_mark_read",
};

@customElement("log-notifier-card-editor")
export class LogNotifierCardEditor extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;

  @state() private _config: LogNotifierCardConfig = { type: "" };
  @state() private _channels: ChannelSummary[] = [];

  public setConfig(config: LogNotifierCardConfig): void {
    this._config = config;
  }

  protected firstUpdated(): void {
    if (this.hass) {
      void fetchChannels(this.hass).then((channels) => {
        this._channels = channels;
      });
    }
  }

  private _t(key: TextKey): string {
    return localize(this.hass?.locale?.language ?? this.hass?.language, key);
  }

  private get _schema() {
    return [
      { name: "title", selector: { text: {} } },
      {
        name: "channels",
        selector: {
          select: {
            // Chips rather than checkboxes: only they can be dragged, and
            // the order of the selection is the order on the card.
            multiple: true,
            reorder: true,
            mode: "dropdown",
            options: this._channels.map((channel) => ({
              value: channel.id,
              label: channel.name,
            })),
          },
        },
      },
      {
        name: "sort",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "config", label: this._t("sort_config") },
              { value: "name", label: this._t("sort_name") },
              { value: "unread", label: this._t("sort_unread") },
              { value: "latest", label: this._t("sort_latest") },
            ],
          },
        },
      },
      {
        name: "levels",
        selector: {
          select: { multiple: true, mode: "list", options: [...LEVELS] },
        },
      },
      {
        name: "layout",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "auto", label: this._t("layout_auto") },
              { value: "split", label: this._t("layout_split") },
              { value: "stacked", label: this._t("layout_stacked") },
            ],
          },
        },
      },
      { name: "height", selector: { text: {} } },
      {
        name: "page_size",
        selector: { number: { min: 10, max: 200, mode: "box" } },
      },
      {
        name: "mark_read",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "manual", label: this._t("mark_read_manual") },
              { value: "visible", label: this._t("mark_read_visible") },
              { value: "open", label: this._t("mark_read_open") },
            ],
          },
        },
      },
    ];
  }

  private _label = (schema: { name: string }): string => {
    const key = LABELS[schema.name];
    return key ? this._t(key) : schema.name;
  };

  private _valueChanged(event: CustomEvent): void {
    const value = { ...event.detail.value };
    // "all channels" is the absence of a selection — an empty list would
    // otherwise be stored as "no channels".
    if (Array.isArray(value.channels) && value.channels.length === 0) {
      delete value.channels;
    }
    // Same for the levels: no selection in the editor means "show all".
    if (Array.isArray(value.levels) && value.levels.length === 0) {
      delete value.levels;
    }
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: value } }),
    );
  }

  protected render() {
    if (!this.hass) return nothing;
    const data = {
      ...this._config,
      channels: this._config.channels === "all" ? [] : (this._config.channels ?? []),
    };
    return html`
      <ha-form
        .hass=${this.hass}
        .data=${data}
        .schema=${this._schema}
        .computeLabel=${this._label}
        @value-changed=${this._valueChanged}
      ></ha-form>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "log-notifier-card-editor": LogNotifierCardEditor;
  }
}
