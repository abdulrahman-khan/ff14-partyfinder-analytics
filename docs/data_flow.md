# Data Flow

Two views of the same pipeline: how the data physically moves through GCP services (orchestration), and how it is cleaned, joined, and reshaped as it crosses the medallion layers (lineage). See [`architecture.md`](architecture.md) for narrative detail and [`gold_marts.md`](gold_marts.md) for the full mart catalog.

Icons are plain emoji, not brand logos - GitHub/VS Code render Markdown's Mermaid fences without executing JS, so a real GCP or FFXIV logo (which requires registering an icon pack at runtime) won't render there. Emoji is the one icon mechanism guaranteed to display everywhere.

## Orchestration

Only the scraper is scheduled. The loader is run on demand and, on success, fires the pipeline workflow itself. The workflow uses a blocking connector, so the duty-extractor always finishes before Dataform runs.

Legend: 🎮 external source · ⏰ trigger · ☁️ Cloud Run · 🪣 object storage (GCS) · 🗄️ BigQuery · ⚙️ orchestration.

```mermaid
flowchart TD
    classDef source fill:#6b7280,stroke:#374151,color:#fff
    classDef trigger fill:#f59e0b,stroke:#92600a,color:#1a1a1a
    classDef compute fill:#1a73e8,stroke:#174ea6,color:#fff
    classDef storage fill:#34a853,stroke:#1e7e34,color:#fff
    classDef orchestration fill:#9333ea,stroke:#5b21b6,color:#fff

    Source["🎮 xivpf.com"]:::source --> Scraper["☁️ Cloud Run: scraper"]:::compute
    CS["⏰ Cloud Scheduler<br/>every 15 min"]:::trigger --> Scraper
    Scraper -->|parse HTML| GCS[("🪣 GCS: ff14-pf-data-raw<br/>append-only")]:::storage
    GCS --> Loader["☁️ Cloud Run: loader<br/>(on demand)"]:::compute
    Loader -->|insert| BronzeListings[("🗄️ bronze.raw_listings")]:::storage
    Loader -.->|on success| Workflow{{"⚙️ Cloud Workflows<br/>ff14-pf-pipeline"}}:::orchestration
    Workflow --> DutyExtractor["☁️ Cloud Run: duty-extractor"]:::compute
    DutyExtractor --> BronzeDuties[("🗄️ bronze.raw_duties")]:::storage
    DutyExtractor -.->|then| DataformRunner["☁️ Cloud Run: dataform-runner"]:::compute
    DataformRunner --> SilverGold[("🗄️ silver.* → gold.*")]:::storage
```

## Medallion lineage

Bronze is raw and append-only. Silver is where cleaning, keying, and the two hardest transforms happen: pseudonymization and sessionization. Gold is ten pre-aggregated marts, all sourced from one keystone fact.

Legend: 🥉 bronze · 🥈 silver · 🥇 gold · 🔒 privacy-restricted (dashed = manual/annotation, not a data transform).

```mermaid
flowchart TD
    classDef bronze fill:#b5651d,stroke:#7a430f,color:#fff
    classDef silver fill:#64748b,stroke:#334155,color:#fff
    classDef gold fill:#eab308,stroke:#92710a,color:#1a1a1a
    classDef note fill:#f3f4f6,stroke:#9ca3af,stroke-dasharray: 4 3,color:#374151

    subgraph BronzeLayer["🥉 BRONZE - raw, append-only"]
        direction LR
        B_listings[("raw_listings<br/>real creator name")]:::bronze
        B_duties[("raw_duties")]:::bronze
        B_duties_ref[("raw_duties_reference<br/>curated CSV")]:::bronze
        B_worlds[("raw_worlds")]:::bronze
        B_players[("dim_players<br/>identity vault")]:::bronze
    end
    PrivacyNote["🔒 bronze-restricted by IAM<br/>real name never leaves bronze"]:::note
    B_players -.-> PrivacyNote

    subgraph SilverLayer["🥈 SILVER - cleaned, keyed, flagged"]
        direction LR
        S_fct[("fct_listings<br/>periodic snapshot")]:::silver
        S_dedup[("fct_listings_deduped")]:::silver
        S_lifecycle[("fct_listing_lifecycle<br/>KEYSTONE")]:::silver
        S_dim_duties[("dim_duties")]:::silver
        S_dim_worlds[("dim_worlds<br/>manual stub")]:::silver
        S_dim_date[("dim_date")]:::silver
    end

    subgraph GoldLayer["🥇 GOLD - pre-aggregated marts"]
        G["10 marts<br/>pattern + trend + fill_funnel<br/>see gold_marts.md"]:::gold
    end

    B_listings -->|pseudonymize| S_fct
    B_duties --> S_dim_duties
    B_duties_ref -->|classification| S_dim_duties
    B_worlds -.->|manual load| S_dim_worlds

    S_fct --> S_dedup
    S_fct -->|sessionize, 30min gap| S_lifecycle
    S_dim_duties --> S_lifecycle
    S_dim_worlds --> S_lifecycle
    S_dim_date --> S_lifecycle
    S_lifecycle --> G
```

**Reading the pseudonymization boundary:** `bronze.raw_listings` is the only table that ever holds a real character name. Every downstream row carries `player_hash = TO_HEX(MD5(lower(creator)|lower(creator_server)))` and `creator_initials` instead. `bronze.dim_players` is the sole reverse-lookup table, and it stays behind the same IAM line as the rest of bronze - `analyst_group` never gets bronze access.

**Reading the sessionization step:** `fct_listings` is a snapshot (one row per listing per scrape, every 15 min). `fct_listing_lifecycle` collapses that stream into sessions - a content-hashed `listing_id` can repeat weeks apart, so consecutive scrapes more than 30 minutes apart start a new session. This is the step that turns raw scrape noise into fill-rate and time-to-fill metrics, and every gold mart reads from its output, never from `fct_listings` directly.
