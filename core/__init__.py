"""Pure analysis modules for Sentinel.

Modules here take data plus an injected ``now`` and return results. They never
open the database, read files, inspect the clock (except ``timeutil.utc_now``),
or make network calls.
"""
