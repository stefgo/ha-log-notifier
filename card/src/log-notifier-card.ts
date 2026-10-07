/**
 * Log Notifier Card
 *
 * Channel list with unread badges and a message view per channel.
 * The data comes through the integration's WebSocket commands rather than
 * entity states: only that way can message bodies and paging be represented.
 */

import { LitElement, PropertyValues, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import "./editor";
import {
  StreamEvent,
  clearChannel,
  fetchChannels,
  fetchMessages,
  markRead,
  subscribe,
} from "./api";
import { TextKey, localize } from "./i18n";
import { LEVELS, levelColor, levelIcon } from "./levels";
import { toPlainText } from "./markdown";
import { renderBlocks, renderMarkdown, renderPlain } from "./render";
import type {
  ChannelSummary,
  HomeAssistant,
  Level,
  LogMessage,
  LogNotifierCardConfig,
} from "./types";
import {
  ViewMode,
  ViewState,
  isCompact,
  isUnread,
  previewText,
  summaryLine,
} from "./view";

/** Default height of the message area. */
const DEFAULT_HEIGHT = "70vh";

const LENGTH = /^\d+(\.\d+)?(px|vh|svh|dvh|lvh|vmin|vmax|%|rem|em)$/;

/**
 * `calc(…)` with a `var(…)` inside — there is no other way to express "window
 * height minus header". The character set is kept tight: without `:`, `;` and
 * quotes the value cannot turn into a second CSS declaration.
 */
const CALC = /^calc\([-+*/\s0-9a-z().%]+\)$/i;

/**
 * Validate the height value and turn it into a CSS length.
 *
 * The value ends up in a CSS variable; an unchecked string there would be an
 * open flank — hence the allow-list. A bare number reads as pixels, just like
 * everywhere else in Lovelace.
 */
function parseHeight(value: string | number | undefined): string {
  if (value === undefined) return DEFAULT_HEIGHT;
  if (typeof value === "number") {
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error(`Invalid height: ${value}`);
    }
    return `${value}px`;
  }
  const text = String(value).trim();
  if (!LENGTH.test(text) && !CALC.test(text)) {
    throw new Error(
      `Invalid height: ${value} — allowed are numbers, values such as 70vh ` +
        `or 500px, and calc(…)`,
    );
  }
  return text;
}

console.info(
  "%c LOG-NOTIFIER-CARD %c " + CARD_VERSION + " ",
  "background-color: #000000; color: #4CAF50; font-weight: bold;",
  "background-color: #666666; color: #FFFFFF; font-weight: bold;",
);

@customElement("log-notifier-card")
export class LogNotifierCard extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;

  @state() private _config: LogNotifierCardConfig = { type: "" };
  @state() private _channels: ChannelSummary[] = [];
  @state() private _selected: string | null = null;
  @state() private _messages: LogMessage[] = [];
  @state() private _levels: Level[] = [...LEVELS];
  @state() private _loading = false;
  @state() private _hasMore = false;
  /**
   * Read position at the moment the channel was opened; the "New" divider is
   * drawn there. A snapshot, so the divider stays put while the channel is
   * open even after its messages were marked read.
   */
  @state() private _dividerReadId: number | null = null;
  /** Form of all messages; "auto" until the header switch is used. */
  @state() private _viewMode: ViewMode = "auto";
  /** Messages switched individually — each the opposite of the view mode. */
  @state() private _toggled: ReadonlySet<number> = new Set();
  @state() private _error: string | null = null;
  @state() private _wide = false;

  private _unsubscribe?: () => Promise<void>;
  private _started = false;
  private _resizeObserver?: ResizeObserver;
  private _visibilityObserver?: IntersectionObserver;
  /** IDs that stayed on screen long enough to count as seen. */
  private _height = DEFAULT_HEIGHT;
  private _seen = new Set<number>();
  private _dwellTimers = new Map<number, ReturnType<typeof setTimeout>>();
  /** IDs of messages that arrived live and still have to slide in. */
  private _arrived: number[] = [];

  /**
   * This is how long a message has to stay visible before it counts as seen —
   * scrolling past quickly should not acknowledge anything.
   */
  private static readonly DWELL_MS = 400;

  /** Duration of the slide-in of a message that arrives live. */
  private static readonly SLIDE_MS = 250;

  /**
   * From this width on, channel list and messages fit side by side. What is
   * measured is the card itself, not the window: on a desktop it may sit in a
   * narrow dashboard column, where two columns would be unreadable.
   */
  private static readonly SPLIT_WIDTH = 700;

  public setConfig(config: LogNotifierCardConfig): void {
    const unknown = (config.levels ?? []).filter(
      (level) => !LEVELS.includes(level),
    );
    if (unknown.length) {
      throw new Error(`Unknown levels: ${unknown.join(", ")}`);
    }
    if (config.layout && !["auto", "split", "stacked"].includes(config.layout)) {
      throw new Error(`Unknown layout: ${config.layout}`);
    }
    if (
      config.mark_read &&
      !["manual", "visible", "open"].includes(config.mark_read)
    ) {
      throw new Error(`Unknown mark_read: ${config.mark_read}`);
    }
    this._height = parseHeight(config.height);
    this._config = { page_size: 50, layout: "auto", mark_read: "manual", ...config };
    // The order comes from LEVELS so the chips are always arranged the same way
    // regardless of the configuration.
    this._levels = config.levels?.length
      ? LEVELS.filter((level) => config.levels!.includes(level))
      : [...LEVELS];
  }

  /** Two columns or drill-down? */
  private get _split(): boolean {
    const layout = this._config.layout ?? "auto";
    if (layout === "split") return true;
    if (layout === "stacked") return false;
    return this._wide;
  }

  public getCardSize(): number {
    if (this._split) return 10;
    return this._selected ? 8 : Math.max(3, this._channels.length + 1);
  }

  public static getConfigElement(): HTMLElement {
    return document.createElement("log-notifier-card-editor");
  }

  public static getStubConfig(): LogNotifierCardConfig {
    return { type: "custom:log-notifier-card", channels: "all" };
  }

  protected updated(changed: PropertyValues): void {
    // hass only arrives after the first render; the startup depends on it.
    if (changed.has("hass") && this.hass && !this._started) {
      this._started = true;
      void this._start();
    }
    // Re-attach after every render: the message elements are different ones.
    this._observeMessages();
    this._slideInArrived();
  }

  /**
   * Lets the messages that just arrived live slide in from the top.
   *
   * The top margin runs from minus the element's height to its normal value,
   * so the message grows out of the upper edge and pushes the older ones down
   * instead of making them jump. Loaded pages are not animated — only what
   * arrives while the channel is open.
   */
  private _slideInArrived(): void {
    const arrived = this._arrived;
    if (arrived.length === 0) return;
    this._arrived = [];
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    for (const id of arrived) {
      const element = this.renderRoot.querySelector<HTMLElement>(
        `.message[data-id="${id}"]`,
      );
      if (!element || typeof element.animate !== "function") continue;
      element.animate(
        [
          { marginTop: `-${element.offsetHeight}px`, opacity: 0 },
          { marginTop: getComputedStyle(element).marginTop, opacity: 1 },
        ],
        { duration: LogNotifierCard.SLIDE_MS, easing: "ease-out" },
      );
    }
  }

  public connectedCallback(): void {
    super.connectedCallback();
    if (typeof ResizeObserver !== "undefined") {
      this._resizeObserver = new ResizeObserver((entries) =>
        this._applyWidth(entries[0]?.contentRect.width ?? 0),
      );
      this._resizeObserver.observe(this);
    }
  }

  /**
   * Observes the rendered messages.
   *
   * No custom `root`: the default (the viewport) takes the clipping rectangles
   * of all scrolling ancestors into account, and those differ per layout —
   * stacked it is `.messages` that scrolls, in two columns it is the column.
   */
  private _observeMessages(): void {
    if (this._config.mark_read !== "visible") {
      this._visibilityObserver?.disconnect();
      this._visibilityObserver = undefined;
      return;
    }
    if (typeof IntersectionObserver === "undefined") return;
    if (!this._visibilityObserver) {
      this._visibilityObserver = new IntersectionObserver(
        (entries) => this._onVisibility(entries),
        { threshold: 0.5 },
      );
    }
    this._visibilityObserver.disconnect();
    this.renderRoot
      .querySelectorAll<HTMLElement>(".message[data-id]")
      .forEach((element) => this._visibilityObserver!.observe(element));
  }

  private _onVisibility(entries: IntersectionObserverEntry[]): void {
    for (const entry of entries) {
      const id = Number((entry.target as HTMLElement).dataset.id);
      if (!id) continue;
      const running = this._dwellTimers.get(id);
      if (entry.isIntersecting) {
        if (running || this._seen.has(id)) continue;
        this._dwellTimers.set(
          id,
          setTimeout(() => {
            this._dwellTimers.delete(id);
            this._seen.add(id);
            void this._markReadIfAllSeen();
          }, LogNotifierCard.DWELL_MS),
        );
      } else if (running) {
        clearTimeout(running);
        this._dwellTimers.delete(id);
      }
    }
  }

  /**
   * Acknowledges only once every unread message really appeared on screen.
   *
   * The read position is a watermark: marking the newest seen message also
   * marks every older one as read. Partial progress cannot be represented that
   * way — hence the all-or-nothing rule.
   */
  private async _markReadIfAllSeen(): Promise<void> {
    if (this._config.mark_read !== "visible" || !this._selected) return;
    const channel = this._channelById(this._selected);
    if (!channel) return;

    // A level filter can hide unread messages; then "everything seen" cannot
    // be established.
    if (this._levels.length !== LEVELS.length) return;

    const unread = this._messages.filter(
      (message) => message.id > channel.last_read_id,
    );
    if (unread.length === 0) return;
    // If unread messages remain below the loaded page, the proof is missing —
    // let it load more first.
    const oldestLoaded = this._messages[this._messages.length - 1];
    if (this._hasMore && oldestLoaded && oldestLoaded.id > channel.last_read_id) {
      return;
    }
    if (!unread.every((message) => this._seen.has(message.id))) return;
    await this._markRead();
  }

  protected firstUpdated(): void {
    // The observer only reports on the next frame; without this measurement the
    // card would sit in the wrong layout until the first resize.
    this._applyWidth(this.getBoundingClientRect().width);
  }

  private _applyWidth(width: number): void {
    // A width of 0 means "not laid out yet" — that says nothing about the later
    // size and must not switch the layout.
    if (width <= 0) return;
    const wide = width >= LogNotifierCard.SPLIT_WIDTH;
    if (wide === this._wide) return;
    this._wide = wide;
    // When switching to two columns, the right-hand column must not stay
    // empty.
    if (this._split && !this._selected) void this._selectFirst();
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    void this._unsubscribe?.();
    this._unsubscribe = undefined;
    this._resizeObserver?.disconnect();
    this._resizeObserver = undefined;
    this._visibilityObserver?.disconnect();
    this._visibilityObserver = undefined;
    this._dwellTimers.forEach((timer) => clearTimeout(timer));
    this._dwellTimers.clear();
    this._started = false;
  }

  private async _selectFirst(): Promise<void> {
    const first = this._visibleChannels[0];
    if (first) await this._openChannel(first.id);
  }

  private async _start(): Promise<void> {
    await this._loadChannels();
    if (!this.hass) return;
    try {
      this._unsubscribe = await subscribe(this.hass, (event) =>
        this._onStreamEvent(event),
      );
    } catch (err) {
      this._error = String(err);
    }
  }

  private _onStreamEvent(event: StreamEvent): void {
    // Channels were reconfigured: new names, icons, possibly other channels.
    if (event.event === "channels") {
      this._channels = event.channels;
      if (this._selected && !this._channelById(this._selected)) {
        // The open channel is gone — back to the list, or in two columns to
        // the first remaining one.
        this._selected = null;
        this._messages = [];
        if (this._split) void this._selectFirst();
      }
      return;
    }
    if (event.event === "channel") {
      this._channels = this._channels.map((channel) =>
        channel.id === event.channel.id ? event.channel : channel,
      );
      return;
    }
    // New message: only insert it if the affected channel is open and the
    // filter lets it through.
    if (
      event.channel_id === this._selected &&
      this._levels.includes(event.message.level)
    ) {
      this._messages = [event.message, ...this._messages];
      this._arrived.push(event.message.id);
      // With "open" the opened channel counts as reviewed, including what
      // arrives afterwards; with "visible" the observer decides.
      if (this._config.mark_read === "open") {
        void this._markRead(event.message.id);
      }
    }
  }

  private get _visibleChannels(): ChannelSummary[] {
    const wanted = this._config.channels;
    if (!wanted || wanted === "all") return this._channels;
    return wanted
      .map((id) => this._channels.find((channel) => channel.id === id))
      .filter((channel): channel is ChannelSummary => Boolean(channel));
  }

  private async _loadChannels(): Promise<void> {
    if (!this.hass) return;
    try {
      this._channels = await fetchChannels(this.hass);
      this._error = null;
      if (this._split && !this._selected) await this._selectFirst();
    } catch (err) {
      this._error = this._t("error_channels", { error: String(err) });
    }
  }

  private async _openChannel(channelId: string): Promise<void> {
    this._selected = channelId;
    this._dividerReadId = this._channelById(channelId)?.last_read_id ?? null;
    this._viewMode = "auto";
    this._toggled = new Set();
    this._messages = [];
    // "Seen" is counted per channel — otherwise a switch would drag the state
    // of the previous one along.
    this._seen.clear();
    this._dwellTimers.forEach((timer) => clearTimeout(timer));
    this._dwellTimers.clear();
    await this._loadMessages();
    if (this._config.mark_read === "open") {
      await this._markRead();
    }
  }

  private async _loadMessages(before?: number): Promise<void> {
    if (!this.hass || !this._selected) return;
    // Without a selected level there is nothing to fetch — and the server would
    // first have to assemble an empty list.
    if (this._levels.length === 0) {
      this._messages = [];
      this._hasMore = false;
      return;
    }
    this._loading = true;
    try {
      const limit = this._config.page_size ?? 50;
      const page = await fetchMessages(this.hass, this._selected, {
        before,
        limit,
        levels: this._levels,
      });
      this._messages = before ? [...this._messages, ...page] : page;
      this._hasMore = page.length === limit;
      this._error = null;
    } catch (err) {
      this._error = this._t("error_messages", { error: String(err) });
    } finally {
      this._loading = false;
    }
  }

  private async _markRead(upToId?: number): Promise<void> {
    if (!this.hass || !this._selected) return;
    const summary = await markRead(this.hass, this._selected, upToId);
    this._channels = this._channels.map((channel) =>
      channel.id === summary.id ? summary : channel,
    );
  }

  /** Puts every message into one form, dropping the individual switches. */
  private _setViewMode(mode: ViewMode): void {
    this._viewMode = mode;
    this._toggled = new Set();
  }

  private _toggleMessage(id: number): void {
    const toggled = new Set(this._toggled);
    if (!toggled.delete(id)) toggled.add(id);
    this._toggled = toggled;
  }

  private _onHeadKeydown(event: KeyboardEvent, id: number): void {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    this._toggleMessage(id);
  }

  private async _clear(): Promise<void> {
    if (!this.hass || !this._selected) return;
    const channel = this._channelById(this._selected);
    const question = this._t("clear_confirm", { name: channel?.name ?? "" });
    if (!confirm(question)) return;
    await clearChannel(this.hass, this._selected);
    this._messages = [];
    await this._loadChannels();
  }

  /** Toggle a level on or off — each on its own, without any ranking. */
  private async _toggleLevel(level: Level): Promise<void> {
    this._levels = this._levels.includes(level)
      ? this._levels.filter((entry) => entry !== level)
      : LEVELS.filter((entry) => entry === level || this._levels.includes(entry));
    await this._loadMessages();
  }

  private _channelById(id: string): ChannelSummary | undefined {
    return this._channels.find((channel) => channel.id === id);
  }

  /** The viewer's language, for timestamps and formatted values. */
  private get _locale(): string {
    return this.hass?.locale?.language ?? this.hass?.language ?? "en";
  }

  /** A UI text in the viewer's language. */
  private _t(key: TextKey, values?: Record<string, string>): string {
    return localize(this._locale, key, values);
  }

  private _formatTime(ts: number): string {
    const date = new Date(ts * 1000);
    const locale = this._locale;
    const diff = (Date.now() - date.getTime()) / 1000;
    // Recent messages relative ("5 min ago"), older ones with a date.
    if (diff < 60) return this._t("just_now");
    const relative = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
    if (diff < 3600) return relative.format(-Math.round(diff / 60), "minute");
    if (diff < 86400) return relative.format(-Math.round(diff / 3600), "hour");
    if (diff < 7 * 86400) return relative.format(-Math.round(diff / 86400), "day");
    return date.toLocaleString(locale, {
      dateStyle: "short",
      timeStyle: "short",
    });
  }

  protected render() {
    if (!this.hass) return nothing;
    const error = this._error
      ? html`<div class="error">${this._error}</div>`
      : nothing;

    if (this._split) {
      // The title spans both columns rather than sitting in the channel list —
      // it names the card, not the left-hand column.
      return html`
        <ha-card class="split" style=${`--ln-height:${this._height}`}>
          ${this._renderHeader()}
          <div class="panes">
            <div class="pane pane-list">${this._renderChannelList(false)}</div>
            <div class="pane pane-detail">
              ${this._selected
                ? this._renderChannel(false)
                : html`<div class="empty">${this._t("select_channel")}</div>`}
              ${error}
            </div>
          </div>
        </ha-card>
      `;
    }

    return html`
      <ha-card style=${`--ln-height:${this._height}`}>
        ${this._selected ? this._renderChannel(true) : this._renderChannelList(true)}
        ${error}
      </ha-card>
    `;
  }

  /** Without a configured title the header is omitted entirely. */
  private _renderHeader() {
    const title = this._config.title?.trim();
    return title ? html`<h1 class="card-header">${title}</h1>` : nothing;
  }

  private _renderChannelList(withHeader: boolean) {
    const channels = this._visibleChannels;
    return html`
      ${withHeader ? this._renderHeader() : nothing}
      ${channels.length === 0
        ? html`<div class="empty">
            No channels configured — add them under Settings → Devices &
            services → Log Notifier → Configure.
          </div>`
        : html`<div class="channels">
            ${channels.map((channel) => this._renderChannelRow(channel))}
          </div>`}
    `;
  }

  /**
   * One row of the channel list.
   *
   * In the two-column layout the preview text and the time are left out: the
   * channel stream sits right next to it, showing the same message twice would
   * only be noise — and the narrow column would truncate the text anyway.
   */
  private _renderChannelRow(channel: ChannelSummary) {
    const active = this._split && channel.id === this._selected;
    const last = channel.last_message;
    const badgeColor = levelColor(channel.highest_unread_level);
    return html`
      <div
        class="channel ${channel.enabled ? "" : "disabled"} ${active ? "active" : ""}"
        role="button"
        tabindex="0"
        @click=${() => this._openChannel(channel.id)}
        @keydown=${(event: KeyboardEvent) => {
          if (event.key === "Enter" || event.key === " ") {
            void this._openChannel(channel.id);
          }
        }}
      >
        <ha-icon
          class="channel-icon"
          .icon=${channel.icon || "mdi:message-text-outline"}
        ></ha-icon>
        <div class="channel-text">
          <div class="channel-name">${channel.name}</div>
          ${this._split || !last
            ? nothing
            : html`<div class="channel-preview">
                <span class="dot" style=${`background:${levelColor(last.level)}`}></span>
                ${toPlainText(previewText(last)).slice(0, 90)}
              </div>`}
        </div>
        <div class="channel-meta">
          ${last && !this._split
            ? html`<div class="time">${this._formatTime(last.ts)}</div>`
            : nothing}
          ${channel.unread > 0
            ? html`<div class="badge" style=${`background:${badgeColor}`}>
                ${channel.unread > 99 ? "99+" : channel.unread}
              </div>`
            : nothing}
        </div>
      </div>
    `;
  }

  private _renderChannel(withBack: boolean) {
    const channel = this._selected ? this._channelById(this._selected) : undefined;
    if (!channel) return nothing;
    const isAdmin = this.hass?.user?.is_admin ?? false;
    const view: ViewState = {
      readId: channel.last_read_id,
      openedReadId: this._dividerReadId ?? channel.last_read_id,
      mode: this._viewMode,
      toggled: this._toggled,
    };
    // The switch offers "detail" as long as anything is still compact.
    const anyCompact = this._messages.some((message) => isCompact(message.id, view));
    return html`
      <div class="toolbar">
        ${withBack
          ? html`<ha-icon-button
              .path=${"M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z"}
              label=${this._t("back")}
              @click=${() => {
                this._selected = null;
                void this._loadChannels();
              }}
            ></ha-icon-button>`
          : nothing}
        <div class="toolbar-title">${channel.name}</div>
        ${this._messages.length > 0
          ? html`<button
              class="text-button"
              @click=${() => this._setViewMode(anyCompact ? "detail" : "compact")}
            >
              ${this._t(anyCompact ? "show_detail" : "show_compact")}
            </button>`
          : nothing}
        <button class="text-button" @click=${() => this._markRead()}>
          ${this._t("mark_all_read")}
        </button>
        ${isAdmin
          ? html`<button class="text-button danger" @click=${() => this._clear()}>
              ${this._t("clear")}
            </button>`
          : nothing}
      </div>
      <div class="filters">
        ${LEVELS.map((level) => {
          const on = this._levels.includes(level);
          return html`<button
            class="chip ${on ? "active" : ""}"
            style=${on
              ? `background:${levelColor(level)};border-color:${levelColor(level)}`
              : `color:${levelColor(level)}`}
            role="switch"
            aria-checked=${on ? "true" : "false"}
            @click=${() => this._toggleLevel(level)}
          >
            ${level}
          </button>`;
        })}
      </div>
      <div class="messages">
        ${this._levels.length === 0
          ? html`<div class="empty">${this._t("no_level")}</div>`
          : this._messages.length === 0 && !this._loading
          ? html`<div class="empty">${this._t("no_messages")}</div>`
          : this._renderMessages(view)}
        ${this._hasMore
          ? html`<button
              class="text-button more"
              ?disabled=${this._loading}
              @click=${() =>
                this._loadMessages(this._messages[this._messages.length - 1]?.id)}
            >
              ${this._t(this._loading ? "loading" : "load_older")}
            </button>`
          : nothing}
      </div>
    `;
  }

  /**
   * The message stream with the "New" divider at the read position.
   *
   * Messages are listed newest first, so everything above the divider is
   * unread. It sits in front of the first read message; if every message is
   * unread it closes the list — but only once nothing older is left to load,
   * because until then the read position may lie below the loaded page.
   *
   * The position is the one from opening the channel, not the live one:
   * marking read must not make the divider vanish under the reader's eyes. It
   * is gone the next time the channel is opened with nothing unread.
   */
  private _renderMessages(view: ViewState) {
    const firstRead = this._messages.findIndex(
      (message) => message.id <= view.openedReadId,
    );
    const allUnread =
      firstRead === -1 && this._messages.length > 0 && !this._hasMore;
    return html`
      ${this._messages.map(
        (message, index) => html`
          ${index === firstRead && index > 0 ? this._renderNewDivider() : nothing}
          ${this._renderMessage(
            message,
            isCompact(message.id, view),
            !isUnread(message.id, view),
          )}
        `,
      )}
      ${allUnread ? this._renderNewDivider() : nothing}
    `;
  }

  private _renderNewDivider() {
    return html`<div class="new-divider" role="separator">
      <span>↑ ${this._t("new_divider")}</span>
    </div>`;
  }

  /**
   * One message, compact (head line only) or in detail. The head line toggles
   * between the two — unless the message is unread, which keeps it in detail.
   * Compact, a message without a title shows the first line of its body in the
   * title's place.
   */
  private _renderMessage(message: LogMessage, compact: boolean, togglable: boolean) {
    const color = levelColor(message.level);
    const summary = compact && !message.title ? summaryLine(message) : "";
    return html`
      <div
        class="message ${compact ? "compact" : ""}"
        data-id=${message.id}
        style=${`border-left-color:${color}`}
      >
        <div
          class="message-head ${togglable ? "togglable" : ""}"
          role=${togglable ? "button" : nothing}
          tabindex=${togglable ? "0" : nothing}
          aria-expanded=${togglable ? String(!compact) : nothing}
          @click=${togglable ? () => this._toggleMessage(message.id) : nothing}
          @keydown=${togglable
            ? (event: KeyboardEvent) => this._onHeadKeydown(event, message.id)
            : nothing}
        >
          <ha-icon
            class="level-icon"
            style=${`color:${color}`}
            .icon=${levelIcon(message.level)}
          ></ha-icon>
          <span class="level" style=${`color:${color}`}>${message.level}</span>
          ${message.title ? html`<span class="title">${message.title}</span>` : nothing}
          ${summary ? html`<span class="summary">${summary}</span>` : nothing}
          <span class="spacer"></span>
          ${message.source ? html`<span class="source">${message.source}</span>` : nothing}
          <span class="time">${this._formatTime(message.ts)}</span>
        </div>
        ${compact
          ? nothing
          : html`<div class="body">
                ${!message.content
                  ? nothing
                  : message.format === "plain"
                    ? renderPlain(message.content)
                    : renderMarkdown(message.content)}
                ${message.blocks?.length
                  ? renderBlocks(
                      message.blocks,
                      message.format === "plain",
                      this._locale,
                    )
                  : nothing}
              </div>
              ${message.tags?.length
                ? html`<div class="tags">
                    ${message.tags.map((tag) => html`<span class="tag">${tag}</span>`)}
                  </div>`
                : nothing}`}
      </div>
    `;
  }

  static styles = css`
    /* Mandatory, not cosmetic: without this rule a custom element is inline,
       and per spec the ResizeObserver does not report inline elements at all —
       the width measurement for the layout would never happen. */
    :host {
      display: block;
    }
    ha-card {
      overflow: hidden;
    }

    /* Two columns: channels on the left, the message stream on the right. Both
       columns scroll on their own so the channel list stays put while paging. */
    ha-card.split {
      display: flex;
      flex-direction: column;
      height: var(--ln-height, 70vh);
    }
    ha-card.split .card-header {
      border-bottom: 1px solid var(--divider-color);
      padding-bottom: 12px;
    }
    .panes {
      display: grid;
      grid-template-columns: minmax(220px, 300px) 1fr;
      align-items: stretch;
      flex: 1;
      /* Without this line a grid cell grows with its content instead of
         scrolling — the card would run past its height. */
      min-height: 0;
    }
    .pane {
      min-width: 0;
      overflow-y: auto;
    }
    .pane-list {
      border-right: 1px solid var(--divider-color);
      background: var(--card-background-color);
    }
    .pane-detail {
      display: flex;
      flex-direction: column;
    }
    /* In two columns the height is already capped — the message list should
       fill the rest of the column instead of limiting a second time. */
    .pane-detail .messages {
      flex: 1;
      max-height: none;
    }
    .pane-detail .toolbar,
    .pane-detail .filters {
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--card-background-color);
    }
    .pane-detail .filters {
      top: 48px;
      border-bottom: 1px solid var(--divider-color);
    }
    .channel.active {
      background: var(--secondary-background-color);
      box-shadow: inset 3px 0 0 0 var(--primary-color);
    }

    .card-header {
      font-size: 24px;
      font-weight: 400;
      padding: 16px 16px 8px;
      margin: 0;
    }
    .empty {
      padding: 16px;
      color: var(--secondary-text-color);
    }
    .error {
      padding: 12px 16px;
      color: var(--error-color);
    }

    /* Channel list */
    .channel {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 16px;
      cursor: pointer;
      border-top: 1px solid var(--divider-color);
    }
    /* Without a title the first row's divider would sit right at the card edge. */
    .channels > .channel:first-child {
      border-top: none;
    }
    .channel:hover {
      background: var(--secondary-background-color);
    }
    .channel.disabled {
      opacity: 0.5;
    }
    .channel-icon {
      color: var(--state-icon-color);
    }
    .channel-text {
      flex: 1;
      min-width: 0;
    }
    .channel-name {
      font-size: 15px;
      font-weight: 500;
    }
    .channel-preview {
      font-size: 13px;
      color: var(--secondary-text-color);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      margin-right: 6px;
    }
    .channel-meta {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .badge {
      min-width: 20px;
      height: 20px;
      padding: 0 6px;
      border-radius: 10px;
      color: #fff;
      font-size: 12px;
      font-weight: 600;
      line-height: 20px;
      text-align: center;
    }
    .time {
      font-size: 12px;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }

    /* Channel view */
    /* Same left edge as the filter chips and the messages (12px) — otherwise
       the channel name would be out of alignment. */
    .toolbar {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 8px 12px;
      border-bottom: 1px solid var(--divider-color);
    }
    /* The back button brings its own padding; without compensation it would
       push the row out of alignment to the right. */
    .toolbar ha-icon-button {
      margin-left: -8px;
      margin-right: -4px;
    }
    .toolbar-title {
      flex: 1;
      font-size: 18px;
      font-weight: 500;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .text-button {
      background: none;
      border: none;
      color: var(--primary-color);
      font-size: 13px;
      font-family: inherit;
      cursor: pointer;
      padding: 6px 8px;
      border-radius: 4px;
    }
    .text-button:hover {
      background: var(--secondary-background-color);
    }
    .text-button.danger {
      color: var(--error-color);
    }
    .text-button.more {
      display: block;
      margin: 8px auto;
    }
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 8px 12px;
    }
    .chip {
      border: 1px solid var(--divider-color);
      background: none;
      color: var(--primary-text-color);
      border-radius: 14px;
      padding: 3px 10px;
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
    }
    /* Chips that are off carry the level color as text only, active ones as a
       fill — the state is therefore legible from the contrast even without
       color vision. */
    .chip.active {
      color: #fff;
      font-weight: 600;
    }
    .chip:not(.active) {
      opacity: 0.7;
    }
    /* Stacked, the card grows with its content; only the scrolling message
       stream is capped. */
    .messages {
      max-height: var(--ln-height, 70vh);
      overflow-y: auto;
      padding: 0 12px 12px;
    }
    .message {
      border-left: 3px solid var(--divider-color);
      padding: 8px 10px;
      margin: 8px 0;
      background: var(--secondary-background-color);
      border-radius: 0 6px 6px 0;
    }
    /* Marks the read position: everything above it is unread. */
    .new-divider {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 10px 0;
      color: var(--error-color);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .new-divider::before,
    .new-divider::after {
      content: "";
      flex: 1;
      height: 2px;
      border-radius: 1px;
      background: var(--error-color);
    }
    .message-head {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      margin-bottom: 4px;
    }
    .message-head.togglable {
      cursor: pointer;
    }
    .message-head:focus-visible {
      outline: 2px solid var(--primary-color);
      outline-offset: 2px;
      border-radius: 2px;
    }
    /* Compact: the head line is all there is, and it stays one line. */
    .message.compact .message-head {
      margin-bottom: 0;
    }
    .message.compact .title,
    .summary {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .summary {
      color: var(--secondary-text-color);
    }
    .message.compact .level,
    .message.compact .source,
    .message.compact .time {
      flex-shrink: 0;
      white-space: nowrap;
    }
    .level-icon {
      --mdc-icon-size: 16px;
    }
    .level {
      font-weight: 700;
      letter-spacing: 0.04em;
    }
    .title {
      font-weight: 600;
      color: var(--primary-text-color);
    }
    .spacer {
      flex: 1;
    }
    .source {
      color: var(--secondary-text-color);
      font-family: var(--code-font-family, monospace);
    }
    .tags {
      margin-top: 6px;
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }
    .tag {
      font-size: 11px;
      padding: 1px 6px;
      border-radius: 8px;
      background: var(--divider-color);
      color: var(--secondary-text-color);
    }

    /* Message body */
    .body {
      font-size: 14px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .body p {
      margin: 4px 0;
      white-space: pre-wrap;
    }
    .body h1,
    .body h2,
    .body h3 {
      margin: 6px 0 2px;
      font-size: 15px;
    }
    .body ul,
    .body ol {
      margin: 4px 0;
      padding-left: 20px;
    }
    .body blockquote {
      margin: 4px 0;
      padding-left: 8px;
      border-left: 3px solid var(--divider-color);
      color: var(--secondary-text-color);
    }
    .body code {
      font-family: var(--code-font-family, monospace);
      background: var(--code-editor-background-color, rgba(127, 127, 127, 0.2));
      border-radius: 3px;
      padding: 0 3px;
    }
    .body pre {
      background: var(--code-editor-background-color, rgba(127, 127, 127, 0.15));
      border-radius: 4px;
      padding: 8px;
      overflow-x: auto;
      margin: 6px 0;
    }
    .body pre code {
      background: none;
      padding: 0;
    }
    .body pre.plain {
      font-family: inherit;
      white-space: pre-wrap;
    }
    .body a {
      color: var(--primary-color);
    }
    /* Label/value grid: one block of equally wide rows; the sender decides
       how many columns each row has. */
    .body .fields {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 6px 0 2px;
    }
    .body .field-row {
      display: grid;
      grid-template-columns: repeat(var(--ln-columns, 1), minmax(0, 1fr));
      gap: 12px;
    }
    .body .field-label {
      font-size: 12px;
      font-weight: 600;
      color: var(--secondary-text-color);
    }
    .body .field-value p {
      margin: 0;
    }
    .body .field-value .plain {
      white-space: pre-wrap;
    }
    /* Sizes, durations and numbers line up digit by digit in a column. */
    .body .formatted {
      font-variant-numeric: tabular-nums;
    }
    /* Tables span the message column like a grid does; a wider one scrolls
       sideways instead of stretching the column — width is only a minimum. */
    .body .table-wrap {
      overflow-x: auto;
      margin: 6px 0 2px;
    }
    .body table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .body th,
    .body td {
      padding: 3px 12px 3px 0;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--divider-color);
    }
    .body th:last-child,
    .body td:last-child {
      padding-right: 0;
    }
    .body th {
      font-size: 12px;
      font-weight: 600;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }
    .body tbody tr:last-child td {
      border-bottom: none;
    }
    .body td.plain {
      white-space: pre-wrap;
    }
    .body .underline {
      text-decoration: underline;
    }
    .body .spoiler {
      background: var(--primary-text-color);
      color: transparent;
      border-radius: 3px;
      cursor: pointer;
    }
    .body .spoiler.revealed {
      background: var(--divider-color);
      color: inherit;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "log-notifier-card": LogNotifierCard;
  }
  interface Window {
    customCards?: unknown[];
  }
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "log-notifier-card",
  name: "Log Notifier",
  description: "Channels and messages from Log Notifier with unread badges",
  preview: false,
  documentationURL: "https://github.com/stefgo/ha-log-notifier",
});
