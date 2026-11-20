"""Local query embeddings compatible with the prebuilt corpus index."""

from __future__ import annotations

import logging
import os
import warnings
from typing import List


class Embedder:
    def __init__(self, model_name: str = "intfloat/e5-large-v2") -> None:
        self.model_name = model_name
        self._lower_model_name = model_name.lower()

        # Keep dependency diagnostics off the protocol stream.
        if os.getenv("FHWA_SUPPRESS_HF_WARNINGS", "true").strip().lower() != "false":
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
            warnings.filterwarnings(
                "ignore",
                message=r"You are sending unauthenticated requests to the HF Hub.*",
            )

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed in the active environment. "
                "Install the MCP dependencies in the Python environment used to launch it."
            ) from exc

        self.model = SentenceTransformer(model_name)

    def _is_e5_family(self) -> bool:
        return "e5" in self._lower_model_name

    def _prepare_query(self, query: str) -> str:
        q = str(query or "")
        if self._is_e5_family():
            return f"query: {q}"
        return q

    def embed_query(self, query: str) -> List[float]:
        prepared = self._prepare_query(query)
        vec = self.model.encode(
            [prepared],
            normalize_embeddings=True,
            show_progress_bar=True,
            batch_size=1,
        ).tolist()
        return vec[0]
