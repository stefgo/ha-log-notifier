/** Types shared by the card, the API layer and the editor. */

export type Level = "ERROR" | "WARNING" | "INFO" | "TRACE";

/** How the card shows a value the sender sent as a plain number or date. */
export type ValueFormat = "bytes" | "bytes_si" | "duration" | "datetime" | "number";

/** One cell of a message's label/value grid. */
export interface MessageField {
  label: string;
  value: string;
  /** Columns the field takes; left out for one. */
  span?: number;
  format?: ValueFormat;
}

/** One column of a table head; without `align` the column is left-aligned. */
export interface TableColumn {
  label: string;
  align?: "left" | "center" | "right";
  /** Applies to every cell of the column. */
  format?: ValueFormat;
}

/** A block below the content; the list keeps the sender's order. */
export type MessageBlock =
  | { type: "text"; text: string }
  | { type: "fields"; rows: MessageField[][] }
  /** Every row has one cell per column; `columns` is empty for a headless table. */
  | { type: "table"; columns: TableColumn[]; rows: string[][] };

export interface LogMessage {
  id: number;
  ts: number;
  level: Level;
  content: string;
  title?: string;
  source?: string;
  tags?: string[];
  format?: "markdown" | "plain";
  /** Text, field grids and tables below the content, in any order. */
  blocks?: MessageBlock[];
}

export interface ChannelSummary {
  id: string;
  name: string;
  icon: string;
  enabled: boolean;
  /** Levels that count towards the unread badge — a selection, not a threshold. */
  badge_levels: Level[];
  unread: number;
  unread_by_level: Partial<Record<Level, number>>;
  highest_unread_level: Level | null;
  last_read_id: number;
  total: number;
  last_message: LogMessage | null;
}

export interface LogNotifierCardConfig {
  type: string;
  title?: string;
  /** "all" or a list of channel IDs. */
  channels?: "all" | string[];
  /**
   * Levels active initially. Every level stands on its own — there is no
   * threshold. If omitted, all four are active.
   */
  levels?: Level[];
  /** How many messages are fetched per load-more step. */
  page_size?: number;
  /**
   * Height of the message area as a CSS length (`70vh`, `500px`, …) or a
   * number in pixels. In the two-column layout it is the height of the card,
   * stacked it is the height of the scrolling message stream.
   */
  height?: string | number;
  /**
   * When messages count as read: `manual` only via the button (default),
   * `visible` once all unread ones actually appeared on screen, `open` as soon
   * as the channel is opened.
   */
  mark_read?: "manual" | "visible" | "open";
  /**
   * "auto" (default): two columns as soon as the card is wide enough,
   * otherwise drill-down as on a phone. "split"/"stacked" force one of the
   * two.
   */
  layout?: "auto" | "split" | "stacked";
}

/** The slice of the hass object that the card uses. */
export interface HomeAssistant {
  locale?: { language?: string };
  language?: string;
  user?: { is_admin?: boolean };
  connection: {
    sendMessagePromise<T>(message: Record<string, unknown>): Promise<T>;
    subscribeMessage<T>(
      callback: (message: T) => void,
      subscribeMessage: Record<string, unknown>,
    ): Promise<() => Promise<void>>;
  };
}
