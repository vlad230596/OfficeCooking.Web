from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .base import ApiModel


class PreparationOption(ApiModel):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    values: list[str] = Field(min_length=1, max_length=30)
    batch_size: int = Field(default=1, ge=1, le=1000)

    @field_validator("key", "name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("values")
    @classmethod
    def valid_values(cls, values: list[str]) -> list[str]:
        result = [value.strip() for value in values]
        if any(not value or len(value) > 200 for value in result):
            raise ValueError("option values must contain 1..200 characters")
        if len(set(result)) != len(result):
            raise ValueError("option values must be unique")
        return result


class PreparationGroup(ApiModel):
    user_id: UUID
    quantity: int = Field(ge=1, le=1000)
    choices: dict[str, str] = Field(default_factory=dict, max_length=30)


class PreparationPlan(ApiModel):
    options: list[PreparationOption] = Field(default_factory=list, max_length=30)
    groups: list[PreparationGroup] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def valid_choices(self) -> "PreparationPlan":
        options = {option.key: option for option in self.options}
        if len(options) != len(self.options):
            raise ValueError("option keys must be unique")
        for group in self.groups:
            if any(key not in options or value not in options[key].values
                   for key, value in group.choices.items()):
                raise ValueError("choices must reference values in this preparation snapshot")
            group.choices = {
                key: group.choices.get(key, option.values[0]) for key, option in options.items()
            }
        return self


class SaveTemplatePreparation(PreparationPlan):
    expected_version: int = Field(ge=0)

    @model_validator(mode="after")
    def no_groups(self) -> "SaveTemplatePreparation":
        if self.groups:
            raise ValueError("template preparation cannot contain participant groups")
        return self


class TemplatePreparationResponse(PreparationPlan):
    version: int


class SaveCookPreparation(PreparationPlan):
    expected_version: int = Field(ge=1)


class PreparationWarning(ApiModel):
    option_key: str
    option_name: str
    value: str
    quantity: int
    batch_size: int


class CookPreparationResponse(PreparationPlan):
    row_version: int
    warnings: list[PreparationWarning]
