/**
 * The card's UI texts in the viewer's language.
 *
 * Home Assistant translates an integration's dialogs and entities, but hands a
 * custom card nothing — so the card carries its own texts. English is the
 * source and the fallback for every language without a table of its own.
 *
 * Level names are not in here: ERROR, WARNING, INFO and TRACE are identifiers
 * that read the same in YAML and automations.
 */

const en = {
  back: "Back",
  show_detail: "Show detail",
  show_compact: "Show compact",
  mark_all_read: "Mark all read",
  clear: "Clear",
  clear_confirm: 'Delete all messages in "{name}"?',
  load_older: "Load older",
  loading: "Loading …",
  new_divider: "New",
  no_messages: "No messages.",
  no_level: "No level selected — switch on at least one above.",
  select_channel: "Select a channel.",
  just_now: "just now",
  error_channels: "Could not load channels: {error}",
  error_messages: "Could not load messages: {error}",
  editor_title: "Title",
  editor_channels: "Channels (empty = all)",
  editor_levels: "Displayed levels (empty = all)",
  editor_layout: "Layout",
  editor_height: "Height (e.g. 70vh or 500px)",
  editor_page_size: "Messages per load step",
  editor_mark_read: "Mark as read",
  layout_auto: "Automatic",
  layout_split: "Always two columns",
  layout_stacked: "Always stacked",
  mark_read_manual: "Button only",
  mark_read_visible: "When everything was seen",
  mark_read_open: "When the channel is opened",
};

export type TextKey = keyof typeof en;

/** Typed against the source, so a missing or surplus key fails the type check. */
type Texts = Record<TextKey, string>;

// Kept short on purpose: the toolbar has to fit a phone.
const de: Texts = {
  back: "Zurück",
  show_detail: "Details",
  show_compact: "Kompakt",
  mark_all_read: "Alle gelesen",
  clear: "Leeren",
  clear_confirm: "Alle Meldungen in „{name}“ löschen?",
  load_older: "Ältere laden",
  loading: "Lädt …",
  new_divider: "Neu",
  no_messages: "Keine Meldungen.",
  no_level: "Kein Level gewählt — oben mindestens eines einschalten.",
  select_channel: "Kanal wählen.",
  just_now: "gerade eben",
  error_channels: "Kanäle konnten nicht geladen werden: {error}",
  error_messages: "Meldungen konnten nicht geladen werden: {error}",
  editor_title: "Titel",
  editor_channels: "Kanäle (leer = alle)",
  editor_levels: "Angezeigte Level (leer = alle)",
  editor_layout: "Layout",
  editor_height: "Höhe (z. B. 70vh oder 500px)",
  editor_page_size: "Meldungen pro Ladeschritt",
  editor_mark_read: "Als gelesen markieren",
  layout_auto: "Automatisch",
  layout_split: "Immer zweispaltig",
  layout_stacked: "Immer gestapelt",
  mark_read_manual: "Nur per Schaltfläche",
  mark_read_visible: "Wenn alles gesehen wurde",
  mark_read_open: "Beim Öffnen des Kanals",
};

export const TEXTS: Readonly<Record<string, Texts>> = { en, de };

/** Own keys only — "constructor" is neither a language nor a placeholder. */
const hasOwn = (object: object, key: string): boolean =>
  Object.prototype.hasOwnProperty.call(object, key);

/** `de-AT` and `de_CH` are German; anything without a table is English. */
function textsFor(language: string | undefined): Texts {
  const base = (language ?? "").toLowerCase().split(/[-_]/)[0];
  return hasOwn(TEXTS, base) ? TEXTS[base] : en;
}

/**
 * The text for `key` in `language`, with `{name}` placeholders filled from
 * `values`. A placeholder without a value stays as it is.
 */
export function localize(
  language: string | undefined,
  key: TextKey,
  values: Record<string, string> = {},
): string {
  return textsFor(language)[key].replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    hasOwn(values, name) ? values[name] : placeholder,
  );
}
