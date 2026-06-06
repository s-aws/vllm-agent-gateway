# Security Policy

The security policy gate is a read-only release-candidate check for unsafe tester setup, secret exposure, protected fixture mutation risk, destructive command fragments, and unsafe onboarding prompts.

It is not a runtime firewall. It is a release gate that must pass before broader tester distribution.

## Source Of Truth

Policy manifest:

```text
runtime/security_policy.json
```

Validator:

```bash
python scripts/validate_security_policy.py
```

Reports:

```text
runtime-state/security-policy/
```

## What It Checks

- Required security docs, examples, scripts, and runtime policy files exist.
- Configured secret environment variable values are not present in scanned docs, runtime files, scripts, gateway code, or recent runtime artifacts.
- Allowed tester roots are not broad filesystem roots such as `/`, `/mnt/c`, or `C:/`.
- Protected fixture entries remain `protected=true` and `disposable_only=true`.
- Onboarding prompts stay read-only and do not ask for secrets, environment dumps, refactors, implementation prep, or source mutation.
- Project command files do not contain configured destructive command fragments.

The validator does not print secret values. If a configured secret is found in a scanned file, the report records only the secret environment variable name and file path.

## Run The Gate

From Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_security_policy.py \
  --output-path runtime-state/security-policy/current.json
```

Expected markers:

```text
SECURITY POLICY REPORT ...
SECURITY POLICY SUMMARY ...
SECURITY POLICY PASS
```

If `ANYTHINGLLM_API_KEY` is not available, the secret value scan is skipped. That is acceptable for local development, but release-candidate proof should run with the key available so recent artifacts are scanned for accidental exposure.

## Tester Policy

Allowed tester actions:

- run the first-time user doctor
- validate release channels
- run external tester onboarding prompts
- record workflow feedback
- inspect generated artifacts

Disallowed tester actions:

- paste or request real secret values
- ask the harness to print environment variables or dump secrets
- change protected frozen fixture source files
- run broad refactor prompts during onboarding
- approve repository mutation without disposable-copy proof
- point AnythingLLM at the controller service port `8400`

AnythingLLM natural workflow testing should point at:

```text
http://127.0.0.1:8500/v1
```

## Failure Handling

If the security policy gate fails:

1. Open the report under `runtime-state/security-policy/`.
2. Review `summary.failed_check_ids`.
3. Fix the specific policy, doc, prompt, fixture, command, or artifact issue.
4. If a real secret value appeared in an artifact or source-controlled file, remove it and rotate the secret.
5. Rerun the validator before continuing tester release work.

Examples: [docs/examples/security-policy.md](docs/examples/security-policy.md).
