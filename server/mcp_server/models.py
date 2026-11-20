"""Strict input and output schemas for the three evidence-access tools."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("A nonblank string is required")
    return value


Query = Annotated[str, Field(max_length=8000), AfterValidator(nonblank)]
DocumentId = Annotated[str, Field(max_length=200), AfterValidator(nonblank), AfterValidator(str.strip)]
Nonnegative = Annotated[int, Field(ge=0)]
Nonblank = Annotated[str, AfterValidator(nonblank)]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class SearchInput(StrictModel):
    search: Annotated[str, Field(max_length=500)] | None = Field(default=None,
        description="Topic, title or report number, e.g. pavement deflection testing. Omit to browse.")
    topic: Annotated[str, Field(max_length=200)] | None = None
    year: Annotated[int, Field(ge=1, le=9999)] | None = None
    limit: Annotated[int, Field(ge=1, le=25)] = 10
    offset: Annotated[int, Field(ge=0, le=100000)] = 0


class PublicationInput(StrictModel):
    doc_id: DocumentId = Field(description="Exact doc_id returned by search_publications, not a title or URL.")


class RetrieveEvidenceInput(StrictModel):
    mode: Literal["query", "report_overview"] = Field(default="query",
        description="Query finds relevant passages; report_overview collects varied report sections.")
    query: Query | None = Field(default=None,
        description="Question/topic required in query mode; omit in report_overview mode.")
    doc_id: DocumentId | None = Field(default=None,
        description="Exact catalog ID. Omit for corpus-wide query; required for report_overview.")
    limit: Annotated[int, Field(ge=1, le=12)] = Field(default=8,
        description="Maximum passages; fewer may be returned. Total passage text is bounded to 16000 characters.")

    @model_validator(mode="after")
    def check_mode(self):
        if self.mode == "query" and self.query is None:
            raise ValueError("Query mode requires query.")
        if self.mode == "report_overview" and (self.doc_id is None or self.query is not None):
            raise ValueError("Report overview requires doc_id and no query.")
        return self


class Publication(StrictModel):
    doc_id: Nonblank
    title: str
    report_no: str
    year: int | None
    topic: str
    primary_topic: str
    pdf_url: str
    trust_badge: str
    abstract: str
    page_count: int | None


class SearchPublication(Publication):
    match_status: Literal["catalog_record", "metadata_match", "content_mention"]
    match_reason: str


class SearchResult(StrictModel):
    items: list[SearchPublication]
    count: Nonnegative
    topics: list[str]
    years: list[int]


class EvidencePassage(StrictModel):
    rank: Annotated[int, Field(ge=1)]
    chunk_id: Nonblank
    doc_id: Nonblank
    doc_title: str
    report_no: str | None
    pdf_url: str | None
    section_header: str | None
    page_start: int | None
    page_end: int | None
    text: str
    text_truncated: bool


SectionRole = Literal["purpose", "methods", "findings", "conclusions", "limitations", "recommendations", "other"]


class EvidenceCoverage(StrictModel):
    section_roles_present: list[SectionRole]
    section_roles_not_observed: list[SectionRole]
    basis: Literal["Heuristic labels from retrieved section headings; not verification of content coverage."]
    complete_report: Literal[False]


class RetrievedEvidence(StrictModel):
    mode: Literal["query", "report_overview"]
    scope: Literal["corpus", "publication"]
    query: str | None
    doc_id: str | None
    corpus_version: Nonblank
    passages: list[EvidencePassage]
    candidate_count: Nonnegative
    duplicates_removed: Nonnegative
    candidate_scan_truncated: bool
    truncated: bool
    coverage: EvidenceCoverage
    warnings: list[str]
