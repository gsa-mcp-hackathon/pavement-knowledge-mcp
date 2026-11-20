"""Fixed public errors, never exception text or rejected argument values."""

MESSAGES = {
    "INVALID_ARGUMENT": "Check the tool inputs and documented limits.",
    "PUBLICATION_NOT_FOUND": "Publication not found. Use search_publications to select a corpus document ID.",
    "CORPUS_UNAVAILABLE": "The publication corpus is unavailable. Ask the server operator to check setup.",
    "SERVICE_UNAVAILABLE": "The requested service is unavailable. Ask the server operator to check setup.",
    "INVALID_SERVICE_RESPONSE": "The service returned an unusable result. No evidence was released.",
    "INTERNAL_ERROR": "The tool could not complete this request. Ask the server operator to investigate.",
}


class ToolFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(MESSAGES[code])


def error_payload(code: str) -> dict:
    return {"error": {"code": code, "message": MESSAGES[code]}}
