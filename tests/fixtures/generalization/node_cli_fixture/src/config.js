export const DEFAULT_PROFILE = process.env.DEFAULT_PROFILE || "sandbox";
export const API_BASE_URL = process.env.API_BASE_URL || "https://api.example.invalid";

export function describeRuntimeConfig() {
  return {
    profile: DEFAULT_PROFILE,
    apiBaseUrl: API_BASE_URL,
  };
}
