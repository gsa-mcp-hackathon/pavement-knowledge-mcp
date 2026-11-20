# Sources and third-party notices

## Pavement corpus

This corpus contains text extracted and processed from publicly available pavement
research documents. It is provided for hackathon evaluation. Source
references are retained. Some documents may contain third-party copyrighted
material; applicable rights and restrictions remain with their respective owners.

The prepared release contains 68,655 chunks associated with 584 report IDs.
Recorded PDF links point to www.fhwa.dot.gov and international.fhwa.dot.gov.
See runtime/SOURCES.csv for report identities and original source links. Existing
notices within the extracted text are retained. Public availability is not a claim
that every included passage is public domain or unrestricted for redistribution.
No document-by-document rights clearance is asserted by this package.

Text extraction may introduce errors or omit figures, tables and context. Consult
the original reports for authoritative wording and complete findings. Metadata
file_path values were cleared for portability; report identities and source URLs
were preserved. No original PDFs are required for the supplied retrieval runtime.

FHWA's guidance on copyrighted content in publications:
https://www.fhwa.dot.gov/publications/research/general/15058/004.cfm

## Embedding model

The bundle includes the cached Sentence Transformers/Safetensors files for
intfloat/e5-large-v2 at revision f169b11e22de13617baa190a028a32f3493550b6.
The upstream model card declares the MIT license and is retained alongside the
model. Model authors: Liang Wang, Nan Yang, Xiaolong Huang, Binxing Jiao, Linjun
Yang, Daxin Jiang, Rangan Majumder and Furu Wei (E5 research, 2022).

Model/revision: https://huggingface.co/intfloat/e5-large-v2/tree/f169b11e22de13617baa190a028a32f3493550b6
Linked E5 project: https://github.com/microsoft/unilm/tree/master/e5
The linked project's MIT notice is retained in third_party/E5-MIT-LICENSE.txt,
with its Microsoft copyright notice. These notices apply to the upstream model/
project material; they do not assign that license to this MCP's code or corpus.

## Python dependencies

server/requirements.txt records all 113 locked wheel versions and hashes for
Windows x64 / CPython 3.11. The original wheels in wheelhouse/ retain their
upstream metadata and bundled license/notice files; installation preserves those
files in the environment. Their individual terms remain applicable. Dependencies
and the embedding model are not claimed as original work of this project.
