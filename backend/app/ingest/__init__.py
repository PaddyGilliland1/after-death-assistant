"""Knowledge ingestion pipeline (build contract sections 9 and 10).

fetch -> extract -> chunk -> embed -> store, with hash-diff change
detection and Open Government Licence attribution recorded on every
document. The seed source registry lives in
seed_templates/source_registry.json.
"""
