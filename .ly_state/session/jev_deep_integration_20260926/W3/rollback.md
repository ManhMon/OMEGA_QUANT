# W3 rollback

Disable shadow consumers; restore scoped source files from their prior revision. Existing `price_basis=adjusted` records remain explicitly marked; do not re-adjust them. Preserve original raw prices and PIT availability evidence.

Rollback base commit: `256175958f86cce7ef0e17424ed3c39a5c4911da`.

Rem17 publication failure: keep the committed manifest and its immutable generation. Legacy output/report backups are restored on MemoryError or Exception; if restoration fails, retain backup `.tmp` files for manual recovery under the output lock.
