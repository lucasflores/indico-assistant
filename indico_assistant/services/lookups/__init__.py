"""Typed lookups over Indico's own code and access checks (spec 025 story 4, research R7, FR-030, FR-031).

Each lookup runs as the asking user, inside ``acting_as(user)`` (research R6: ``Contribution.can_manage`` reads
``session.user``), and returns only what Indico's own ``can_access`` grants that user: events granted through
their groups included, a protected event with no grant left out, not even its existence.
"""
