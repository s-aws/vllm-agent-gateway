# Related-Test Discovery Reliability Examples

Run the synthetic gate:

```bash
python3 scripts/validate_related_test_discovery_reliability.py
```

Run the live gate:

```bash
python3 scripts/validate_related_test_discovery_reliability.py --live
```

Direct related-test prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup. Read only. Explain why each command is relevant, what risk it covers, and what gaps remain.
```

No bounded test prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for resolve_payment_timeout. Read only. Explain why each command is relevant, what risk it covers, and what gaps remain.
```

Expected behavior:

- direct cases list evidence-backed test files with confidence and exact pytest commands
- no-test cases state `Related tests: none found in bounded evidence`
- no-test cases expose `verification_tests_not_found`
- source mutation remains false
