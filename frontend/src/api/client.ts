import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type SourceMode = Schemas["Envelope_DecisionListOut_"]["source_mode"];

/** Every response carries where its data came from. Nothing here drops it. */
export interface Envelope<T> {
  schema_version: string;
  source_mode: SourceMode;
  source_label: string;
  observed_at: string;
  correlation_id: string | null;
  data: T;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Path = keyof paths;

declare const urlBrand: unique symbol;
/** A URL built from a path the server actually publishes. */
export type ApiUrl = string & { readonly [urlBrand]: "api" };

/** Fails to compile if the template is not a published path. */
const published = <P extends Path>(path: P): P => path;

/**
 * Every URL the client can ask for, built from the generated contract.
 *
 * `get` takes only these. Accepting a bare string would make the generated path
 * union decorative -- any typo would type-check -- which is the opposite of why
 * the types are generated from the server's own schema.
 */
export const api = {
  status: () => published("/api/v1/system/status") as ApiUrl,
  copy: () => published("/api/v1/copy") as ApiUrl,
  groupedDecisions: (view: string) =>
    `${published("/api/v1/decisions/grouped")}?view=${encodeURIComponent(view)}` as ApiUrl,
  summary: (digest: string) =>
    published("/api/v1/decisions/{digest}/summary").replace("{digest}", digest) as ApiUrl,
  market: (digest: string) =>
    published("/api/v1/decisions/{digest}/market").replace("{digest}", digest) as ApiUrl,
  outcomes: (digest: string) =>
    published("/api/v1/decisions/{digest}/outcomes").replace("{digest}", digest) as ApiUrl,
  memo: (digest: string) =>
    published("/api/v1/decisions/{digest}/memo").replace("{digest}", digest) as ApiUrl,
  structure: (digest: string) =>
    published("/api/v1/decisions/{digest}/structure").replace("{digest}", digest) as ApiUrl,
  risk: (digest: string) =>
    published("/api/v1/decisions/{digest}/risk").replace("{digest}", digest) as ApiUrl,
  lifecycle: (digest: string) =>
    published("/api/v1/decisions/{digest}/lifecycle").replace("{digest}", digest) as ApiUrl,
  proof: (digest: string) =>
    published("/api/v1/decisions/{digest}/proof").replace("{digest}", digest) as ApiUrl,
  proofTiles: () => published("/api/v1/system/proof") as ApiUrl,
  reviewOverview: () => published("/api/v1/outcomes") as ApiUrl,
  tour: () => published("/api/v1/tour") as ApiUrl,
};

/**
 * Same-origin GET. There is no POST helper and no body parameter, because the
 * API publishes no write method: a client that cannot express one cannot drift
 * into attempting one.
 */
export async function get<T>(path: ApiUrl, signal?: AbortSignal): Promise<Envelope<T>> {
  const response = await fetch(path, {
    signal: signal ?? null,
    headers: { accept: "application/json" },
  });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as Envelope<T>;
}
