/** Typed wrapper around the integration's WebSocket commands. */

import type { ChannelSummary, HomeAssistant, Level, LogMessage } from "./types";

export const DOMAIN = "lognotifier";

export const fetchChannels = async (
  hass: HomeAssistant,
): Promise<ChannelSummary[]> => {
  const result = await hass.connection.sendMessagePromise<{
    channels: ChannelSummary[];
  }>({ type: `${DOMAIN}/channels` });
  return result.channels;
};

export const fetchMessages = async (
  hass: HomeAssistant,
  channelId: string,
  options: { before?: number; limit?: number; levels?: Level[] } = {},
): Promise<LogMessage[]> => {
  const result = await hass.connection.sendMessagePromise<{
    messages: LogMessage[];
  }>({
    type: `${DOMAIN}/messages`,
    channel_id: channelId,
    before: options.before,
    limit: options.limit ?? 50,
    levels: options.levels,
  });
  return result.messages;
};

export const markRead = (
  hass: HomeAssistant,
  channelId: string,
  upToId?: number,
): Promise<ChannelSummary> =>
  hass.connection.sendMessagePromise<ChannelSummary>({
    type: `${DOMAIN}/mark_read`,
    channel_id: channelId,
    up_to_id: upToId,
  });

export const clearChannel = (
  hass: HomeAssistant,
  channelId: string,
): Promise<ChannelSummary> =>
  hass.connection.sendMessagePromise<ChannelSummary>({
    type: `${DOMAIN}/clear`,
    channel_id: channelId,
  });

export type StreamEvent =
  | { event: "message"; channel_id: string; message: LogMessage }
  | { event: "channel"; channel: ChannelSummary }
  /** Channels were reconfigured — the whole list arrives anew. */
  | { event: "channels"; channels: ChannelSummary[] };

export const subscribe = (
  hass: HomeAssistant,
  callback: (event: StreamEvent) => void,
): Promise<() => Promise<void>> =>
  hass.connection.subscribeMessage<StreamEvent>(callback, {
    type: `${DOMAIN}/subscribe`,
  });
