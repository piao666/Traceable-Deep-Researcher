"""Core table mappings; schema is created only by versioned SQL migrations."""

from sqlalchemy import Column, Integer, MetaData, Table, Text

metadata = MetaData()
reports = Table("reports", metadata,
    Column("report_id", Text, primary_key=True), Column("payload_json", Text),
    Column("timestamp", Integer), Column("current_version", Integer),
    Column("content_hash", Text), Column("origin", Text), Column("lineage_status", Text))
report_versions = Table("report_versions", metadata,
    Column("report_id", Text, primary_key=True), Column("version", Integer, primary_key=True),
    Column("payload_json", Text), Column("content_hash", Text))
report_chats = Table("report_chats", metadata,
    Column("report_id", Text, primary_key=True), Column("position", Integer, primary_key=True),
    Column("message_id", Text), Column("report_version", Integer), Column("payload_json", Text))
legacy_batches = Table("legacy_batches", metadata,
    Column("source_hash", Text, primary_key=True), Column("source_key", Text),
    Column("record_count", Integer))
legacy_imports = Table("legacy_imports", metadata,
    Column("source_hash", Text, primary_key=True), Column("report_id", Text, primary_key=True),
    Column("source_key", Text), Column("record_hash", Text))
