import assert from "node:assert";
import { describeRuntimeConfig } from "../src/config.js";

const config = describeRuntimeConfig();

assert.equal(typeof config.profile, "string");
assert.equal(typeof config.apiBaseUrl, "string");
