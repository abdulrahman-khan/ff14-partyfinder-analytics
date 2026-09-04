# Improvements

Open backlog items called out from within the codebase itself - not aspirational, just things
already flagged in a comment or doc and not yet acted on.

## 1. `description_clean` may still leak player names

The bronze→silver boundary pseudonymizes `creator`/`creator_server` into `player_hash` and
`creator_initials` (see [`architecture.md`](architecture.md)), but `description_clean` is free
text a player typed into their own listing.
It can still contain a name they wrote themselves (their own, a friend's, a static group's).
No transform strips this today - it is out of scope for the hash/initials boundary, which only
covers the structured creator fields.

## 2. `dim_worlds` needs a world-alias mapping

`silver.qa_unmatched_worlds` is a non-blocking monitoring view that lists `raw_listings.world`
values that fail to match `dim_worlds` on `LOWER(TRIM(world))`.
A match failure nulls `pf_world_key`/`creator_world_key`, which silently drops the listing from
every region/datacenter rollup in gold.
A consistently non-empty result means either a new world needs adding to
`reference/worlds.csv`, or a `world_aliases` mapping table is needed for cases where xivpf's
world spelling drifts from the canonical name.
