"""Release-gate profile contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class LiveGuardLevel(str, Enum):
    NONE = "none"
    SMOKE = "smoke"
    FULL = "full"


class ReleaseGateProfile(str, Enum):
    OFFLINE = "offline"
    MUTATION = "mutation"
    LIVE_SMOKE = "live-smoke"
    LIVE_FULL = "live-full"
    RELEASE_CANDIDATE = "release-candidate"


@dataclass(frozen=True)
class ReleaseGateProfileContract:
    profile: ReleaseGateProfile
    description: str
    includes_static: bool
    includes_mutation: bool
    live_guard_level: LiveGuardLevel
    includes_anythingllm: bool
    final_gate: bool


PROFILE_CONTRACTS: dict[ReleaseGateProfile, ReleaseGateProfileContract] = {
    ReleaseGateProfile.OFFLINE: ReleaseGateProfileContract(
        profile=ReleaseGateProfile.OFFLINE,
        description="Static registry, eval, scale, selector, docs, and focused regression proof only.",
        includes_static=True,
        includes_mutation=False,
        live_guard_level=LiveGuardLevel.NONE,
        includes_anythingllm=False,
        final_gate=False,
    ),
    ReleaseGateProfile.MUTATION: ReleaseGateProfileContract(
        profile=ReleaseGateProfile.MUTATION,
        description="Offline proof plus disposable-copy mutation and fault-injection proof.",
        includes_static=True,
        includes_mutation=True,
        live_guard_level=LiveGuardLevel.NONE,
        includes_anythingllm=False,
        final_gate=False,
    ),
    ReleaseGateProfile.LIVE_SMOKE: ReleaseGateProfileContract(
        profile=ReleaseGateProfile.LIVE_SMOKE,
        description="Mutation profile plus the shortest Bash-hosted live lifecycle guard.",
        includes_static=True,
        includes_mutation=True,
        live_guard_level=LiveGuardLevel.SMOKE,
        includes_anythingllm=False,
        final_gate=False,
    ),
    ReleaseGateProfile.LIVE_FULL: ReleaseGateProfileContract(
        profile=ReleaseGateProfile.LIVE_FULL,
        description="Mutation profile plus all Bash-hosted live guards without AnythingLLM.",
        includes_static=True,
        includes_mutation=True,
        live_guard_level=LiveGuardLevel.FULL,
        includes_anythingllm=False,
        final_gate=False,
    ),
    ReleaseGateProfile.RELEASE_CANDIDATE: ReleaseGateProfileContract(
        profile=ReleaseGateProfile.RELEASE_CANDIDATE,
        description="Mutation profile plus all live guards through AnythingLLM.",
        includes_static=True,
        includes_mutation=True,
        live_guard_level=LiveGuardLevel.FULL,
        includes_anythingllm=True,
        final_gate=True,
    ),
}


def release_gate_profile_values() -> list[str]:
    return [profile.value for profile in ReleaseGateProfile]


def release_gate_profile_contract(profile: ReleaseGateProfile) -> ReleaseGateProfileContract:
    return PROFILE_CONTRACTS[profile]


def release_gate_profile_contract_json(profile: ReleaseGateProfile) -> dict[str, object]:
    contract = asdict(release_gate_profile_contract(profile))
    contract["profile"] = profile.value
    contract["live_guard_level"] = release_gate_profile_contract(profile).live_guard_level.value
    return contract
