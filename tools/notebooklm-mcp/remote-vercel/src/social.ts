export const SOCIAL_PROVIDERS = [
  "youtube",
  "telegram",
  "instagram",
  "facebook",
  "tiktok",
  "vk",
  "line",
  "dzen",
] as const;

export type SocialProvider = (typeof SOCIAL_PROVIDERS)[number];

const WRITES_ENABLED =
  (process.env.ND_SOCIAL_WRITES_ENABLED ?? "false").trim().toLowerCase() === "true";

const REQUIREMENTS: Record<
  SocialProvider,
  {
    state: string;
    officialApi: boolean;
    authMode: string;
    secretNames: string[];
    idNames: string[];
    callbackUrl?: string;
    scopes?: string[];
    notes?: string[];
  }
> = {
  youtube: {
    state: "READY_FOR_AUTH",
    officialApi: true,
    authMode: "oauth2_authorization_code_refresh_token",
    secretNames: [
      "ND_YOUTUBE_CLIENT_ID",
      "ND_YOUTUBE_CLIENT_SECRET",
      "ND_YOUTUBE_REFRESH_TOKEN",
    ],
    idNames: ["ND_YOUTUBE_CHANNEL_ID"],
    callbackUrl:
      "https://nd-notebooklm-remote-mcp.vercel.app/api/social-oauth/youtube/callback",
    scopes: [
      "https://www.googleapis.com/auth/youtube.force-ssl",
      "https://www.googleapis.com/auth/youtube.upload",
      "https://www.googleapis.com/auth/yt-analytics.readonly",
    ],
    notes: [
      "Canonical channel is the new ND YouTube under namelessdhamma@gmail.com.",
      "Legacy personal YouTube is excluded from production publishing.",
    ],
  },
  telegram: {
    state: "READY_FOR_TOKEN",
    officialApi: true,
    authMode: "bot_token",
    secretNames: ["ND_TELEGRAM_BOT_TOKEN"],
    idNames: ["ND_TELEGRAM_CHANNEL_ID"],
    notes: ["Channel identity: @namelessdhamma."],
  },
  instagram: {
    state: "READY_FOR_AUTH",
    officialApi: true,
    authMode: "meta_oauth_shared_with_facebook",
    secretNames: ["ND_META_USER_ACCESS_TOKEN"],
    idNames: ["ND_INSTAGRAM_USER_ID", "ND_FACEBOOK_PAGE_ID"],
    callbackUrl:
      "https://nd-notebooklm-remote-mcp.vercel.app/api/social-oauth/meta/callback",
    scopes: [
      "instagram_basic",
      "instagram_content_publish",
      "instagram_manage_comments",
      "instagram_manage_insights",
      "pages_show_list",
      "pages_read_engagement",
    ],
    notes: ["Share one Meta app/OAuth flow with Facebook."],
  },
  facebook: {
    state: "READY_FOR_AUTH",
    officialApi: true,
    authMode: "meta_oauth_shared_with_instagram",
    secretNames: ["ND_META_USER_ACCESS_TOKEN"],
    idNames: ["ND_FACEBOOK_PAGE_ID"],
    callbackUrl:
      "https://nd-notebooklm-remote-mcp.vercel.app/api/social-oauth/meta/callback",
    scopes: [
      "pages_show_list",
      "pages_read_engagement",
      "pages_manage_posts",
      "read_insights",
    ],
    notes: ["Share one Meta app/OAuth flow with Instagram."],
  },
  tiktok: {
    state: "READY_FOR_APP_AUTH",
    officialApi: true,
    authMode: "oauth2_authorization_code_refresh_token",
    secretNames: [
      "ND_TIKTOK_CLIENT_KEY",
      "ND_TIKTOK_CLIENT_SECRET",
      "ND_TIKTOK_REFRESH_TOKEN",
    ],
    idNames: ["ND_TIKTOK_OPEN_ID"],
    callbackUrl:
      "https://nd-notebooklm-remote-mcp.vercel.app/api/social-oauth/tiktok/callback",
    scopes: ["user.info.basic", "user.info.stats", "video.list", "video.publish", "video.upload"],
    notes: [
      "Public Direct Post requires TikTok approval/audit.",
      "Unaudited clients are restricted for Direct Post visibility.",
    ],
  },
  vk: {
    state: "READY_FOR_CREDENTIAL_BINDING",
    officialApi: true,
    authMode: "community_access_token",
    secretNames: ["VK_GROUP_TOKEN"],
    idNames: ["VK_GROUP_ID"],
    notes: ["Reuse the existing ND VK credential before any new app/token flow."],
  },
  line: {
    state: "READY_FOR_CHANNEL_AUTH",
    officialApi: true,
    authMode: "messaging_api_channel_access_token",
    secretNames: ["ND_LINE_CHANNEL_ACCESS_TOKEN", "ND_LINE_CHANNEL_SECRET"],
    idNames: ["ND_LINE_CHANNEL_ID"],
    notes: ["Reuse the existing ND LINE Official Account."],
  },
  dzen: {
    state: "READY_FOR_SESSION_AUTH_EXPERIMENTAL",
    officialApi: false,
    authMode: "authenticated_session_cookie",
    secretNames: ["ND_DZEN_SESSION_BUNDLE"],
    idNames: ["ND_DZEN_CHANNEL_ID"],
    notes: [
      "No current public official publishing API is qualified.",
      "Direct route is experimental and must fail closed on behavior changes.",
    ],
  },
};

function envPresent(name: string): boolean {
  return Boolean((process.env[name] ?? "").trim());
}

export function authRequirements(provider: SocialProvider) {
  return {
    provider,
    identity: {
      email: "namelessdhamma@gmail.com",
      handle: "@namelessdhamma",
    },
    ...REQUIREMENTS[provider],
  };
}

export function readiness(provider: SocialProvider) {
  const spec = REQUIREMENTS[provider];
  const missingSecrets = spec.secretNames.filter((name) => !envPresent(name));
  const missingIds = spec.idNames.filter((name) => !envPresent(name));

  return {
    ok: missingSecrets.length === 0 && missingIds.length === 0,
    provider,
    state: spec.state,
    officialApi: spec.officialApi,
    authMode: spec.authMode,
    missingSecretNames: missingSecrets,
    missingIdNames: missingIds,
    callbackUrl: spec.callbackUrl ?? null,
    writesEnabled: WRITES_ENABLED,
  };
}

async function jsonFetch(
  url: string,
  init: RequestInit = {},
): Promise<{ status: number; body: any }> {
  const response = await fetch(url, {
    ...init,
    cache: "no-store",
  });
  let body: any = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  if (!response.ok) {
    throw new Error(`UPSTREAM_HTTP_${response.status}`);
  }
  return { status: response.status, body };
}

function required(names: string[]) {
  const missing = names.filter((name) => !envPresent(name));
  if (missing.length) {
    throw new Error(`AWAITING_AUTH:${missing.join(",")}`);
  }
}

async function youtubeAccessToken(): Promise<string> {
  required([
    "ND_YOUTUBE_CLIENT_ID",
    "ND_YOUTUBE_CLIENT_SECRET",
    "ND_YOUTUBE_REFRESH_TOKEN",
  ]);
  const body = new URLSearchParams({
    client_id: process.env.ND_YOUTUBE_CLIENT_ID!,
    client_secret: process.env.ND_YOUTUBE_CLIENT_SECRET!,
    refresh_token: process.env.ND_YOUTUBE_REFRESH_TOKEN!,
    grant_type: "refresh_token",
  });
  const result = await jsonFetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const token = String(result.body?.access_token ?? "");
  if (!token) throw new Error("youtube_refresh_failed");
  return token;
}

async function youtubeStatus() {
  const token = await youtubeAccessToken();
  const query = new URLSearchParams({
    part: "id,snippet,statistics",
    mine: "true",
    maxResults: "10",
  });
  const { body } = await jsonFetch(
    `https://www.googleapis.com/youtube/v3/channels?${query.toString()}`,
    { headers: { authorization: `Bearer ${token}` } },
  );
  const accounts = (body?.items ?? []).map((item: any) => ({
    id: item?.id ?? null,
    title: item?.snippet?.title ?? null,
    customUrl: item?.snippet?.customUrl ?? null,
    subscriberCount: item?.statistics?.subscriberCount ?? null,
    videoCount: item?.statistics?.videoCount ?? null,
    viewCount: item?.statistics?.viewCount ?? null,
  }));
  return { transport: "vercel_to_youtube_api", accounts };
}

async function telegramStatus() {
  required(["ND_TELEGRAM_BOT_TOKEN"]);
  const token = process.env.ND_TELEGRAM_BOT_TOKEN!;
  const { body: me } = await jsonFetch(
    `https://api.telegram.org/bot${token}/getMe`,
  );
  const result: any = { transport: "vercel_to_telegram_bot_api", bot: me?.result ?? null };
  const chatId = (process.env.ND_TELEGRAM_CHANNEL_ID ?? "").trim();
  if (chatId) {
    const q = new URLSearchParams({ chat_id: chatId });
    const { body: chat } = await jsonFetch(
      `https://api.telegram.org/bot${token}/getChat?${q.toString()}`,
    );
    result.channel = chat?.result ?? null;
  }
  return result;
}

async function metaGet(path: string, params: Record<string, string>) {
  required(["ND_META_USER_ACCESS_TOKEN"]);
  const version = (process.env.ND_META_GRAPH_VERSION ?? "v24.0").trim() || "v24.0";
  const q = new URLSearchParams({
    ...params,
    access_token: process.env.ND_META_USER_ACCESS_TOKEN!,
  });
  return jsonFetch(
    `https://graph.facebook.com/${version}/${path.replace(/^\//, "")}?${q.toString()}`,
  );
}

async function facebookStatus() {
  const pageId = (process.env.ND_FACEBOOK_PAGE_ID ?? "").trim();
  if (pageId) {
    const { body } = await metaGet(pageId, {
      fields: "id,name,username,followers_count",
    });
    return { transport: "vercel_to_meta_graph_api", page: body };
  }
  const { body } = await metaGet("me/accounts", {
    fields: "id,name,username",
  });
  return {
    transport: "vercel_to_meta_graph_api",
    pages: body?.data ?? [],
  };
}

async function instagramStatus() {
  required(["ND_META_USER_ACCESS_TOKEN", "ND_INSTAGRAM_USER_ID"]);
  const { body } = await metaGet(process.env.ND_INSTAGRAM_USER_ID!, {
    fields: "id,username,account_type,media_count",
  });
  return { transport: "vercel_to_instagram_graph_api", account: body };
}

async function tiktokAccessToken(): Promise<string> {
  const direct = (process.env.ND_TIKTOK_ACCESS_TOKEN ?? "").trim();
  if (direct) return direct;
  required([
    "ND_TIKTOK_CLIENT_KEY",
    "ND_TIKTOK_CLIENT_SECRET",
    "ND_TIKTOK_REFRESH_TOKEN",
  ]);
  const form = new URLSearchParams({
    client_key: process.env.ND_TIKTOK_CLIENT_KEY!,
    client_secret: process.env.ND_TIKTOK_CLIENT_SECRET!,
    grant_type: "refresh_token",
    refresh_token: process.env.ND_TIKTOK_REFRESH_TOKEN!,
  });
  const { body } = await jsonFetch("https://open.tiktokapis.com/v2/oauth/token/", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: form,
  });
  const token = String(body?.access_token ?? "");
  if (!token) throw new Error("tiktok_refresh_failed");
  return token;
}

async function tiktokStatus() {
  const token = await tiktokAccessToken();
  const q = new URLSearchParams({
    fields: "open_id,union_id,avatar_url,display_name",
  });
  const { body } = await jsonFetch(
    `https://open.tiktokapis.com/v2/user/info/?${q.toString()}`,
    { headers: { authorization: `Bearer ${token}` } },
  );
  return {
    transport: "vercel_to_tiktok_api",
    account: body?.data?.user ?? {},
  };
}

async function vkStatus() {
  required(["VK_GROUP_TOKEN"]);
  const group =
    (process.env.VK_GROUP_ID ?? "").trim() ||
    (process.env.VK_GROUP_SCREEN_NAME ?? "").trim() ||
    "namelessdhamma";
  const version = (process.env.VK_API_VERSION ?? "5.199").trim() || "5.199";
  const q = new URLSearchParams({
    group_id: group,
    fields: "members_count,screen_name,name",
    access_token: process.env.VK_GROUP_TOKEN!,
    v: version,
  });
  const { body } = await jsonFetch(
    `https://api.vk.com/method/groups.getById?${q.toString()}`,
  );
  if (body?.error) throw new Error("vk_api_error");
  return {
    transport: "vercel_to_vk_api",
    group: body?.response ?? null,
  };
}

async function lineStatus() {
  required(["ND_LINE_CHANNEL_ACCESS_TOKEN"]);
  const { body } = await jsonFetch("https://api.line.me/v2/bot/info", {
    headers: {
      authorization: `Bearer ${process.env.ND_LINE_CHANNEL_ACCESS_TOKEN!}`,
    },
  });
  return { transport: "vercel_to_line_messaging_api", account: body };
}

async function dzenStatus() {
  required(["ND_DZEN_SESSION_BUNDLE"]);
  return {
    transport: "vercel_to_dzen_experimental_session",
    status: "SESSION_PRESENT_UNQUALIFIED",
    experimental: true,
    officialApi: false,
  };
}

const STATUS_ROUTERS: Record<SocialProvider, () => Promise<any>> = {
  youtube: youtubeStatus,
  telegram: telegramStatus,
  instagram: instagramStatus,
  facebook: facebookStatus,
  tiktok: tiktokStatus,
  vk: vkStatus,
  line: lineStatus,
  dzen: dzenStatus,
};

export async function invokeSocial(
  provider: SocialProvider,
  operation: string,
): Promise<any> {
  const op = operation.trim().toLowerCase();
  if (op === "status" || op === "account") {
    return STATUS_ROUTERS[provider]();
  }
  if (!WRITES_ENABLED) {
    throw new Error("WRITE_NOT_QUALIFIED");
  }
  throw new Error(`${provider}_operation_not_implemented`);
}
