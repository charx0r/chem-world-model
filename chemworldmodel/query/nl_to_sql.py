"""Natural language to SQL query pipeline.

Converts user chemistry questions into validated SQL, executes them,
and returns grounded answers with reaction ID citations.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, text

from chemworldmodel.config import Settings, get_settings
from chemworldmodel.models.query import LLMSQLResponse, QueryResult
from chemworldmodel.query.grounding import ground_answer
from chemworldmodel.query.prompts import build_sql_generation_prompt, build_synthesis_prompt

# ---------------------------------------------------------------------------
# SQL validation
# ---------------------------------------------------------------------------

_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"COPY|EXECUTE|CALL|VACUUM|DO|LOAD|LISTEN|NOTIFY)\b",
    re.IGNORECASE,
)

_BLOCKED_FUNCTIONS = re.compile(
    r"\b(dblink|lo_import|lo_export|pg_read_file|pg_ls_dir|pg_read_binary_file|"
    r"pg_write_file|pg_terminate_backend|pg_sleep|set_config)\b",
    re.IGNORECASE,
)

_BLOCKED_SCHEMAS = re.compile(
    r"\b(pg_catalog|information_schema|pg_temp|pg_toast)\b",
    re.IGNORECASE,
)

_ALLOWED_SCHEMA_PREFIX = re.compile(r"\b(\w+)\.")
_ALLOWED_SCHEMAS = {"chem", "rxn", "onto", "lineage"}

# Known table names and common SQL aliases used by the LLM
_ALLOWED_IDENTIFIERS = {
    # Table names (used as aliases in queries)
    "molecules", "reactions", "reaction_components", "reaction_conditions",
    "reaction_classes", "molecule_roles", "hazard_data", "data_loads",
    "molecule_provenance",
    # Common SQL functions and aliases
    "round", "count", "array", "generate", "date", "extract",
    "coalesce", "nullif", "greatest", "least", "concat",
    "route", "result", "results", "subquery", "stats",
}

# Strip $$ ... $$ blocks (AGE Cypher) before schema validation
_DOLLAR_QUOTED = re.compile(r"\$\$.*?\$\$", re.DOTALL)

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


class SQLValidationError(ValueError):
    """Raised when LLM-generated SQL fails safety validation."""


def _validate_sql(sql: str, max_chars: int = 2000) -> str:
    """Validate and sanitise LLM-generated SQL.

    Returns cleaned SQL (trailing semicolons stripped).
    Raises SQLValidationError on any violation.
    """
    if not sql or not sql.strip():
        raise SQLValidationError("Empty SQL query")

    # Strip comments before analysis
    cleaned = _LINE_COMMENT.sub(" ", sql)
    cleaned = _BLOCK_COMMENT.sub(" ", cleaned)
    cleaned = cleaned.strip()

    # Length check
    if len(cleaned) > max_chars:
        raise SQLValidationError(f"SQL exceeds {max_chars} character limit ({len(cleaned)} chars)")

    # Must start with SELECT or WITH (CTEs)
    upper = cleaned.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise SQLValidationError("Only SELECT statements (with optional CTEs) are allowed")

    # Strip trailing semicolons
    cleaned = cleaned.rstrip(";").strip()

    # Reject mid-query semicolons (multi-statement injection)
    if ";" in cleaned:
        raise SQLValidationError("Multiple statements (semicolons) not allowed")

    # Blocked DML/DDL keywords
    match = _BLOCKED_KEYWORDS.search(cleaned)
    if match:
        raise SQLValidationError(f"Forbidden keyword: {match.group(0).upper()}")

    # Blocked functions
    match = _BLOCKED_FUNCTIONS.search(cleaned)
    if match:
        raise SQLValidationError(f"Forbidden function: {match.group(0)}")

    # Blocked system schemas
    match = _BLOCKED_SCHEMAS.search(cleaned)
    if match:
        raise SQLValidationError(f"Access to {match.group(0)} is not allowed")

    # Verify only allowed schema prefixes.
    # Strip $$ Cypher blocks first — identifiers inside Cypher (e.g. m.inchikey)
    # are AGE property access, not PostgreSQL schema references.
    sql_without_cypher = _DOLLAR_QUOTED.sub(" ", cleaned)
    for schema_match in _ALLOWED_SCHEMA_PREFIX.finditer(sql_without_cypher):
        schema = schema_match.group(1).lower()
        if schema in _ALLOWED_SCHEMAS:
            continue
        # Allow short aliases (single letters, common abbreviations like m1, r2)
        if len(schema) <= 4:
            continue
        if schema in _ALLOWED_IDENTIFIERS:
            continue
        raise SQLValidationError(f"Schema '{schema}' is not in the allowed list")

    return cleaned


# ---------------------------------------------------------------------------
# LLM adapter
# ---------------------------------------------------------------------------


async def _call_llm(
    provider: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    response_model: type[BaseModel] | None = None,
    *,
    ollama_base_url: str = "http://localhost:11434/v1",
) -> str | BaseModel:
    """Call the configured LLM provider. Returns parsed model or raw text."""

    if provider == "gemini":
        from google import genai
        from google.genai.types import GenerateContentConfig

        client = genai.Client(api_key=api_key)

        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
        }
        if response_model is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_model.model_json_schema()

        response = await client.aio.models.generate_content(
            model=model,
            contents=user_message,
            config=GenerateContentConfig(**config_kwargs),
        )

        text_result = response.text or ""
        if response_model is not None:
            return response_model.model_validate_json(text_result)
        return text_result

    elif provider in ("openai", "ollama"):
        from openai import AsyncOpenAI

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if provider == "ollama":
            client_kwargs = {"api_key": "ollama", "base_url": ollama_base_url}

        client = AsyncOpenAI(**client_kwargs)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        if response_model is not None:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "sql_response",
                        "strict": True,
                        "schema": response_model.model_json_schema(),
                    },
                },
            )
            content = response.choices[0].message.content or "{}"
            return response_model.model_validate_json(content)
        else:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
            )
            return response.choices[0].message.content or ""

    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _extract_sql_fallback(text_response: str) -> str:
    """Extract SQL from a freeform text response (fallback if structured output fails)."""
    # Try ```sql ... ``` blocks
    match = re.search(r"```sql\s*\n?(.*?)```", text_response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Try ``` ... ``` blocks
    match = re.search(r"```\s*\n?(.*?)```", text_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Return as-is if it looks like SQL
    stripped = text_response.strip()
    if stripped.upper().startswith("SELECT"):
        return stripped
    raise SQLValidationError("Could not extract SQL from LLM response")


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------


class NLToSQL:
    """Natural language to SQL query pipeline."""

    def __init__(self, engine: Engine, settings: Settings | None = None):
        self.engine = engine
        self.settings = settings or get_settings()

    async def query(self, question: str) -> QueryResult:
        """Convert a natural language question to SQL, execute, and ground the answer."""
        settings = self.settings

        # Step 1: Generate SQL via LLM
        system_prompt, user_msg = build_sql_generation_prompt(question)
        try:
            llm_response = await _call_llm(
                provider=settings.llm_provider,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                system_prompt=system_prompt,
                user_message=user_msg,
                response_model=LLMSQLResponse,
                ollama_base_url=settings.ollama_base_url,
            )
            sql = llm_response.sql
        except Exception:
            # Fallback: try plain text and extract SQL
            text_response = await _call_llm(
                provider=settings.llm_provider,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                system_prompt=system_prompt,
                user_message=user_msg,
                ollama_base_url=settings.ollama_base_url,
            )
            sql = _extract_sql_fallback(str(text_response))

        # Step 2: Validate SQL
        sql = _validate_sql(sql, max_chars=settings.query_max_sql_chars)

        # Step 3: Execute with timeout
        raw_results = await self._execute_sql(sql)

        # Step 4: Synthesise answer
        synth_system, synth_user = build_synthesis_prompt(question, sql, raw_results)
        answer_text = await _call_llm(
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            system_prompt=synth_system,
            user_message=synth_user,
            ollama_base_url=settings.ollama_base_url,
        )

        # Step 5: Ground the answer
        return ground_answer(raw_results, str(answer_text), sql)

    async def _execute_sql(self, sql: str) -> list[dict[str, Any]]:
        """Execute validated SQL in a read-only transaction with timeout."""

        def _run() -> list[dict[str, Any]]:
            timeout_ms = self.settings.query_timeout * 1000
            with self.engine.connect() as conn:
                with conn.begin():
                    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                    conn.exec_driver_sql(
                        f"SET LOCAL statement_timeout = {int(timeout_ms)}"
                    )
                    conn.exec_driver_sql("LOAD 'age'")
                    conn.exec_driver_sql(
                        "SET LOCAL search_path = ag_catalog, chem, rxn, onto, public"
                    )
                    result = conn.exec_driver_sql(sql)
                    columns = list(result.keys())
                    rows = result.fetchall()
                    return [dict(zip(columns, row)) for row in rows]

        return await asyncio.to_thread(_run)

    def query_sync(self, question: str) -> QueryResult:
        """Synchronous wrapper for CLI usage."""
        return asyncio.run(self.query(question))
