// AI-NOTICE:Schema-Version=0.1
// AI-NOTICE:License=AGPL-3.0-or-later
// AI-NOTICE:Project=rita
// AI-NOTICE:Network-Service=AGPL-3.0-or-later section 13 applies

"use strict";

const fs = require("node:fs");
const { isIP } = require("node:net");
const { parseEnv } = require("node:util");

const MANAGED_ENV = "/etc/aimee-main-voice-relay.env";
const MAX_ENV_BYTES = 16384;
const MAX_RESPONSE_BYTES = 65536;
const MAX_INPUT_BYTES = 8192;
const HANDOFF_PATH = "/v1/handoff";
const CALL_PATH = "/v1/internal-calls";
const OPENING_LIMITS = { opening_kind: 64, opening_text: 1024 };
const CONTROL = ["accepted_indeterminate", "rejected", "unknown", "reserved_unknown"];
const PBX_STATE = ["unknown", "ringing", "answered", "active", "ended"];
const CALL_BOOLEAN_FIELDS = [
  "ok",
  "terminal",
  "answer_observed",
  "ext6_gate_observed",
  "readback_available",
  "replay",
];
const OBSERVATION_BOOLEAN_FIELDS = [
  "ext6_auth_pass_observed",
  "lifecycle_subscription_active",
  "lifecycle_observation_available",
  "ext6_auth_observation_available",
];
const CALL_FIELDS = [
  ...CALL_BOOLEAN_FIELDS,
  "request_id",
  "call_id",
  "other_channel_id",
  "target_extension",
  "control_status",
  "pbx_state",
  "observed_at_unix_ms",
  "delivery",
  "human_acknowledgement",
  ...OBSERVATION_BOOLEAN_FIELDS,
  "lifecycle_observation_error",
  "ext6_auth_observation_error",
  "error",
];
const HEALTH_FIELDS = [
  "ok",
  "control_ready",
  "ami_actions_advertised",
  "resolver_readback",
  "durable_store_writable",
];
const HEALTH_OBSERVATION_FIELDS = [
  "ami_event_read_permissions",
  "ami_event_filters",
  "ami_event_read_required",
  "lifecycle_observation_ready",
  "ext6_auth_observation_ready",
  "observation_readiness_error",
];
const SERVER_ERROR_CODES = [
  "internal_state_unavailable_or_invalid",
  "internal_state_busy",
  "ami_observer_not_ready",
  "ami_timeout_unknown",
  "ami_originate_unknown",
  "ami_originate_rejected",
  "ami_readback_timeout",
  "ami_lifecycle_invalid",
  "ami_lifecycle_gap",
  "ami_banner_invalid",
  "ami_login_rejected",
  "ami_channel_readback_invalid",
  "ami_timeout",
  "ami_connect_failed",
  "ami_banner_timeout",
  "ami_banner_failed",
  "ami_write_failed",
  "ami_missing_response",
];

/** @typedef {import("./rita_internal_calls").ClientOptions} ClientOptions */
/** @typedef {import("./rita_internal_calls").OriginateRequest} OriginateRequest */
/** @typedef {import("./rita_internal_calls").StatusRequest} StatusRequest */
/** @typedef {import("./rita_internal_calls").CallReceipt} CallReceipt */
/** @typedef {import("./rita_internal_calls").HealthReceipt} HealthReceipt */
/** @typedef {import("./rita_internal_calls").Result} Result */

const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const exactKeys = (value, keys) =>
  record(value) &&
  Object.keys(value).length === keys.length &&
  keys.every((key) => Object.hasOwn(value, key));
const originateKeys = (value, required) =>
  record(value) &&
  required.every((key) => Object.hasOwn(value, key)) &&
  Object.keys(value).every((key) => required.includes(key) || Object.hasOwn(OPENING_LIMITS, key));
const identity = (value) => typeof value === "string" && /^[A-Za-z0-9_.:-]{8,128}$/u.test(value);
const text = (value, limit) =>
  typeof value === "string" &&
  value.trim().length > 0 &&
  Buffer.byteLength(value, "utf8") <= limit &&
  !/[\u0000-\u001f\u007f-\u009f]/u.test(value);
const opening = (value, limit) =>
  value === null ||
  (typeof value === "string" &&
    Buffer.byteLength(value, "utf8") <= limit &&
    !/[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u.test(value));
const optional = (data, key, valid) => !Object.hasOwn(data, key) || valid(data[key]);
const nullableCode = (value, codes) => value === null || codes.includes(value);
const project = (data, fields) =>
  Object.fromEntries(
    fields.filter((key) => Object.hasOwn(data, key)).map((key) => [key, data[key]]),
  );

function callIdentities(data) {
  if (typeof data.call_id !== "string" || typeof data.other_channel_id !== "string") return false;
  // Schema 2 is exactly 192 bits in unpadded base64url; schema 1 remains readable.
  return (
    (data.call_id.length === 75 &&
      data.other_channel_id.length === 75 &&
      /^rita-int-a-[a-f0-9]{64}$/u.test(data.call_id) &&
      /^rita-int-b-[a-f0-9]{64}$/u.test(data.other_channel_id)) ||
    (data.call_id.length === 32 &&
      data.other_channel_id.length === 32 &&
      /^[A-Za-z0-9_-]{32}$/u.test(data.call_id) &&
      /^[A-Za-z0-9_-]{32}$/u.test(data.other_channel_id))
  );
}

/** @returns {Result} */
function failure(error, httpStatus = null) {
  return { ok: false, http_status: httpStatus, error, receipt: null };
}

function readManagedEnv() {
  let fd;
  try {
    fd = fs.openSync(
      MANAGED_ENV,
      fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK,
    );
    const stat = fs.fstatSync(fd);
    if (
      !stat.isFile() ||
      stat.uid !== 0 ||
      (stat.mode & 0o7777) !== 0o640 ||
      stat.nlink !== 1 ||
      stat.size > MAX_ENV_BYTES
    ) {
      throw new Error("managed_config_unavailable");
    }
    const buffer = Buffer.alloc(MAX_ENV_BYTES + 1);
    const size = fs.readSync(fd, buffer, 0, buffer.length, null);
    if (size > MAX_ENV_BYTES || size !== stat.size) throw new Error("managed_config_unavailable");
    const content = new TextDecoder("utf-8", { fatal: true }).decode(buffer.subarray(0, size));
    const pair = {};
    for (const line of content.split(/\r?\n/u)) {
      const match = /^\s*(PBX_ROUTER_URL|PBX_ROUTER_TOKEN)\s*=\s*(.*)$/u.exec(line);
      if (!match) continue;
      const [, key, raw] = match;
      if (Object.hasOwn(pair, key)) throw new Error("managed_config_unavailable");
      // The managed installer double-quotes with JSON-compatible quote/backslash escaping.
      // parseEnv handles existing unquoted/single-quoted data; nothing is evaluated as shell code.
      pair[key] = raw.startsWith('"') ? JSON.parse(raw) : parseEnv(`${key}=${raw}`)[key];
    }
    return pair;
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

function configuration(options) {
  const env = options.env ?? process.env;
  let pair = {};
  if (env.PBX_ROUTER_URL === undefined || env.PBX_ROUTER_TOKEN === undefined) {
    try {
      pair = (options.readManagedEnv ?? readManagedEnv)();
    } catch (_error) {
      throw new Error("managed_config_unavailable");
    }
  }
  const rawUrl = env.PBX_ROUTER_URL ?? pair.PBX_ROUTER_URL;
  const token = env.PBX_ROUTER_TOKEN ?? pair.PBX_ROUTER_TOKEN;
  const timeoutMs = options.timeoutMs ?? 30000;
  if (
    typeof rawUrl !== "string" ||
    /[\u0000-\u0020\u007f]/u.test(rawUrl) ||
    rawUrl.includes("?") ||
    rawUrl.includes("#") ||
    typeof token !== "string" ||
    !token.length ||
    /[^\x21-\x7e]/u.test(token) ||
    !Number.isInteger(timeoutMs) ||
    timeoutMs < 1 ||
    timeoutMs > 30000
  ) {
    throw new Error("configuration_invalid");
  }
  const url = new URL(rawUrl);
  if (
    url.protocol !== "https:" ||
    !url.hostname ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    isIP(url.hostname.replace(/^\[|\]$/gu, "")) ||
    !url.pathname.endsWith(HANDOFF_PATH)
  ) {
    throw new Error("configuration_invalid");
  }
  url.pathname = url.pathname.slice(0, -HANDOFF_PATH.length) + CALL_PATH;
  return { url: url.href, token, timeoutMs };
}

function callReceipt(data, requestId) {
  if (
    !record(data) ||
    data.request_id !== requestId ||
    !CALL_BOOLEAN_FIELDS.every((key) => typeof data[key] === "boolean") ||
    !callIdentities(data) ||
    typeof data.target_extension !== "string" ||
    !/^[0-9]+$/u.test(data.target_extension) ||
    !CONTROL.includes(data.control_status) ||
    !PBX_STATE.includes(data.pbx_state) ||
    !(
      data.observed_at_unix_ms === null ||
      (Number.isSafeInteger(data.observed_at_unix_ms) && data.observed_at_unix_ms >= 0)
    ) ||
    data.delivery !== "unproven" ||
    data.human_acknowledgement !== "unproven" ||
    !OBSERVATION_BOOLEAN_FIELDS.every((key) =>
      optional(data, key, (value) => typeof value === "boolean"),
    ) ||
    !optional(data, "lifecycle_observation_error", (value) =>
      nullableCode(value, ["ami_lifecycle_gap", "ami_call_events_unverified"]),
    ) ||
    !optional(data, "ext6_auth_observation_error", (value) =>
      nullableCode(value, ["ami_lifecycle_gap", "ami_dialplan_events_unverified"]),
    ) ||
    !optional(data, "error", (value) => value === null || typeof value === "string")
  )
    return null;
  const receipt = project(data, CALL_FIELDS);
  if (
    Object.hasOwn(receipt, "error") &&
    receipt.error !== null &&
    !SERVER_ERROR_CODES.includes(receipt.error)
  ) {
    receipt.error = "router_error_unrecognized";
  }
  return receipt;
}

function healthReceipt(data) {
  if (
    !record(data) ||
    !HEALTH_FIELDS.every((key) => data[key] === true) ||
    data.delivery !== "unproven" ||
    data.human_acknowledgement !== "unproven" ||
    !["ami_event_read_permissions", "ami_event_filters"].every((key) =>
      optional(data, key, (value) => value === "unverified"),
    ) ||
    !optional(
      data,
      "ami_event_read_required",
      (value) =>
        Array.isArray(value) &&
        value.length === 2 &&
        value[0] === "call" &&
        value[1] === "dialplan",
    ) ||
    !["lifecycle_observation_ready", "ext6_auth_observation_ready"].every((key) =>
      optional(data, key, (value) => value === null || typeof value === "boolean"),
    ) ||
    !optional(data, "observation_readiness_error", (value) =>
      nullableCode(value, ["ami_event_permissions_unverified"]),
    )
  )
    return null;
  return project(data, [
    ...HEALTH_FIELDS,
    ...HEALTH_OBSERVATION_FIELDS,
    "delivery",
    "human_acknowledgement",
  ]);
}

async function responseJson(response, signal) {
  if (
    !response.headers.get("content-type")?.toLowerCase().includes("application/json") ||
    !response.body
  ) {
    throw new Error("response_invalid");
  }
  const reader = response.body.getReader();
  const cancel = () => {
    void reader.cancel().catch(() => {});
  };
  signal.addEventListener("abort", cancel, { once: true });
  const chunks = [];
  let size = 0;
  try {
    for (;;) {
      const part = await reader.read();
      if (part.done) break;
      size += part.value.byteLength;
      if (size > MAX_RESPONSE_BYTES) {
        cancel();
        throw new Error("response_invalid");
      }
      chunks.push(Buffer.from(part.value));
    }
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks)));
  } finally {
    signal.removeEventListener("abort", cancel);
    reader.releaseLock();
  }
}

/** @param {ClientOptions} [options] */
function createInternalCallsClient(options = {}) {
  let config;
  let configError;
  try {
    config = configuration(options);
    if (typeof (options.fetchImpl ?? globalThis.fetch) !== "function")
      throw new Error("configuration_invalid");
  } catch (error) {
    configError =
      error?.message === "managed_config_unavailable"
        ? "managed_config_unavailable"
        : "configuration_invalid";
  }
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;

  /** @returns {Promise<Result>} */
  async function request(suffix, body) {
    if (configError) return failure(configError);
    const controller = new AbortController();
    let httpStatus = null;
    let timer;
    const expired = new Promise((resolve) => {
      timer = setTimeout(() => {
        resolve(failure("request_timeout", httpStatus));
        controller.abort();
      }, config.timeoutMs);
    });
    const operation = (async () => {
      try {
        const response = await fetchImpl(config.url + suffix, {
          method: body === undefined ? "GET" : "POST",
          redirect: "error",
          signal: controller.signal,
          headers: {
            Authorization: `Bearer ${config.token}`,
            Accept: "application/json",
            ...(body === undefined ? {} : { "Content-Type": "application/json" }),
          },
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        });
        httpStatus = response.status;
        if (controller.signal.aborted) return failure("request_timeout", httpStatus);
        if (response.redirected) {
          controller.abort();
          return failure("redirect_rejected", httpStatus);
        }
        const expectedStatus = body === undefined || suffix === "/status" ? [200] : [200, 202];
        const expected = expectedStatus.includes(httpStatus);
        // Error-only responses are not inspected. A 502 may contain a durable/cached PBX receipt.
        if (!expected && httpStatus !== 502) {
          controller.abort();
          return failure("router_http_error", httpStatus);
        }
        let receipt;
        try {
          const data = await responseJson(response, controller.signal);
          receipt = body === undefined ? healthReceipt(data) : callReceipt(data, body.request_id);
        } catch (_error) {
          return failure(expected ? "response_invalid" : "router_http_error", httpStatus);
        }
        if (!receipt)
          return failure(expected ? "response_invalid" : "router_http_error", httpStatus);
        const ok = expected && receipt.ok;
        return {
          ok,
          http_status: httpStatus,
          error: ok ? null : expected ? "router_not_ok" : "router_http_error",
          receipt,
        };
      } catch (_error) {
        return failure(
          controller.signal.aborted ? "request_timeout" : "transport_unavailable",
          httpStatus,
        );
      }
    })();
    try {
      return await Promise.race([operation, expired]);
    } finally {
      clearTimeout(timer);
    }
  }

  return Object.freeze({
    health: () => request("/health"),
    /** @param {OriginateRequest} input */
    originate: async (input) => {
      if (!originateKeys(input, ["request_id", "target", "purpose"])) return failure("invalid_request");
      if (!identity(input.request_id)) return failure("invalid_identity");
      if (!text(input.target, 96)) return failure("invalid_target");
      if (!text(input.purpose, 700)) return failure("invalid_purpose");
      for (const [key, limit] of Object.entries(OPENING_LIMITS)) {
        if (!optional(input, key, (value) => opening(value, limit))) return failure(`invalid_${key}`);
      }
      return request("", project(input, ["request_id", "target", "purpose", ...Object.keys(OPENING_LIMITS)]));
    },
    /** @param {StatusRequest} input */
    status: async (input) => {
      if (!exactKeys(input, ["request_id"])) return failure("invalid_request");
      if (!identity(input.request_id)) return failure("invalid_identity");
      return request("/status", { request_id: input.request_id });
    },
  });
}

/** @param {string} raw @param {ClientOptions} [options] @returns {Promise<Result>} */
async function runJsonRequest(raw, options = {}) {
  let input;
  try {
    if (typeof raw !== "string" || Buffer.byteLength(raw) > MAX_INPUT_BYTES)
      return failure("invalid_request");
    input = JSON.parse(raw);
  } catch (_error) {
    return failure("invalid_request");
  }
  if (!record(input)) return failure("invalid_request");
  const { operation, ...body } = input;
  if (operation === "health" && exactKeys(input, ["operation"]))
    return createInternalCallsClient(options).health();
  if (
    operation === "originate" &&
    originateKeys(input, ["operation", "request_id", "target", "purpose"])
  ) {
    return createInternalCallsClient(options).originate(body);
  }
  if (operation === "status" && exactKeys(input, ["operation", "request_id"])) {
    return createInternalCallsClient(options).status(body);
  }
  return failure("invalid_request");
}

module.exports = { createInternalCallsClient, runJsonRequest };

if (require.main === module) {
  (async () => {
    let result;
    try {
      if (process.argv.length !== 2) result = failure("invalid_request");
      else {
        let size = 0;
        const chunks = [];
        for await (const chunk of process.stdin) {
          size += chunk.length;
          if (size > MAX_INPUT_BYTES) break;
          chunks.push(chunk);
        }
        result =
          size > MAX_INPUT_BYTES
            ? failure("invalid_request")
            : await runJsonRequest(Buffer.concat(chunks).toString("utf8"));
      }
    } catch (_error) {
      result = failure("client_error");
    }
    process.stdout.write(JSON.stringify(result) + "\n");
    process.exitCode = result.ok ? 0 : 1;
  })();
}
