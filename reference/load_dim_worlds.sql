CREATE OR REPLACE TABLE `ff14-pf-data.silver.dim_worlds` AS
SELECT
  TO_HEX(MD5(TRIM(world,      "'"))) AS world_key,
  TRIM(world,      "'") AS world,
  TRIM(datacenter, "'") AS datacenter,
  TRIM(region,     "'") AS region
FROM `ff14-pf-data.bronze.raw_worlds`

