"""Connectors (spec 023): the user's own accounts elsewhere, read with their own token. GitHub is the first."""

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel


@dataclass(frozen=True)
class Tool:
    """A read tool: ``args`` is a Pydantic model with a literal ``tool`` field equal to ``name``, and its docstring is
    what the model reads about the tool; ``run(client, args)`` returns text. (The shape of an MCP tool, so a later
    connector can be backed by an MCP server without changing the loop.)"""

    name: str
    args: type[BaseModel]
    run: Callable[[Any, BaseModel], str]

    @property
    def description(self):
        return inspect.cleandoc(self.args.__doc__ or "")
