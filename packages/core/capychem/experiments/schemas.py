"""Strict version-one experiment intent, independent of tool execution details."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .science_config import (
    MAX_RANDOM_SEED,
    MAX_SMILES_LENGTH,
    PROPERTY_CONSTRAINT_BOUNDS,
    PROTOCOL_TARGETS,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class SuppliedCandidate(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    smiles: str = Field(min_length=1, max_length=MAX_SMILES_LENGTH)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give the candidate a name.")
        return value.strip()


class SuppliedSource(StrictModel):
    kind: Literal["supplied"]
    candidates: list[SuppliedCandidate] = Field(min_length=1, max_length=128)


class LibInventSource(StrictModel):
    kind: Literal["libinvent"]
    raw_proposal_count: int = Field(default=32, ge=2, le=128)
    seed: int = Field(default=43, ge=0, le=MAX_RANDOM_SEED)


class Limits(StrictModel):
    max_unique_candidates_evaluated: int = Field(default=24, ge=1, le=64)
    embedding_attempts_per_candidate: int = Field(default=8, ge=1, le=32)
    evaluation_admission_seconds: int = Field(default=600, ge=10, le=3600)


class Seeds(StrictModel):
    embedding: int = Field(default=194715, ge=0, le=MAX_RANDOM_SEED)
    vina: int = Field(default=42, ge=0, le=MAX_RANDOM_SEED)


class PropertyConstraints(StrictModel):
    max_molecular_weight: float = Field(
        default=450,
        ge=PROPERTY_CONSTRAINT_BOUNDS["max_molecular_weight"][0],
        le=PROPERTY_CONSTRAINT_BOUNDS["max_molecular_weight"][1],
    )
    max_clogp: float = Field(
        default=4.5,
        ge=PROPERTY_CONSTRAINT_BOUNDS["max_clogp"][0],
        le=PROPERTY_CONSTRAINT_BOUNDS["max_clogp"][1],
    )
    max_rotatable_bonds: int = Field(
        default=8,
        ge=PROPERTY_CONSTRAINT_BOUNDS["max_rotatable_bonds"][0],
        le=PROPERTY_CONSTRAINT_BOUNDS["max_rotatable_bonds"][1],
    )
    formal_charge: Literal[0] = 0

    @field_validator("formal_charge", mode="before")
    @classmethod
    def integer_charge(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Formal charge must be the integer zero.")
        return value


class CandidateOrigin(StrictModel):
    candidate_index: int = Field(ge=0, le=127)
    experiment_id: str = Field(max_length=36)
    candidate_id: str = Field(max_length=36)
    pose_id: str | None = Field(default=None, max_length=36)

    @field_validator("experiment_id", "candidate_id", "pose_id")
    @classmethod
    def identity_uuid(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None


class CreateExperiment(StrictModel):
    schema_version: Literal[1] = 1
    label: str = Field(min_length=1, max_length=160)
    target_preparation_id: Literal["cdk2_1h1p", "cdk2_1h1s_nu6094_v1"] = "cdk2_1h1p"
    protocol: Literal["guided_local_cdk2_v1", "guided_growth_cdk2_v2"] = "guided_local_cdk2_v1"
    candidate_source: Annotated[SuppliedSource | LibInventSource, Field(discriminator="kind")]
    limits: Limits = Field(default_factory=Limits)
    seeds: Seeds = Field(default_factory=Seeds)
    constraints: PropertyConstraints = Field(default_factory=PropertyConstraints)
    parent_experiment_id: str | None = Field(default=None, max_length=36)
    candidate_origins: list[CandidateOrigin] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def matching_preparation_protocol(self) -> CreateExperiment:
        if PROTOCOL_TARGETS[self.protocol] != self.target_preparation_id:
            raise ValueError("The selected protocol does not support this target preparation.")
        indices = [origin.candidate_index for origin in self.candidate_origins]
        if len(set(indices)) != len(indices):
            raise ValueError("Each supplied candidate can have only one origin.")
        if self.candidate_origins and (
            self.candidate_source.kind != "supplied"
            or any(index >= len(self.candidate_source.candidates) for index in indices)
        ):
            raise ValueError("Candidate origins must refer to supplied input indices.")
        return self

    @field_validator("parent_experiment_id")
    @classmethod
    def parent_uuid(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema version must be an integer.")
        return value

    @field_validator("label")
    @classmethod
    def trim_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give the experiment a name.")
        return value


class StudyBaseSpec(StrictModel):
    schema_version: Literal[1] = 1
    target_preparation_id: Literal["cdk2_1h1p", "cdk2_1h1s_nu6094_v1"]
    protocol: Literal["guided_local_cdk2_v1", "guided_growth_cdk2_v2"]
    candidate_source: SuppliedSource
    limits: Limits = Field(default_factory=Limits)
    constraints: PropertyConstraints = Field(default_factory=PropertyConstraints)
    parent_experiment_id: str | None = Field(default=None, max_length=36)
    candidate_origins: list[CandidateOrigin] = Field(default_factory=list, max_length=128)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        return CreateExperiment.integer_version(value)


class CreateStudy(StrictModel):
    label: str = Field(min_length=1, max_length=160)
    base_spec: StudyBaseSpec
    seed_pairs: list[Seeds] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def validate_design(self) -> CreateStudy:
        self.label = self.label.strip()
        if not self.label:
            raise ValueError("Give the study a name.")
        if len({(s.embedding, s.vina) for s in self.seed_pairs}) != len(self.seed_pairs):
            raise ValueError(
                "Declare distinct seed pairs; repeating a pair adds no independent run."
            )
        CreateExperiment.model_validate({**self.base_spec.model_dump(), "label": self.label})
        return self


class DecisionRequest(StrictModel):
    pinned: bool = False
    notes: str = Field(default="", max_length=10000)
    preferred_pose_id: str | None = Field(default=None, max_length=36)
    expected_revision: int | None = Field(default=None, ge=0)

    @field_validator("preferred_pose_id")
    @classmethod
    def pose_uuid(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None
