/** Visual editor of the card (ha-form). */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { fetchChannels } from "./api";
import { LEVELS } from "./levels";
import type { ChannelSummary, HomeAssistant, LogNotifierCardConfig } from "./types";

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

  private get _schema() {
    return [
      { name: "title", selector: { text: {} } },
      {
        name: "channels",
        selector: {
          select: {
            multiple: true,
            mode: "list",
            options: this._channels.map((channel) => ({
              value: channel.id,
              label: channel.name,
            })),
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
              { value: "auto", label: "Automatic" },
              { value: "split", label: "Always two columns" },
              { value: "stacked", label: "Always stacked" },
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
              { value: "manual", label: "Button only" },
              { value: "visible", label: "When everything was seen" },
              { value: "open", label: "When the channel is opened" },
            ],
          },
        },
      },
    ];
  }

  private _label = (schema: { name: string }): string =>
    ({
      title: "Title",
      channels: "Channels (empty = all)",
      levels: "Displayed levels (empty = all)",
      layout: "Layout",
      height: "Height (e.g. 70vh or 500px)",
      page_size: "Messages per load step",
      mark_read: "Mark as read",
    })[schema.name] ?? schema.name;

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
