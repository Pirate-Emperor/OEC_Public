Request targeted synchronization of OEC FLUX/TRELLIS/LTX support into the persistent A100 OEC checkout.
Seven pipeline tools are already synced. This pass snapshots and replaces only the authorized TRELLIS entry point and TRELLIS notebooks after verifying backups, copies missing FLUX/combined entry points, preserves unrelated dirty files, and revalidates CLI/config/notebook syntax.
The live checkout has no root requirements.txt; no dependencies are installed. No model download, inference, broad checkout reset, cache purge, or storage-reserve access.
