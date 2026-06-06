import { describeRuntimeConfig } from "./config.js";

export function main(argv = process.argv.slice(2)) {
  const config = describeRuntimeConfig();
  const command = argv[0] || "status";
  return `${command}:${config.profile}:${config.apiBaseUrl}`;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  console.log(main());
}
